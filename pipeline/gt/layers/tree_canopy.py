from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import psycopg
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.features import geometry_mask, rasterize
from rasterio.windows import Window, from_bounds
from shapely.geometry.base import BaseGeometry

from gt.db.migrate import database_url
from gt.manifests import LayerManifest, load_layer_manifest
from gt.reports import ValidationReport, write_report

NLCD_TCC_ZIP_URL = (
    "https://data.fs.usda.gov/geodata/rastergateway/treecanopycover/docs/"
    "v2025-6/nlcd_tcc_conus_2025_v2025-6_wgs84.zip"
)
NLCD_TCC_MEMBER = "nlcd_tcc_conus_wgs84_v2025-6_20250101_20251231.tif"


@dataclass(frozen=True)
class RegionMetric:
    region_slug: str
    value: float


@dataclass(frozen=True)
class ListingMetric:
    listing_id: int
    grain: str
    value: float


def run_tree_canopy(manifest_path: Path, region_slug: str, grain: str) -> tuple[ValidationReport, Path]:
    manifest = load_layer_manifest(manifest_path)
    if manifest.metric_key != "tree_canopy_pct":
        raise ValueError(f"Unsupported tree canopy manifest metric: {manifest.metric_key}")
    if grain not in {"tract", "listing", "both"}:
        raise ValueError("grain must be tract, listing, or both")

    with psycopg.connect(database_url(), autocommit=False) as conn:
        tracts = _read_tracts(conn, region_slug)
        listings = _read_listings(conn, region_slug)
        if tracts.empty:
            raise RuntimeError(f"No census tract regions found for {region_slug}")
        if listings.empty:
            raise RuntimeError(f"No frozen listings found for {region_slug}")

        with rasterio.Env(
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
            CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".zip,.tif",
        ):
            with rasterio.open(_raster_path()) as source:
                if source.nodata != 255:
                    raise RuntimeError(f"Unexpected NLCD TCC NoData value: {source.nodata}")
                if not source.crs:
                    raise RuntimeError("NLCD TCC raster is missing CRS metadata")

                tracts_src = tracts.to_crs(source.crs)
                listings_src = listings.to_crs(source.crs)
                listing_buffers = _listing_buffers(listings_src)
                data, transform = _read_region_window(source, tracts_src, listing_buffers)

                region_metrics: list[RegionMetric] = []
                listing_metrics: list[ListingMetric] = []
                if grain in {"tract", "both"}:
                    region_metrics = _compute_region_metrics(tracts, tracts_src, data, transform)
                if grain in {"listing", "both"}:
                    listing_metrics = _compute_listing_metrics(listings, listing_buffers, data, transform)

        with conn.cursor() as cur:
            _clear_staging(cur, region_slug, manifest.metric_key)
            _stage_region_metrics(cur, region_slug, manifest, region_metrics)
            _stage_listing_metrics(cur, region_slug, manifest, listing_metrics)
            checks = _validation_checks(cur, region_slug, manifest, grain)
        conn.commit()

    range_min, range_max = manifest.allowed_range
    needs_tract = grain in {"tract", "both"}
    needs_listing = grain in {"listing", "both"}
    promotable = (
        checks["range_min"] >= range_min
        and checks["range_max"] <= range_max
        and (not needs_tract or checks["tract_coverage"] >= manifest.coverage_threshold)
        and (
            not needs_listing
            or (
                checks["listing_buffer_100m_coverage"] >= 1.0
                and checks["listing_buffer_500m_coverage"] >= 1.0
            )
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


def _raster_path() -> str:
    return f"/vsizip//vsicurl/{NLCD_TCC_ZIP_URL}/{NLCD_TCC_MEMBER}"


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


def _listing_buffers(listings_src: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    projected = listings_src.to_crs("EPSG:5070")
    buffers = gpd.GeoDataFrame(
        {
            "id": listings_src["id"].to_numpy(),
            "buffer_100m": projected.geom.buffer(100).to_crs(listings_src.crs),
            "buffer_500m": projected.geom.buffer(500).to_crs(listings_src.crs),
        },
        geometry="buffer_500m",
        crs=listings_src.crs,
    )
    return buffers


def _read_region_window(
    source: rasterio.DatasetReader,
    tracts_src: gpd.GeoDataFrame,
    listing_buffers: gpd.GeoDataFrame,
) -> tuple[np.ma.MaskedArray, Affine]:
    minx, miny, maxx, maxy = _combined_bounds(tracts_src, listing_buffers)
    window = from_bounds(minx, miny, maxx, maxy, transform=source.transform)
    window = window.round_offsets().round_lengths()
    window = _intersection_window(window, Window(0, 0, source.width, source.height))
    if window.width <= 0 or window.height <= 0:
        raise RuntimeError("NLCD TCC raster window does not intersect region bounds")
    data = source.read(
        1,
        window=window,
        masked=True,
        resampling=Resampling.nearest,
    )
    return data, source.window_transform(window)


def _combined_bounds(tracts_src: gpd.GeoDataFrame, listing_buffers: gpd.GeoDataFrame) -> tuple[float, float, float, float]:
    tract_bounds = tracts_src.total_bounds
    listing_bounds = listing_buffers.total_bounds
    return (
        float(min(tract_bounds[0], listing_bounds[0])),
        float(min(tract_bounds[1], listing_bounds[1])),
        float(max(tract_bounds[2], listing_bounds[2])),
        float(max(tract_bounds[3], listing_bounds[3])),
    )


def _compute_region_metrics(
    tracts_4326: gpd.GeoDataFrame,
    tracts_src: gpd.GeoDataFrame,
    data: np.ma.MaskedArray,
    transform: Affine,
) -> list[RegionMetric]:
    labels = np.arange(1, len(tracts_src) + 1, dtype="int32")
    label_grid = rasterize(
        zip(tracts_src.geom, labels, strict=True),
        out_shape=data.shape,
        transform=transform,
        fill=0,
        dtype="int32",
        all_touched=True,
    )
    valid = (label_grid > 0) & ~np.ma.getmaskarray(data)
    values = np.asarray(data.data, dtype="float64")
    in_range = valid & (values >= 0) & (values <= 100)
    flat_labels = label_grid[in_range]
    flat_values = values[in_range]
    sums = np.bincount(flat_labels, weights=flat_values, minlength=len(tracts_src) + 1)
    counts = np.bincount(flat_labels, minlength=len(tracts_src) + 1)
    slugs = list(tracts_4326["slug"])
    return [
        RegionMetric(region_slug=str(slug), value=float(value_sum / count))
        for slug, value_sum, count in zip(slugs, sums[1:], counts[1:], strict=True)
        if count
    ]


def _compute_listing_metrics(
    listings_4326: gpd.GeoDataFrame,
    listing_buffers: gpd.GeoDataFrame,
    data: np.ma.MaskedArray,
    transform: Affine,
) -> list[ListingMetric]:
    metrics: list[ListingMetric] = []
    for row in listing_buffers.itertuples():
        for grain in ("buffer_100m", "buffer_500m"):
            value = _array_masked_mean(data, transform, getattr(row, grain))
            if value is not None:
                metrics.append(ListingMetric(listing_id=int(row.id), grain=grain, value=value))
    expected = set(int(value) for value in listings_4326["id"])
    seen_100 = {metric.listing_id for metric in metrics if metric.grain == "buffer_100m"}
    seen_500 = {metric.listing_id for metric in metrics if metric.grain == "buffer_500m"}
    missing = (expected - seen_100) | (expected - seen_500)
    if missing:
        sample = ", ".join(str(value) for value in sorted(missing)[:5])
        raise RuntimeError(f"Missing NLCD TCC listing-buffer coverage for listing ids: {sample}")
    return metrics


def _array_masked_mean(
    data: np.ma.MaskedArray, transform: Affine, geom: BaseGeometry
) -> float | None:
    window = from_bounds(*geom.bounds, transform=transform)
    window = window.round_offsets().round_lengths()
    window = _intersection_window(window, Window(0, 0, data.shape[1], data.shape[0]))
    if window.width <= 0 or window.height <= 0:
        return None
    row0 = int(window.row_off)
    row1 = int(window.row_off + window.height)
    col0 = int(window.col_off)
    col1 = int(window.col_off + window.width)
    subset = data[row0:row1, col0:col1]
    subset_transform = transform * Affine.translation(col0, row0)
    mask = geometry_mask([geom], out_shape=subset.shape, transform=subset_transform, invert=True)
    subset_values = np.asarray(subset.data, dtype="float64")
    values = subset_values[mask & ~np.ma.getmaskarray(subset)]
    finite = values[np.isfinite(values) & (values >= 0) & (values <= 100)]
    if finite.size == 0:
        return None
    return float(finite.mean())


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
        "listing_buffer_500m_computed": int(listing_rows.get("buffer_500m", (0, 0, 0))[0]),
        "listing_buffer_500m_coverage": int(listing_rows.get("buffer_500m", (0, 0, 0))[0])
        / expected_listings
        if expected_listings
        else 0,
        "range_allowed": list(manifest.allowed_range),
        "range_min": min(mins),
        "range_max": max(maxes),
    }
