from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import psycopg
import rasterio
from affine import Affine
from rasterio.features import rasterize
from rasterio.windows import Window, from_bounds

from gt.db.migrate import database_url, repo_root
from gt.manifests import LayerManifest, load_layer_manifest
from gt.reports import ValidationReport, write_report

EOG_FILENAME = "VNL_npp_2025_global_vcmslcfg_v2_c202604011200.median_masked.dat.tif.gz"


@dataclass(frozen=True)
class RegionMetric:
    region_slug: str
    value: float


@dataclass(frozen=True)
class SourceStats:
    path: str
    crs: str
    width: int
    height: int
    nodata: float | None
    window_width: int
    window_height: int
    valid_pixels: int
    range_min: float
    range_mean: float
    range_p50: float
    range_p90: float
    range_max: float


def run_light_pollution(
    manifest_path: Path, region_slug: str, grain: str
) -> tuple[ValidationReport, Path]:
    manifest = load_layer_manifest(manifest_path)
    if manifest.metric_key != "light_pollution_radiance":
        raise ValueError(f"Unsupported light pollution manifest metric: {manifest.metric_key}")
    if grain not in {"tract", "both"}:
        raise ValueError("light_pollution_radiance supports tract grain only")

    raster_path = _raster_path()
    with psycopg.connect(database_url(), autocommit=False) as conn:
        tracts = _read_tracts(conn, region_slug)
        if tracts.empty:
            raise RuntimeError(f"No census tract regions found for {region_slug}")

        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
            with rasterio.open(f"gzip://{raster_path}") as source:
                if not source.crs:
                    raise RuntimeError("EOG VNL raster is missing CRS metadata")
                if source.crs.to_epsg() != 4326:
                    raise RuntimeError(f"Unexpected EOG VNL raster CRS: {source.crs}")
                tracts_src = tracts.to_crs(source.crs)
                data, transform = _read_region_window(source, tracts_src)
                metrics = _compute_region_metrics(tracts, tracts_src, data, transform, manifest)
                source_stats = _source_stats(raster_path, source, data, manifest)

        with conn.cursor() as cur:
            _clear_staging(cur, region_slug, manifest.metric_key)
            _stage_region_metrics(cur, region_slug, manifest, metrics)
            checks = _validation_checks(cur, region_slug, manifest, grain, source_stats)
        conn.commit()

    range_min, range_max = manifest.allowed_range
    promotable = (
        checks["range_min"] >= range_min
        and checks["range_max"] <= range_max
        and checks["tract_coverage"] >= manifest.coverage_threshold
        and checks["source_valid_pixels"] > 0
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


def _raster_path() -> Path:
    path = repo_root() / "data" / "raw" / "eog" / EOG_FILENAME
    if not path.exists():
        raise RuntimeError(f"Missing EOG VNL raster: {path}")
    return path


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


def _read_region_window(
    source: rasterio.DatasetReader, tracts_src: gpd.GeoDataFrame
) -> tuple[np.ma.MaskedArray, Affine]:
    minx, miny, maxx, maxy = tracts_src.total_bounds
    window = from_bounds(minx, miny, maxx, maxy, transform=source.transform)
    window = window.round_offsets().round_lengths()
    window = _intersection_window(window, Window(0, 0, source.width, source.height))
    if window.width <= 0 or window.height <= 0:
        raise RuntimeError("EOG VNL raster window does not intersect region bounds")
    data = source.read(1, window=window, masked=True)
    return data, source.window_transform(window)


def _compute_region_metrics(
    tracts_4326: gpd.GeoDataFrame,
    tracts_src: gpd.GeoDataFrame,
    data: np.ma.MaskedArray,
    transform: Affine,
    manifest: LayerManifest,
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
    range_min, range_max = manifest.allowed_range
    values = np.asarray(data.data, dtype="float64")
    valid = (
        (label_grid > 0)
        & ~np.ma.getmaskarray(data)
        & np.isfinite(values)
        & (values >= range_min)
        & (values <= range_max)
    )
    flat_labels = label_grid[valid]
    flat_values = values[valid]
    sums = np.bincount(flat_labels, weights=flat_values, minlength=len(tracts_src) + 1)
    counts = np.bincount(flat_labels, minlength=len(tracts_src) + 1)
    slugs = list(tracts_4326["slug"])
    return [
        RegionMetric(region_slug=str(slug), value=float(value_sum / count))
        for slug, value_sum, count in zip(slugs, sums[1:], counts[1:], strict=True)
        if count
    ]


def _source_stats(
    raster_path: Path,
    source: rasterio.DatasetReader,
    data: np.ma.MaskedArray,
    manifest: LayerManifest,
) -> SourceStats:
    range_min, range_max = manifest.allowed_range
    values = np.asarray(data.data, dtype="float64")
    valid = values[
        ~np.ma.getmaskarray(data)
        & np.isfinite(values)
        & (values >= range_min)
        & (values <= range_max)
    ]
    if valid.size == 0:
        raise RuntimeError("EOG VNL region window has no valid pixels")
    return SourceStats(
        path=str(raster_path),
        crs=str(source.crs),
        width=int(source.width),
        height=int(source.height),
        nodata=None if source.nodata is None else float(source.nodata),
        window_width=int(data.shape[1]),
        window_height=int(data.shape[0]),
        valid_pixels=int(valid.size),
        range_min=float(valid.min()),
        range_mean=float(valid.mean()),
        range_p50=float(np.percentile(valid, 50)),
        range_p90=float(np.percentile(valid, 90)),
        range_max=float(valid.max()),
    )


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


def _validation_checks(
    cur: psycopg.Cursor[Any],
    region_slug: str,
    manifest: LayerManifest,
    grain: str,
    source_stats: SourceStats,
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
    tract_count, range_min, range_max = cur.fetchone()
    return {
        "metric_key": manifest.metric_key,
        "region": region_slug,
        "grain": grain,
        "tracts_expected": expected_tracts,
        "tracts_computed": int(tract_count),
        "tract_coverage": int(tract_count) / expected_tracts if expected_tracts else 0,
        "listings_expected": expected_listings,
        "listing_point_computed": 0,
        "listing_point_coverage": 0,
        "listing_buffer_100m_computed": 0,
        "listing_buffer_100m_coverage": 0,
        "listing_buffer_500m_computed": 0,
        "listing_buffer_500m_coverage": 0,
        "range_allowed": list(manifest.allowed_range),
        "range_min": float(range_min),
        "range_max": float(range_max),
        "source_path": source_stats.path,
        "source_crs": source_stats.crs,
        "source_width": source_stats.width,
        "source_height": source_stats.height,
        "source_nodata": source_stats.nodata,
        "source_window_width": source_stats.window_width,
        "source_window_height": source_stats.window_height,
        "source_valid_pixels": source_stats.valid_pixels,
        "source_sample_min": source_stats.range_min,
        "source_sample_mean": source_stats.range_mean,
        "source_sample_p50": source_stats.range_p50,
        "source_sample_p90": source_stats.range_p90,
        "source_sample_max": source_stats.range_max,
    }
