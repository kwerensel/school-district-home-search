from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any
from urllib.request import urlretrieve

from affine import Affine
import geopandas as gpd
import mercantile
import numpy as np
import psycopg
import rasterio
from rasterio.features import geometry_mask, rasterize
from rasterio.transform import rowcol
from rasterio.windows import Window, from_bounds
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from gt.db.migrate import database_url, repo_root
from gt.manifests import LayerManifest, load_layer_manifest
from gt.reports import ValidationReport, write_report


SERVICE_URL = (
    "https://tiles.arcgis.com/tiles/xOi1kZaI0eWDREZv/arcgis/rest/services/"
    "NTAD_Noise_2022_CONUS_aviation_rail_road/MapServer"
)
TILE_URL = f"{SERVICE_URL}/tile/{{z}}/{{y}}/{{x}}"
ZOOM = 12
TILE_SIZE = 256
WEB_MERCATOR_HALF_WORLD = 20_037_508.342789244
WEB_MERCATOR_RESOLUTION = 156_543.03392804097 / (2**ZOOM)

# The official BTS tiled service exposes seven modeled LAeq classes. Index 0
# is transparent and therefore below the published 45 dBA modeling floor.
CLASS_COLORS = {
    0: (253, 253, 253, 0),
    1: (255, 193, 7, 255),
    2: (255, 128, 0, 255),
    3: (255, 0, 0, 255),
    4: (255, 51, 153, 255),
    5: (163, 0, 204, 255),
    6: (82, 0, 204, 255),
    7: (0, 0, 255, 255),
}
CLASS_LABELS = {
    0: "<45.0",
    1: "45.0-49.9",
    2: "50.0-54.9",
    3: "55.0-59.9",
    4: "60.0-69.9",
    5: "70.0-79.9",
    6: "80.0-89.9",
    7: ">=90.0",
}
# Preserve the source's categorical precision. Below-floor pixels use the
# published 45 dBA floor rather than an invented sub-45 estimate.
CLASS_MIDPOINT_DBA = np.array(
    [45.0, 47.45, 52.45, 57.45, 64.95, 74.95, 84.95, 92.5],
    dtype="float64",
)
SUPPORTED_METRICS = {
    "noise_mean_dba",
    "noise_pct_over_45",
    "noise_pct_over_55",
}


@dataclass(frozen=True)
class RegionMetric:
    region_slug: str
    value: float


@dataclass(frozen=True)
class ListingMetric:
    listing_id: int
    grain: str
    value: float


@dataclass(frozen=True)
class SourceStats:
    service_url: str
    zoom: int
    resolution_m: float
    tiles: int
    tile_x_min: int
    tile_x_max: int
    tile_y_min: int
    tile_y_max: int
    pixels: int
    class_pixel_counts: dict[str, int]


def run_noise(
    manifest_path: Path, region_slug: str, grain: str
) -> tuple[ValidationReport, Path]:
    manifest = load_layer_manifest(manifest_path)
    if manifest.metric_key not in SUPPORTED_METRICS:
        raise ValueError(f"Unsupported BTS noise metric: {manifest.metric_key}")
    if grain not in {"tract", "listing", "both"}:
        raise ValueError("grain must be tract, listing, or both")

    with psycopg.connect(database_url(), autocommit=True) as conn:
        tracts = _read_tracts(conn, region_slug)
        listings = _read_listings(conn, region_slug)
    if tracts.empty:
        raise RuntimeError(f"No census tract regions found for {region_slug}")
    if listings.empty:
        raise RuntimeError(f"No frozen listings found for {region_slug}")

    tracts_3857 = tracts.to_crs("EPSG:3857")
    listings_3857 = listings.to_crs("EPSG:3857")
    listing_buffers = _listing_buffers(listings_3857)
    categories, transform, source_stats = _load_region_categories(
        region_slug, tracts_3857, listing_buffers
    )
    values = _metric_values(categories, manifest.metric_key)

    region_metrics: list[RegionMetric] = []
    listing_metrics: list[ListingMetric] = []
    if grain in {"tract", "both"}:
        region_metrics = _compute_region_metrics(tracts, tracts_3857, values, transform)
    if grain in {"listing", "both"}:
        listing_metrics = _compute_listing_metrics(
            listings, listings_3857, listing_buffers, values, transform
        )

    with psycopg.connect(database_url(), autocommit=False) as conn:
        with conn.cursor() as cur:
            _clear_staging(cur, region_slug, manifest.metric_key)
            _stage_region_metrics(cur, region_slug, manifest, region_metrics)
            _stage_listing_metrics(cur, region_slug, manifest, listing_metrics)
            checks = _validation_checks(
                cur, region_slug, manifest, grain, source_stats
            )
        conn.commit()

    allowed_min, allowed_max = manifest.allowed_range
    needs_tract = grain in {"tract", "both"}
    needs_listing = grain in {"listing", "both"}
    promotable = (
        math.isfinite(checks["range_min"])
        and math.isfinite(checks["range_max"])
        and checks["range_min"] >= allowed_min
        and checks["range_max"] <= allowed_max
        and checks["nonfinite_values"] == 0
        and (not needs_tract or checks["tract_coverage"] >= manifest.coverage_threshold)
        and (
            not needs_listing
            or checks["listing_point_coverage"] >= 1.0
            and checks["listing_buffer_100m_coverage"] >= 1.0
        )
        and checks["source_tiles"] > 0
        and checks["source_pixels_at_or_above_45"] > 0
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
        SELECT id, slug, geom AS geometry
        FROM regions
        WHERE region_group = %s
          AND region_type = 'census_tract'
        ORDER BY slug
        """,
        conn,
        params=(region_slug,),
        geom_col="geometry",
    )


def _read_listings(conn: psycopg.Connection[Any], region_slug: str) -> gpd.GeoDataFrame:
    return gpd.read_postgis(
        """
        SELECT id, geom AS geometry
        FROM listings
        WHERE region_slug = %s
        ORDER BY id
        """,
        conn,
        params=(region_slug,),
        geom_col="geometry",
    )


def _listing_buffers(listings_3857: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "id": listings_3857["id"].to_numpy(),
            "geometry": listings_3857.geometry.buffer(100),
        },
        geometry="geometry",
        crs="EPSG:3857",
    )


def _load_region_categories(
    region_slug: str,
    tracts_3857: gpd.GeoDataFrame,
    listing_buffers: gpd.GeoDataFrame,
) -> tuple[np.ndarray, Affine, SourceStats]:
    combined_bounds = _combined_bounds(tracts_3857, listing_buffers)
    bounds_4326 = gpd.GeoSeries(
        [box(*combined_bounds)], crs="EPSG:3857"
    ).to_crs("EPSG:4326").total_bounds
    tiles = list(mercantile.tiles(*bounds_4326, zooms=[ZOOM]))
    if not tiles:
        raise RuntimeError(f"No BTS tiles intersect {region_slug}")

    cache_dir = repo_root() / "data" / "raw" / "bts" / "2022" / f"z{ZOOM}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        paths = list(pool.map(lambda tile: _cache_tile(cache_dir, tile), tiles))

    min_x = min(tile.x for tile in tiles)
    max_x = max(tile.x for tile in tiles)
    min_y = min(tile.y for tile in tiles)
    max_y = max(tile.y for tile in tiles)
    categories = np.zeros(
        ((max_y - min_y + 1) * TILE_SIZE, (max_x - min_x + 1) * TILE_SIZE),
        dtype="uint8",
    )
    for tile, path in zip(tiles, paths, strict=True):
        data = _read_category_tile(path)
        row = (tile.y - min_y) * TILE_SIZE
        col = (tile.x - min_x) * TILE_SIZE
        categories[row : row + TILE_SIZE, col : col + TILE_SIZE] = data

    left = -WEB_MERCATOR_HALF_WORLD + min_x * TILE_SIZE * WEB_MERCATOR_RESOLUTION
    top = WEB_MERCATOR_HALF_WORLD - min_y * TILE_SIZE * WEB_MERCATOR_RESOLUTION
    transform = Affine(
        WEB_MERCATOR_RESOLUTION,
        0,
        left,
        0,
        -WEB_MERCATOR_RESOLUTION,
        top,
    )
    unique, counts = np.unique(categories, return_counts=True)
    class_counts = {CLASS_LABELS[int(key)]: int(value) for key, value in zip(unique, counts)}
    stats = SourceStats(
        service_url=SERVICE_URL,
        zoom=ZOOM,
        resolution_m=WEB_MERCATOR_RESOLUTION,
        tiles=len(tiles),
        tile_x_min=min_x,
        tile_x_max=max_x,
        tile_y_min=min_y,
        tile_y_max=max_y,
        pixels=int(categories.size),
        class_pixel_counts=class_counts,
    )
    metadata = {
        "source": "BTS National Transportation Noise Map tiled service",
        "service_url": SERVICE_URL,
        "tile_url_template": TILE_URL,
        "region": region_slug,
        "zoom": ZOOM,
        "resolution_m": WEB_MERCATOR_RESOLUTION,
        "tile_range": {"x": [min_x, max_x], "y": [min_y, max_y]},
        "tiles": len(tiles),
        "class_labels": CLASS_LABELS,
        "class_midpoint_dba": CLASS_MIDPOINT_DBA.tolist(),
    }
    metadata_path = cache_dir.parent / f"{region_slug}_request.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True))
    return categories, transform, stats


def _combined_bounds(
    tracts_3857: gpd.GeoDataFrame, listing_buffers: gpd.GeoDataFrame
) -> tuple[float, float, float, float]:
    tract_bounds = tracts_3857.total_bounds
    listing_bounds = listing_buffers.total_bounds
    return (
        float(min(tract_bounds[0], listing_bounds[0])),
        float(min(tract_bounds[1], listing_bounds[1])),
        float(max(tract_bounds[2], listing_bounds[2])),
        float(max(tract_bounds[3], listing_bounds[3])),
    )


def _cache_tile(cache_dir: Path, tile: mercantile.Tile) -> Path:
    path = cache_dir / str(tile.x) / f"{tile.y}.png"
    if path.exists() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".download")
    urlretrieve(TILE_URL.format(z=tile.z, y=tile.y, x=tile.x), temporary)
    temporary.replace(path)
    return path


def _read_category_tile(path: Path) -> np.ndarray:
    with rasterio.open(path) as source:
        palette_indexes = source.read(1)
        if palette_indexes.shape != (TILE_SIZE, TILE_SIZE):
            raise RuntimeError(
                f"Unexpected BTS tile shape at {path}: {palette_indexes.shape}"
            )
        color_map = source.colormap(1)
        class_by_color = {color: index for index, color in CLASS_COLORS.items()}
        categories = np.zeros(palette_indexes.shape, dtype="uint8")
        for palette_index in np.unique(palette_indexes):
            color = tuple(color_map[int(palette_index)])
            class_index = class_by_color.get(color)
            if class_index is None:
                raise RuntimeError(
                    f"Unexpected BTS color at {path}: palette index "
                    f"{int(palette_index)} is {color}"
                )
            categories[palette_indexes == palette_index] = class_index
    return categories


def _metric_values(categories: np.ndarray, metric_key: str) -> np.ndarray:
    if metric_key == "noise_mean_dba":
        return CLASS_MIDPOINT_DBA[categories]
    if metric_key == "noise_pct_over_45":
        return (categories >= 1).astype("float64") * 100.0
    if metric_key == "noise_pct_over_55":
        return (categories >= 3).astype("float64") * 100.0
    raise ValueError(f"Unsupported BTS noise metric: {metric_key}")


def _compute_region_metrics(
    tracts_4326: gpd.GeoDataFrame,
    tracts_3857: gpd.GeoDataFrame,
    values: np.ndarray,
    transform: Affine,
) -> list[RegionMetric]:
    labels = np.arange(1, len(tracts_3857) + 1, dtype="int32")
    label_grid = rasterize(
        zip(tracts_3857.geometry, labels, strict=True),
        out_shape=values.shape,
        transform=transform,
        fill=0,
        dtype="int32",
        all_touched=True,
    )
    valid = (label_grid > 0) & np.isfinite(values)
    flat_labels = label_grid[valid]
    flat_values = values[valid]
    sums = np.bincount(flat_labels, weights=flat_values, minlength=len(tracts_3857) + 1)
    counts = np.bincount(flat_labels, minlength=len(tracts_3857) + 1)
    metrics: list[RegionMetric] = []
    for slug, value_sum, count in zip(
        tracts_4326["slug"], sums[1:], counts[1:], strict=True
    ):
        if count:
            metrics.append(RegionMetric(str(slug), float(value_sum / count)))
    return metrics


def _compute_listing_metrics(
    listings_4326: gpd.GeoDataFrame,
    listings_3857: gpd.GeoDataFrame,
    listing_buffers: gpd.GeoDataFrame,
    values: np.ndarray,
    transform: Affine,
) -> list[ListingMetric]:
    metrics: list[ListingMetric] = []
    for listing_id, geom in zip(
        listings_3857["id"], listings_3857.geometry, strict=True
    ):
        row, col = rowcol(transform, geom.x, geom.y)
        if 0 <= row < values.shape[0] and 0 <= col < values.shape[1]:
            metrics.append(ListingMetric(int(listing_id), "point", float(values[row, col])))
    for listing_id, geom in zip(
        listing_buffers["id"], listing_buffers.geometry, strict=True
    ):
        value = _array_masked_mean(values, transform, geom)
        if value is not None:
            metrics.append(ListingMetric(int(listing_id), "buffer_100m", value))

    expected = set(int(value) for value in listings_4326["id"])
    for expected_grain in ("point", "buffer_100m"):
        seen = {
            metric.listing_id for metric in metrics if metric.grain == expected_grain
        }
        missing = expected - seen
        if missing:
            sample = ", ".join(str(value) for value in sorted(missing)[:5])
            raise RuntimeError(
                f"Missing BTS {expected_grain} coverage for listing ids: {sample}"
            )
    return metrics


def _array_masked_mean(
    values: np.ndarray, transform: Affine, geom: BaseGeometry
) -> float | None:
    window = from_bounds(*geom.bounds, transform=transform)
    window = window.round_offsets().round_lengths()
    window = _intersection_window(
        window, Window(0, 0, values.shape[1], values.shape[0])
    )
    if window.width <= 0 or window.height <= 0:
        return None
    row0 = int(window.row_off)
    row1 = int(window.row_off + window.height)
    col0 = int(window.col_off)
    col1 = int(window.col_off + window.width)
    subset = values[row0:row1, col0:col1]
    subset_transform = transform * Affine.translation(col0, row0)
    mask = geometry_mask(
        [geom], out_shape=subset.shape, transform=subset_transform, invert=True
    )
    selected = subset[mask & np.isfinite(subset)]
    if selected.size == 0:
        return None
    return float(selected.mean())


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
    cur: psycopg.Cursor[Any],
    region_slug: str,
    manifest: LayerManifest,
    grain: str,
    source_stats: SourceStats,
) -> dict[str, Any]:
    cur.execute(
        """
        SELECT count(*) FROM regions
        WHERE region_group = %s AND region_type = 'census_tract'
        """,
        (region_slug,),
    )
    expected_tracts = int(cur.fetchone()[0])
    cur.execute("SELECT count(*) FROM listings WHERE region_slug = %s", (region_slug,))
    expected_listings = int(cur.fetchone()[0])
    cur.execute(
        """
        SELECT count(*), min(value), max(value),
               count(*) FILTER (
                 WHERE value::text IN ('NaN', 'Infinity', '-Infinity')
               )
        FROM staging.layer_region_metrics
        WHERE region_group = %s AND metric_key = %s AND vintage = %s
        """,
        (region_slug, manifest.metric_key, manifest.vintage),
    )
    tract_count, region_min, region_max, region_nonfinite = cur.fetchone()
    cur.execute(
        """
        SELECT grain, count(*), min(value), max(value),
               count(*) FILTER (
                 WHERE value::text IN ('NaN', 'Infinity', '-Infinity')
               )
        FROM staging.layer_listing_metrics
        WHERE region_group = %s AND metric_key = %s AND vintage = %s
        GROUP BY grain
        """,
        (region_slug, manifest.metric_key, manifest.vintage),
    )
    listing_rows = {row[0]: row[1:] for row in cur.fetchall()}
    mins = [float(value) for value in [region_min] if value is not None]
    maxes = [float(value) for value in [region_max] if value is not None]
    for _, min_value, max_value, _ in listing_rows.values():
        if min_value is not None:
            mins.append(float(min_value))
        if max_value is not None:
            maxes.append(float(max_value))
    nonfinite = int(region_nonfinite or 0) + sum(
        int(row[3] or 0) for row in listing_rows.values()
    )
    point_count = int(listing_rows.get("point", (0, None, None, 0))[0])
    buffer_count = int(listing_rows.get("buffer_100m", (0, None, None, 0))[0])
    pixels_at_or_above_45 = sum(
        count
        for label, count in source_stats.class_pixel_counts.items()
        if label != "<45.0"
    )
    return {
        "metric_key": manifest.metric_key,
        "region": region_slug,
        "grain": grain,
        "tracts_expected": expected_tracts,
        "tracts_computed": int(tract_count),
        "tract_coverage": int(tract_count) / expected_tracts if expected_tracts else 0,
        "listings_expected": expected_listings,
        "listing_point_computed": point_count,
        "listing_point_coverage": point_count / expected_listings if expected_listings else 0,
        "listing_buffer_100m_computed": buffer_count,
        "listing_buffer_100m_coverage": buffer_count / expected_listings
        if expected_listings
        else 0,
        "nonfinite_values": nonfinite,
        "range_allowed": list(manifest.allowed_range),
        "range_min": min(mins, default=math.nan),
        "range_max": max(maxes, default=math.nan),
        "source_service_url": source_stats.service_url,
        "source_zoom": source_stats.zoom,
        "source_resolution_m": source_stats.resolution_m,
        "source_tiles": source_stats.tiles,
        "source_tile_x_range": [source_stats.tile_x_min, source_stats.tile_x_max],
        "source_tile_y_range": [source_stats.tile_y_min, source_stats.tile_y_max],
        "source_pixels": source_stats.pixels,
        "source_class_pixel_counts": source_stats.class_pixel_counts,
        "source_pixels_at_or_above_45": pixels_at_or_above_45,
    }
