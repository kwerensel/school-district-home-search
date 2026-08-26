from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import urlretrieve
import json
import math

import geopandas as gpd
import pandas as pd
import psycopg
from shapely.geometry import Point, box

from gt.db.migrate import database_url, repo_root
from gt.manifests import LayerManifest, load_layer_manifest
from gt.reports import ValidationReport, write_report


AQS_BULK_URL = "https://aqs.epa.gov/aqsweb/airdata/daily_{parameter}_{vintage}.zip"
AQS_PARAMETERS = ("44201", "88101", "88502", "81102", "42101", "42401", "42602")
PROJECTED_CRS = "EPSG:5070"
INTERPOLATION_RADIUS_M = 30_000.0
MIN_MONITOR_DAYS = 30


@dataclass(frozen=True)
class RegionMetric:
    region_slug: str
    value: float


@dataclass(frozen=True)
class SourceStats:
    files_read: int
    files_downloaded: int
    raw_rows: int
    rows_with_aqi: int
    rows_missing_aqi: int
    invalid_rows: int
    duplicate_site_days_removed: int
    monitors_qualified: int
    monitors_below_minimum_days: int
    monitor_days_min: int
    monitor_days_max: int
    parameters_with_aqi: list[str]
    query_bbox: tuple[float, float, float, float]


def run_aqi_annual_mean(
    manifest_path: Path, region_slug: str, grain: str
) -> tuple[ValidationReport, Path]:
    manifest = load_layer_manifest(manifest_path)
    if manifest.metric_key != "aqi_annual_mean":
        raise ValueError(f"Unsupported AQS manifest metric: {manifest.metric_key}")
    if grain not in {"tract", "both"}:
        raise ValueError("aqi_annual_mean supports tract grain only")

    with psycopg.connect(database_url(), autocommit=True) as conn:
        tracts = _read_tracts(conn, region_slug)
    if tracts.empty:
        raise RuntimeError(f"No census tract regions found for {region_slug}")

    records, request_stats = _fetch_daily_aqi_bulk(
        region_slug,
        tracts,
        manifest.vintage,
    )
    monitors, monitor_stats = _annual_monitor_means(records)
    metrics, reduction_stats = _interpolate_tracts(tracts, monitors)
    source_stats = SourceStats(**request_stats, **monitor_stats)

    with psycopg.connect(database_url(), autocommit=False) as conn:
        with conn.cursor() as cur:
            _clear_staging(cur, region_slug, manifest.metric_key)
            _stage_region_metrics(cur, region_slug, manifest, metrics)
            checks = _validation_checks(
                cur,
                region_slug,
                manifest,
                source_stats,
                reduction_stats,
            )
        conn.commit()

    allowed_min, allowed_max = manifest.allowed_range
    promotable = (
        math.isfinite(checks["range_min"])
        and math.isfinite(checks["range_max"])
        and checks["range_min"] >= allowed_min
        and checks["range_max"] <= allowed_max
        and checks["nonfinite_values"] == 0
        and checks["tract_coverage"] >= manifest.coverage_threshold
        and checks["source_monitors_qualified"] > 0
        and checks["tracts_idw"] + checks["tracts_county_fallback"]
        == checks["tracts_computed"]
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
        SELECT slug, source_id, geom AS geometry
        FROM regions
        WHERE region_group = %s
          AND region_type = 'census_tract'
        ORDER BY slug
        """,
        conn,
        params=(region_slug,),
        geom_col="geometry",
    )


def _query_bbox(tracts: gpd.GeoDataFrame) -> tuple[float, float, float, float]:
    bounds = gpd.GeoSeries([box(*tracts.total_bounds)], crs="EPSG:4326")
    buffered = (
        bounds.to_crs(PROJECTED_CRS)
        .buffer(INTERPOLATION_RADIUS_M)
        .to_crs("EPSG:4326")
    )
    return tuple(float(value) for value in buffered.iloc[0].bounds)


def _fetch_daily_aqi_bulk(
    region_slug: str,
    tracts: gpd.GeoDataFrame,
    vintage: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    bbox = _query_bbox(tracts)
    cache_dir = repo_root() / "data" / "raw" / "aqs" / vintage
    cache_dir.mkdir(parents=True, exist_ok=True)
    request_payload = {
        "source": "EPA AirData daily summary bulk archives",
        "vintage": vintage,
        "bbox": list(bbox),
        "parameters": list(AQS_PARAMETERS),
        "urls": [
            AQS_BULK_URL.format(parameter=parameter, vintage=vintage)
            for parameter in AQS_PARAMETERS
        ],
    }
    request_path = cache_dir / f"{region_slug}_request.json"
    if request_path.exists() and json.loads(request_path.read_text()) != request_payload:
        raise RuntimeError(
            f"Cached AQS request differs for {region_slug}; preserve the old evidence "
            "and move the cache directory before rerunning"
        )
    request_path.write_text(json.dumps(request_payload, indent=2, sort_keys=True))

    rows: list[dict[str, Any]] = []
    files_downloaded = 0
    for parameter in AQS_PARAMETERS:
        archive = cache_dir / f"daily_{parameter}_{vintage}.zip"
        if not archive.exists():
            urlretrieve(
                AQS_BULK_URL.format(parameter=parameter, vintage=vintage),
                archive,
            )
            files_downloaded += 1
        rows.extend(_read_bulk_archive(archive, bbox))

    return rows, {
        "files_read": len(AQS_PARAMETERS),
        "files_downloaded": files_downloaded,
        "raw_rows": len(rows),
        "query_bbox": bbox,
    }


def _read_bulk_archive(
    archive: Path,
    bbox: tuple[float, float, float, float],
) -> list[dict[str, Any]]:
    usecols = [
        "State Code",
        "County Code",
        "Site Num",
        "Parameter Code",
        "Latitude",
        "Longitude",
        "Date Local",
        "AQI",
    ]
    rows: list[dict[str, Any]] = []
    for chunk in pd.read_csv(
        archive,
        compression="zip",
        usecols=usecols,
        dtype={
            "State Code": "string",
            "County Code": "string",
            "Site Num": "string",
            "Parameter Code": "string",
        },
        chunksize=100_000,
        low_memory=False,
    ):
        selected = chunk.loc[
            chunk["Latitude"].between(bbox[1], bbox[3])
            & chunk["Longitude"].between(bbox[0], bbox[2])
        ]
        for row in selected.itertuples(index=False, name=None):
            state, county, site, parameter, lat, lon, date, aqi = row
            rows.append(
                {
                    "state_code": state,
                    "county_code": county,
                    "site_number": site,
                    "parameter_code": parameter,
                    "latitude": lat,
                    "longitude": lon,
                    "date_local": date,
                    "aqi": aqi,
                }
            )
    return rows


def _annual_monitor_means(
    records: list[dict[str, Any]],
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    daily_max: dict[tuple[str, str], float] = {}
    site_details: dict[str, dict[str, Any]] = {}
    parameters_with_aqi: set[str] = set()
    rows_with_aqi = 0
    rows_missing_aqi = 0
    invalid_rows = 0
    for record in records:
        raw_aqi = record.get("aqi")
        if raw_aqi is None or pd.isna(raw_aqi):
            rows_missing_aqi += 1
            continue
        try:
            aqi = float(raw_aqi)
            lat = float(record.get("latitude"))
            lon = float(record.get("longitude"))
        except (TypeError, ValueError):
            invalid_rows += 1
            continue
        if not all(math.isfinite(value) for value in (aqi, lat, lon)):
            invalid_rows += 1
            continue
        date = str(record.get("date_local") or "")
        state = str(record.get("state_code") or "").zfill(2)
        county = str(record.get("county_code") or "").zfill(3)
        site = str(record.get("site_number") or "").zfill(4)
        if not date or not state.isdigit() or not county.isdigit() or not site.isdigit():
            invalid_rows += 1
            continue
        rows_with_aqi += 1
        site_id = f"{state}-{county}-{site}"
        key = (site_id, date)
        daily_max[key] = max(aqi, daily_max.get(key, -math.inf))
        site_details.setdefault(
            site_id,
            {
                "site_id": site_id,
                "county_fips": f"{state}{county}",
                "latitude": lat,
                "longitude": lon,
            },
        )
        parameters_with_aqi.add(str(record.get("parameter_code") or ""))

    daily_by_site: dict[str, list[float]] = {}
    for (site_id, _date), value in daily_max.items():
        daily_by_site.setdefault(site_id, []).append(value)

    monitor_rows: list[dict[str, Any]] = []
    below_minimum = 0
    for site_id, values in daily_by_site.items():
        if len(values) < MIN_MONITOR_DAYS:
            below_minimum += 1
            continue
        details = site_details[site_id]
        monitor_rows.append(
            details
            | {
                "value": float(sum(values) / len(values)),
                "days": len(values),
                "geometry": Point(details["longitude"], details["latitude"]),
            }
        )
    monitors = gpd.GeoDataFrame(monitor_rows, geometry="geometry", crs="EPSG:4326")
    day_counts = [int(row["days"]) for row in monitor_rows]
    return monitors, {
        "rows_with_aqi": rows_with_aqi,
        "rows_missing_aqi": rows_missing_aqi,
        "invalid_rows": invalid_rows,
        "duplicate_site_days_removed": rows_with_aqi - len(daily_max),
        "monitors_qualified": len(monitors),
        "monitors_below_minimum_days": below_minimum,
        "monitor_days_min": min(day_counts, default=0),
        "monitor_days_max": max(day_counts, default=0),
        "parameters_with_aqi": sorted(parameters_with_aqi),
    }


def _interpolate_tracts(
    tracts: gpd.GeoDataFrame, monitors: gpd.GeoDataFrame
) -> tuple[list[RegionMetric], dict[str, Any]]:
    if monitors.empty:
        raise RuntimeError("AQS returned no monitor sites with enough valid AQI days")
    tracts_projected = tracts.to_crs(PROJECTED_CRS)
    monitors_projected = monitors.to_crs(PROJECTED_CRS)
    county_means: dict[str, float] = {}
    for county_fips, group in monitors_projected.groupby("county_fips"):
        weight_total = float(group["days"].sum())
        if weight_total > 0:
            county_means[str(county_fips)] = float(
                (group["value"] * group["days"]).sum() / weight_total
            )

    metrics: list[RegionMetric] = []
    idw_count = 0
    county_fallback_count = 0
    missing_slugs: list[str] = []
    contributing_counts: list[int] = []
    nearest_distances: list[float] = []
    for tract in tracts_projected.itertuples():
        point = tract.geometry.representative_point()
        distances = monitors_projected.geometry.distance(point)
        within = distances <= INTERPOLATION_RADIUS_M
        value: float | None = None
        if within.any():
            selected = monitors_projected.loc[within]
            selected_distances = distances.loc[within]
            nearest = float(selected_distances.min())
            nearest_distances.append(nearest)
            contributing_counts.append(int(within.sum()))
            if nearest <= 1.0:
                value = float(selected.loc[selected_distances.idxmin(), "value"])
            else:
                weights = 1.0 / selected_distances.pow(2)
                value = float((selected["value"] * weights).sum() / weights.sum())
            idw_count += 1
        else:
            county_fips = str(tract.source_id)[:5]
            value = county_means.get(county_fips)
            if value is not None:
                county_fallback_count += 1
        if value is None or not math.isfinite(value):
            missing_slugs.append(str(tract.slug))
            continue
        metrics.append(RegionMetric(region_slug=str(tract.slug), value=value))

    return metrics, {
        "interpolation_radius_m": INTERPOLATION_RADIUS_M,
        "minimum_monitor_days": MIN_MONITOR_DAYS,
        "tracts_idw": idw_count,
        "tracts_county_fallback": county_fallback_count,
        "tracts_missing": len(missing_slugs),
        "tracts_missing_slugs": missing_slugs,
        "idw_contributing_monitors_min": min(contributing_counts, default=0),
        "idw_contributing_monitors_max": max(contributing_counts, default=0),
        "nearest_monitor_distance_max_m": max(nearest_distances, default=0.0),
        "counties_with_monitor_fallback": sorted(county_means),
    }


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
    source_stats: SourceStats,
    reduction_stats: dict[str, Any],
) -> dict[str, Any]:
    cur.execute(
        "SELECT count(*) FROM regions WHERE region_group = %s AND region_type = 'census_tract'",
        (region_slug,),
    )
    expected = int(cur.fetchone()[0])
    cur.execute(
        """
        SELECT count(*), coalesce(min(value), 0), coalesce(max(value), 0),
               count(*) FILTER (WHERE value::text IN ('NaN', 'Infinity', '-Infinity')),
               coalesce(avg(value), 0),
               coalesce(percentile_cont(0.5) WITHIN GROUP (ORDER BY value), 0)
        FROM staging.layer_region_metrics
        WHERE region_group = %s AND metric_key = %s AND vintage = %s
        """,
        (region_slug, manifest.metric_key, manifest.vintage),
    )
    count, range_min, range_max, nonfinite, mean, p50 = cur.fetchone()
    return {
        "metric_key": manifest.metric_key,
        "region": region_slug,
        "grain": "tract",
        "tracts_expected": expected,
        "tracts_computed": int(count),
        "tract_coverage": int(count) / expected if expected else 0,
        "nonfinite_values": int(nonfinite),
        "range_allowed": list(manifest.allowed_range),
        "range_min": float(range_min),
        "range_max": float(range_max),
        "value_mean": float(mean),
        "value_p50": float(p50),
        "source_files_read": source_stats.files_read,
        "source_files_downloaded": source_stats.files_downloaded,
        "source_raw_rows": source_stats.raw_rows,
        "source_rows_with_aqi": source_stats.rows_with_aqi,
        "source_rows_missing_aqi": source_stats.rows_missing_aqi,
        "source_invalid_rows": source_stats.invalid_rows,
        "source_duplicate_site_days_removed": source_stats.duplicate_site_days_removed,
        "source_monitors_qualified": source_stats.monitors_qualified,
        "source_monitors_below_minimum_days": source_stats.monitors_below_minimum_days,
        "source_monitor_days_min": source_stats.monitor_days_min,
        "source_monitor_days_max": source_stats.monitor_days_max,
        "source_parameters_with_aqi": source_stats.parameters_with_aqi,
        "query_bbox": list(source_stats.query_bbox),
        "aqs_bulk_url_pattern": AQS_BULK_URL,
    } | reduction_stats
