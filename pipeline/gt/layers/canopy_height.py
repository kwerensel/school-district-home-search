from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import geopandas as gpd
import mercantile
import numpy as np
import psycopg
import rasterio
import rasterio.warp
from rasterio.features import geometry_mask, rasterize
from rasterio.enums import Resampling
from rasterio.transform import rowcol
from rasterio.windows import Window, from_bounds
from affine import Affine
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from gt.db.migrate import database_url
from gt.manifests import LayerManifest, load_layer_manifest
from gt.reports import ValidationReport, write_report

S3_HTTP_PREFIX = (
    "https://dataforgood-fb-data.s3.amazonaws.com/"
    "forests/v2/global/dinov3_global_chm_v2_ml3/chm"
)


@dataclass(frozen=True)
class RegionMetric:
    region_slug: str
    value: float


@dataclass(frozen=True)
class ListingMetric:
    listing_id: int
    grain: str
    value: float


def run_canopy_height(manifest_path: Path, region_slug: str, grain: str) -> tuple[ValidationReport, Path]:
    manifest = load_layer_manifest(manifest_path)
    if manifest.metric_key != "canopy_height_m":
        raise ValueError(f"Unsupported canopy manifest metric: {manifest.metric_key}")
    if grain not in {"tract", "listing", "both"}:
        raise ValueError("grain must be tract, listing, or both")

    with psycopg.connect(database_url(), autocommit=False) as conn:
        tracts = _read_tracts(conn, region_slug)
        listings = _read_listings(conn, region_slug)
        if tracts.empty:
            raise RuntimeError(f"No census tract regions found for {region_slug}")
        if listings.empty:
            raise RuntimeError(f"No frozen listings found for {region_slug}")

        bbox = tuple(tracts.total_bounds)
        tiles = _tiles_for_bbox(bbox)

        region_metrics: list[RegionMetric] = []
        listing_metrics: list[ListingMetric] = []
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
            sources = _open_sources(tiles)
            try:
                if grain in {"tract", "both"}:
                    region_metrics = _compute_region_metrics(tracts, sources)
                if grain in {"listing", "both"}:
                    listing_metrics = _compute_listing_metrics(listings, sources)
            finally:
                for source in sources.values():
                    source.close()

        with conn.cursor() as cur:
            _clear_staging(cur, region_slug, manifest.metric_key)
            _stage_region_metrics(cur, region_slug, manifest, region_metrics)
            _stage_listing_metrics(cur, region_slug, manifest, listing_metrics)
            checks = _validation_checks(cur, region_slug, manifest, grain)
        conn.commit()

    range_min, range_max = manifest.allowed_range
    promotable = (
        checks["range_min"] >= range_min
        and checks["range_max"] <= range_max
        and checks["tract_coverage"] >= manifest.coverage_threshold
        and (
            grain == "tract"
            or checks["listing_point_coverage"] >= 1.0
            and checks["listing_buffer_100m_coverage"] >= 1.0
        )
    )
    report = ValidationReport(
        report_type="layer",
        target=f"{manifest.metric_key}:{region_slug}",
        status="staged",
        promotable=promotable,
        checks=checks,
    )
    path = write_report(report, f"layer_{manifest.metric_key}_{region_slug}_latest.json")
    return report, path


def _read_tracts(conn: psycopg.Connection[Any], region_slug: str) -> gpd.GeoDataFrame:
    return gpd.read_postgis(
        """
        SELECT id, slug, geom
        FROM regions
        WHERE region_group = %s
          AND region_type = 'census_tract'
        ORDER BY slug
        """,
        conn,
        params=(region_slug,),
        geom_col="geom",
    )


def _read_listings(conn: psycopg.Connection[Any], region_slug: str) -> gpd.GeoDataFrame:
    return gpd.read_postgis(
        """
        SELECT id, geom
        FROM listings
        WHERE region_slug = %s
        ORDER BY id
        """,
        conn,
        params=(region_slug,),
        geom_col="geom",
    )


def _tiles_for_bbox(bbox: tuple[float, float, float, float]) -> list[str]:
    return [mercantile.quadkey(tile) for tile in mercantile.tiles(*bbox, zooms=[10])]


def _open_sources(tiles: Iterable[str]) -> dict[str, rasterio.DatasetReader]:
    return {
        tile: rasterio.open(f"{S3_HTTP_PREFIX}/{tile}.tif")
        for tile in tiles
    }


def _source_tile_geom(source: rasterio.DatasetReader) -> BaseGeometry:
    bounds_4326 = rasterio.warp.transform_bounds(source.crs, "EPSG:4326", *source.bounds)
    return box(*bounds_4326)


def _compute_region_metrics(
    tracts: gpd.GeoDataFrame, sources: dict[str, rasterio.DatasetReader]
) -> list[RegionMetric]:
    tracts_3857 = tracts.to_crs("EPSG:3857")
    tile_geoms = {tile: _source_tile_geom(source) for tile, source in sources.items()}
    slugs = list(tracts["slug"])
    sums = np.zeros(len(tracts), dtype="float64")
    counts = np.zeros(len(tracts), dtype="int64")

    for tile, source in sources.items():
        matching = tracts.intersects(tile_geoms[tile]).to_numpy()
        if not matching.any():
            continue
        subset = tracts_3857.loc[matching].copy()
        labels = np.flatnonzero(matching) + 1
        out_width = 2048
        out_height = 2048
        data = source.read(
            1,
            out_shape=(out_height, out_width),
            resampling=Resampling.average,
            masked=False,
        )
        transform = source.transform * Affine.scale(
            source.width / out_width,
            source.height / out_height,
        )
        label_grid = rasterize(
            zip(subset.geom, labels, strict=True),
            out_shape=data.shape,
            transform=transform,
            fill=0,
            dtype="int32",
            all_touched=True,
        )
        valid = label_grid > 0
        if not valid.any():
            continue
        flat_labels = label_grid[valid]
        flat_values = data[valid].astype("float64")
        tile_sums = np.bincount(flat_labels, weights=flat_values, minlength=len(tracts) + 1)
        tile_counts = np.bincount(flat_labels, minlength=len(tracts) + 1)
        sums += tile_sums[1:]
        counts += tile_counts[1:]

    return [
        RegionMetric(region_slug=str(slug), value=float(value_sum / count))
        for slug, value_sum, count in zip(slugs, sums, counts, strict=True)
        if count
    ]


def _compute_listing_metrics(
    listings: gpd.GeoDataFrame, sources: dict[str, rasterio.DatasetReader]
) -> list[ListingMetric]:
    listings_3857 = listings.to_crs("EPSG:3857")
    metrics: list[ListingMetric] = []
    listing_tiles: list[str] = []
    for listing_4326 in listings.itertuples():
        tile = mercantile.quadkey(mercantile.tile(float(listing_4326.geom.x), float(listing_4326.geom.y), 10))
        listing_tiles.append(tile)

    listing_ids = list(listings["id"])
    listings_3857 = listings_3857.copy()
    listings_3857["tile"] = listing_tiles
    listings_3857["buffer_100m"] = listings_3857.geom.buffer(100)

    for tile, source in sources.items():
        matching = (listings_3857["tile"] == tile).to_numpy()
        if not matching.any():
            continue
        subset = listings_3857.loc[matching]
        out_width = 4096
        out_height = 4096
        data = source.read(
            1,
            out_shape=(out_height, out_width),
            resampling=Resampling.average,
            masked=False,
        )
        transform = source.transform * Affine.scale(
            source.width / out_width,
            source.height / out_height,
        )
        coords = [(float(row.geom.x), float(row.geom.y)) for row in subset.itertuples()]
        rows, cols = rowcol(transform, [coord[0] for coord in coords], [coord[1] for coord in coords])
        for listing_id, row, col in zip(subset["id"], rows, cols, strict=True):
            if 0 <= row < data.shape[0] and 0 <= col < data.shape[1]:
                point_value = data[row, col]
                if np.isfinite(point_value):
                    metrics.append(
                        ListingMetric(
                            listing_id=int(listing_id),
                            grain="point",
                            value=float(point_value),
                        )
                    )

        for row in subset.itertuples():
            buffer_mean = _array_masked_mean(data, transform, row.buffer_100m)
            if buffer_mean is not None:
                metrics.append(
                    ListingMetric(
                        listing_id=int(row.id),
                        grain="buffer_100m",
                        value=buffer_mean,
                    )
                )
    return metrics


def _array_masked_mean(data: np.ndarray, transform: Affine, geom: BaseGeometry) -> float | None:
    window = from_bounds(*geom.bounds, transform=transform)
    window = window.round_offsets().round_lengths()
    full_window = Window(0, 0, data.shape[1], data.shape[0])
    window = _intersection_window(window, full_window)
    if window.width <= 0 or window.height <= 0:
        return None
    row0 = int(window.row_off)
    row1 = int(window.row_off + window.height)
    col0 = int(window.col_off)
    col1 = int(window.col_off + window.width)
    subset = data[row0:row1, col0:col1]
    subset_transform = transform * Affine.translation(col0, row0)
    mask = geometry_mask([geom], out_shape=subset.shape, transform=subset_transform, invert=True)
    values = subset[mask]
    if values.size == 0:
        return None
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None
    return float(finite.mean())


def _masked_sum_count(
    source: rasterio.DatasetReader, geom: BaseGeometry, max_pixels: int
) -> tuple[float, int]:
    window = from_bounds(*geom.bounds, transform=source.transform)
    window = window.round_offsets().round_lengths()
    full_window = Window(0, 0, source.width, source.height)
    window = _intersection_window(window, full_window)
    if window.width <= 0 or window.height <= 0:
        return 0.0, 0
    pixels = int(window.width * window.height)
    if pixels > max_pixels:
        scale = (pixels / max_pixels) ** 0.5
        out_height = max(1, int(window.height / scale))
        out_width = max(1, int(window.width / scale))
        data = source.read(
            1,
            window=window,
            out_shape=(out_height, out_width),
            resampling=Resampling.average,
            masked=False,
        )
        transform = source.window_transform(window) * Affine.scale(
            window.width / out_width,
            window.height / out_height,
        )
    else:
        data = source.read(1, window=window, masked=False)
        transform = source.window_transform(window)
    mask = geometry_mask([geom], out_shape=data.shape, transform=transform, invert=True)
    values = data[mask]
    if values.size == 0:
        return 0.0, 0
    finite = values[np.isfinite(values)]
    return float(finite.sum()), int(finite.size)


def _intersection_window(window: Window, full: Window) -> Window:
    col0 = max(window.col_off, full.col_off)
    row0 = max(window.row_off, full.row_off)
    col1 = min(window.col_off + window.width, full.col_off + full.width)
    row1 = min(window.row_off + window.height, full.row_off + full.height)
    return Window(col0, row0, max(0, col1 - col0), max(0, row1 - row0))


def _clear_staging(cur: psycopg.Cursor[Any], region_slug: str, metric_key: str) -> None:
    cur.execute(
        "DELETE FROM staging.layer_region_metrics WHERE region_group = %s AND metric_key = %s",
        (region_slug, metric_key),
    )
    cur.execute(
        "DELETE FROM staging.layer_listing_metrics WHERE region_group = %s AND metric_key = %s",
        (region_slug, metric_key),
    )


def _stage_region_metrics(
    cur: psycopg.Cursor[Any],
    region_slug: str,
    manifest: LayerManifest,
    metrics: list[RegionMetric],
) -> None:
    cur.executemany(
        """
        INSERT INTO staging.layer_region_metrics
          (region_group, metric_key, region_slug, value, vintage)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (region_group, metric_key, region_slug, vintage) DO UPDATE SET
          value = EXCLUDED.value
        """,
        [
            (region_slug, manifest.metric_key, metric.region_slug, metric.value, manifest.vintage)
            for metric in metrics
        ],
    )


def _stage_listing_metrics(
    cur: psycopg.Cursor[Any],
    region_slug: str,
    manifest: LayerManifest,
    metrics: list[ListingMetric],
) -> None:
    cur.executemany(
        """
        INSERT INTO staging.layer_listing_metrics
          (region_group, metric_key, listing_id, grain, value, vintage)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (region_group, metric_key, listing_id, grain, vintage) DO UPDATE SET
          value = EXCLUDED.value
        """,
        [
            (
                region_slug,
                manifest.metric_key,
                metric.listing_id,
                metric.grain,
                metric.value,
                manifest.vintage,
            )
            for metric in metrics
        ],
    )


def _validation_checks(
    cur: psycopg.Cursor[Any], region_slug: str, manifest: LayerManifest, grain: str
) -> dict[str, Any]:
    cur.execute(
        """
        SELECT count(*)
        FROM regions
        WHERE region_group = %s
          AND region_type = 'census_tract'
        """,
        (region_slug,),
    )
    expected_tracts = int(cur.fetchone()[0])
    cur.execute("SELECT count(*) FROM listings WHERE region_slug = %s", (region_slug,))
    expected_listings = int(cur.fetchone()[0])
    cur.execute(
        """
        SELECT count(*), coalesce(min(value), 0), coalesce(max(value), 0)
        FROM staging.layer_region_metrics
        WHERE region_group = %s
          AND metric_key = %s
          AND vintage = %s
        """,
        (region_slug, manifest.metric_key, manifest.vintage),
    )
    tract_count, region_min, region_max = cur.fetchone()
    cur.execute(
        """
        SELECT grain, count(*), coalesce(min(value), 0), coalesce(max(value), 0)
        FROM staging.layer_listing_metrics
        WHERE region_group = %s
          AND metric_key = %s
          AND vintage = %s
        GROUP BY grain
        """,
        (region_slug, manifest.metric_key, manifest.vintage),
    )
    listing_rows = {row[0]: row[1:] for row in cur.fetchall()}
    mins = [float(region_min)]
    maxes = [float(region_max)]
    for _, min_value, max_value in listing_rows.values():
        mins.append(float(min_value))
        maxes.append(float(max_value))
    return {
        "metric_key": manifest.metric_key,
        "region": region_slug,
        "grain": grain,
        "tracts_expected": expected_tracts,
        "tracts_computed": int(tract_count),
        "tract_coverage": int(tract_count) / expected_tracts if expected_tracts else 0,
        "listings_expected": expected_listings,
        "listing_point_computed": int(listing_rows.get("point", (0, 0, 0))[0]),
        "listing_point_coverage": int(listing_rows.get("point", (0, 0, 0))[0])
        / expected_listings
        if expected_listings
        else 0,
        "listing_buffer_100m_computed": int(listing_rows.get("buffer_100m", (0, 0, 0))[0]),
        "listing_buffer_100m_coverage": int(listing_rows.get("buffer_100m", (0, 0, 0))[0])
        / expected_listings
        if expected_listings
        else 0,
        "range_allowed": list(manifest.allowed_range),
        "range_min": min(mins),
        "range_max": max(maxes),
    }
