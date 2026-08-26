from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen, urlretrieve
import csv
import json
import math
import os
import time

import geopandas as gpd
import pandas as pd
import psycopg
from shapely.geometry import Point

from gt.db.migrate import database_url, repo_root
from gt.manifests import LayerManifest, load_layer_manifest, load_region_manifest
from gt.reports import ValidationReport, write_report


ORS_MATRIX_URL = "https://api.heigit.org/openrouteservice/v2/matrix/driving-car"
ACS_POPULATION_URL = (
    "https://www2.census.gov/programs-surveys/acs/summary_file/2024/"
    "table-based-SF/data/5YRData/acsdt5y2024-b01003.dat"
)
TIGER_BG_URL = "https://www2.census.gov/geo/tiger/TIGER2024/BG/tl_2024_{state}_bg.zip"
PROJECTED_CRS = "EPSG:5070"
ORS_BATCH_SIZE = 49
METRIC_REGIONS = {
    "commute_minutes_center_city_philadelphia": "pa-mainline",
    "commute_minutes_grand_central": "hudson-valley",
}


@dataclass(frozen=True)
class CommuteMetric:
    region_slug: str
    value: float


@dataclass(frozen=True)
class OriginStats:
    tracts_expected: int
    tracts_population_weighted: int
    tracts_point_on_surface_fallback: int
    block_groups_matched: int
    population_total: int
    acs_vintage: str


@dataclass(frozen=True)
class MatrixStats:
    batches: int
    batches_read: int
    batches_fetched: int
    retries: int
    routed: int
    unroutable: int
    unroutable_slugs: list[str]
    source_snap_distance_max_m: float
    destination_snap_distance_max_m: float
    engine_versions: list[str]
    engine_graph_dates: list[str]
    engine_osm_dates: list[str]


def run_commute_minutes(
    manifest_path: Path, region_slug: str, grain: str
) -> tuple[ValidationReport, Path]:
    manifest = load_layer_manifest(manifest_path)
    expected_region = METRIC_REGIONS.get(manifest.metric_key)
    if expected_region is None:
        raise ValueError(f"Unsupported commute manifest metric: {manifest.metric_key}")
    if region_slug != expected_region:
        raise ValueError(f"{manifest.metric_key} is approved only for {expected_region}")
    if grain not in {"tract", "both"}:
        raise ValueError(f"{manifest.metric_key} supports tract grain only")

    api_key = os.environ.get("ORS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Set ORS_API_KEY before running commute layers")

    region_manifest = load_region_manifest(
        repo_root() / "pipeline" / "manifests" / "regions" / f"{region_slug}.yaml"
    )
    if len(region_manifest.anchors) != 1:
        raise RuntimeError(f"{region_slug} must have exactly one approved fixed anchor")
    anchor = region_manifest.anchors[0]

    with psycopg.connect(database_url(), autocommit=True) as conn:
        tracts = _read_tracts(conn, region_slug)
    if tracts.empty:
        raise RuntimeError(f"No census tract regions found for {region_slug}")

    origins, origin_stats = _population_weighted_origins(
        tracts, region_manifest.state_fips[0], region_manifest.counties
    )
    metrics, matrix_stats = _fetch_matrix(
        manifest.metric_key,
        region_slug,
        origins,
        (anchor.lng, anchor.lat),
        api_key,
    )

    with psycopg.connect(database_url(), autocommit=False) as conn:
        with conn.cursor() as cur:
            _clear_staging(cur, region_slug, manifest.metric_key)
            _stage_region_metrics(cur, region_slug, manifest, metrics)
            checks = _validation_checks(
                cur,
                region_slug,
                manifest,
                origin_stats,
                matrix_stats,
                anchor.label,
                (anchor.lng, anchor.lat),
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
        and checks["routed_tracts"] + checks["unroutable_tracts"]
        == checks["tracts_expected"]
        and checks["matrix_batches"] > 0
        and bool(checks["ors_engine_graph_dates"])
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


def _population_weighted_origins(
    tracts: gpd.GeoDataFrame, state_fips: str, county_fips: list[str]
) -> tuple[gpd.GeoDataFrame, OriginStats]:
    populations = _load_block_group_populations(state_fips, county_fips)
    block_groups = _load_block_groups(state_fips, county_fips)
    block_groups = block_groups.loc[
        block_groups["GEOID"].astype(str).str[:11].isin(tracts["source_id"].astype(str))
    ].copy()
    block_groups["population"] = (
        block_groups["GEOID"].astype(str).map(populations).fillna(0).astype(int)
    )
    block_groups["tract_source_id"] = block_groups["GEOID"].astype(str).str[:11]
    representative_points = gpd.GeoSeries(
        [
            Point(float(lon), float(lat))
            for lon, lat in zip(
                block_groups["INTPTLON"], block_groups["INTPTLAT"], strict=True
            )
        ],
        crs="EPSG:4326",
    ).to_crs(PROJECTED_CRS)
    block_groups["point_x"] = representative_points.x.to_numpy()
    block_groups["point_y"] = representative_points.y.to_numpy()

    weighted_points: dict[str, Point] = {}
    total_population = 0
    for tract_source_id, group in block_groups.groupby("tract_source_id"):
        positive = group.loc[group["population"] > 0]
        population = int(positive["population"].sum())
        if population <= 0:
            continue
        x = float((positive["point_x"] * positive["population"]).sum() / population)
        y = float((positive["point_y"] * positive["population"]).sum() / population)
        weighted_points[str(tract_source_id)] = Point(x, y)
        total_population += population

    tracts_projected = tracts.to_crs(PROJECTED_CRS)
    points: list[Point] = []
    fallbacks = 0
    for row in tracts_projected.itertuples():
        point = weighted_points.get(str(row.source_id))
        if point is None:
            point = row.geometry.representative_point()
            fallbacks += 1
        points.append(point)

    origins = gpd.GeoDataFrame(
        tracts_projected[["slug", "source_id"]].copy(),
        geometry=points,
        crs=PROJECTED_CRS,
    ).to_crs("EPSG:4326")
    return origins, OriginStats(
        tracts_expected=len(tracts),
        tracts_population_weighted=len(tracts) - fallbacks,
        tracts_point_on_surface_fallback=fallbacks,
        block_groups_matched=len(block_groups),
        population_total=total_population,
        acs_vintage="2024 ACS 5-year B01003",
    )


def _load_block_group_populations(
    state_fips: str, county_fips: list[str]
) -> dict[str, int]:
    cache_dir = repo_root() / "data" / "raw" / "acs" / "2024" / "table-based-SF"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "acsdt5y2024-b01003.dat"
    if not path.exists():
        urlretrieve(ACS_POPULATION_URL, path)
    county_prefixes = set(county_fips)
    populations: dict[str, int] = {}
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="|")
        for row in reader:
            geo_id = str(row.get("GEO_ID") or "")
            if not geo_id.startswith("1500000US"):
                continue
            geoid = geo_id.rsplit("US", 1)[-1]
            if geoid[:2] != state_fips or geoid[:5] not in county_prefixes:
                continue
            raw_value = row.get("B01003_E001")
            if raw_value in {None, ""}:
                continue
            populations[geoid] = max(int(float(raw_value)), 0)
    return populations


def _load_block_groups(state_fips: str, county_fips: list[str]) -> gpd.GeoDataFrame:
    raw_dir = repo_root() / "data" / "raw" / "tiger" / "2024"
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"tl_2024_{state_fips}_bg.zip"
    if not path.exists():
        urlretrieve(TIGER_BG_URL.format(state=state_fips), path)
    frame = gpd.read_file(path)
    counties = {value[2:] for value in county_fips}
    return frame.loc[
        frame["COUNTYFP"].astype(str).isin(counties),
        ["GEOID", "INTPTLAT", "INTPTLON"],
    ].copy()


def _fetch_matrix(
    metric_key: str,
    region_slug: str,
    origins: gpd.GeoDataFrame,
    anchor: tuple[float, float],
    api_key: str,
) -> tuple[list[CommuteMetric], MatrixStats]:
    cache_dir = repo_root() / "data" / "raw" / "openrouteservice" / metric_key / region_slug
    cache_dir.mkdir(parents=True, exist_ok=True)
    metrics: list[CommuteMetric] = []
    batches_read = 0
    batches_fetched = 0
    retries = 0
    unroutable = 0
    unroutable_slugs: list[str] = []
    source_snap_distances: list[float] = []
    destination_snap_distances: list[float] = []
    engine_versions: set[str] = set()
    graph_dates: set[str] = set()
    osm_dates: set[str] = set()

    batches = [
        origins.iloc[start : start + ORS_BATCH_SIZE]
        for start in range(0, len(origins), ORS_BATCH_SIZE)
    ]
    for batch_number, batch in enumerate(batches, start=1):
        source_locations = [
            [float(point.x), float(point.y)] for point in batch.geometry
        ]
        request_payload = {
            "locations": source_locations + [[float(anchor[0]), float(anchor[1])]],
            "sources": [str(index) for index in range(len(source_locations))],
            "destinations": [str(len(source_locations))],
            "metrics": ["duration"],
        }
        request_path = cache_dir / f"batch_{batch_number:03d}_request.json"
        response_path = cache_dir / f"batch_{batch_number:03d}_response.json"
        if request_path.exists() and json.loads(request_path.read_text()) != request_payload:
            raise RuntimeError(
                f"Cached ORS request differs for batch {batch_number}; preserve the old evidence "
                "and move the cache directory before rerunning"
            )
        request_path.write_text(json.dumps(request_payload, indent=2, sort_keys=True))
        batches_read += 1
        if response_path.exists():
            response_payload = json.loads(response_path.read_text())
        else:
            response_payload, batch_retries = _request_matrix(request_payload, api_key)
            response_path.write_text(json.dumps(response_payload, indent=2, sort_keys=True))
            batches_fetched += 1
            retries += batch_retries

        durations = _matrix_durations(response_payload, len(batch))
        for slug, duration_seconds in zip(batch["slug"], durations, strict=True):
            if duration_seconds is None:
                unroutable += 1
                unroutable_slugs.append(str(slug))
                continue
            metrics.append(
                CommuteMetric(region_slug=str(slug), value=float(duration_seconds) / 60.0)
            )

        for source in response_payload.get("sources") or []:
            distance = source.get("snapped_distance")
            if isinstance(distance, (int, float)):
                source_snap_distances.append(float(distance))
        for destination in response_payload.get("destinations") or []:
            distance = destination.get("snapped_distance")
            if isinstance(distance, (int, float)):
                destination_snap_distances.append(float(distance))
        engine = ((response_payload.get("metadata") or {}).get("engine") or {})
        if engine.get("version"):
            engine_versions.add(str(engine["version"]))
        if engine.get("graph_date"):
            graph_dates.add(str(engine["graph_date"]))
        if engine.get("osm_date"):
            osm_dates.add(str(engine["osm_date"]))

    return metrics, MatrixStats(
        batches=len(batches),
        batches_read=batches_read,
        batches_fetched=batches_fetched,
        retries=retries,
        routed=len(metrics),
        unroutable=unroutable,
        unroutable_slugs=unroutable_slugs,
        source_snap_distance_max_m=max(source_snap_distances, default=0.0),
        destination_snap_distance_max_m=max(destination_snap_distances, default=0.0),
        engine_versions=sorted(engine_versions),
        engine_graph_dates=sorted(graph_dates),
        engine_osm_dates=sorted(osm_dates),
    )


def _request_matrix(payload: dict[str, Any], api_key: str) -> tuple[dict[str, Any], int]:
    body = json.dumps(payload).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(8):
        try:
            request = Request(
                ORS_MATRIX_URL,
                data=body,
                headers={
                    "Authorization": api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "Groundtruth fixed-anchor commute ingestion",
                },
                method="POST",
            )
            with urlopen(request, timeout=180) as response:
                return json.load(response), attempt
        except HTTPError as exc:
            last_error = exc
            if exc.code != 429 and not 500 <= exc.code < 600:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                raise RuntimeError(
                    f"ORS matrix request failed with HTTP {exc.code}: {detail}"
                ) from exc
            retry_after = exc.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else 1.5 * (attempt + 1)
            time.sleep(min(delay, 30))
        except Exception as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def _matrix_durations(payload: dict[str, Any], expected: int) -> list[float | None]:
    rows = payload.get("durations")
    if not isinstance(rows, list) or len(rows) != expected:
        returned = len(rows) if isinstance(rows, list) else 0
        raise RuntimeError(
            f"ORS matrix returned {returned} rows; expected {expected}"
        )
    durations: list[float | None] = []
    for row in rows:
        if not isinstance(row, list) or len(row) != 1:
            raise RuntimeError("ORS matrix response must contain one destination per source")
        value = row[0]
        durations.append(float(value) if isinstance(value, (int, float)) else None)
    return durations


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
    metrics: list[CommuteMetric],
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
    origin_stats: OriginStats,
    matrix_stats: MatrixStats,
    anchor_label: str,
    anchor: tuple[float, float],
) -> dict[str, Any]:
    cur.execute(
        """
        SELECT count(*), coalesce(min(value), 0), coalesce(max(value), 0),
               count(*) FILTER (WHERE value::text IN ('NaN', 'Infinity', '-Infinity')),
               coalesce(avg(value), 0),
               coalesce(percentile_cont(0.5) WITHIN GROUP (ORDER BY value), 0),
               coalesce(percentile_cont(0.9) WITHIN GROUP (ORDER BY value), 0)
        FROM staging.layer_region_metrics
        WHERE region_group = %s AND metric_key = %s AND vintage = %s
        """,
        (region_slug, manifest.metric_key, manifest.vintage),
    )
    count, range_min, range_max, nonfinite, mean, p50, p90 = cur.fetchone()
    return {
        "metric_key": manifest.metric_key,
        "region": region_slug,
        "grain": "tract",
        "anchor_label": anchor_label,
        "anchor_lon_lat": list(anchor),
        "tracts_expected": origin_stats.tracts_expected,
        "tracts_computed": int(count),
        "tract_coverage": (
            int(count) / origin_stats.tracts_expected
            if origin_stats.tracts_expected
            else 0
        ),
        "nonfinite_values": int(nonfinite),
        "range_allowed": list(manifest.allowed_range),
        "range_min": float(range_min),
        "range_max": float(range_max),
        "duration_mean_min": float(mean),
        "duration_p50_min": float(p50),
        "duration_p90_min": float(p90),
        "origin_method": "ACS block-group-population-weighted TIGER representative points",
        "origin_acs_vintage": origin_stats.acs_vintage,
        "origin_tracts_population_weighted": origin_stats.tracts_population_weighted,
        "origin_tracts_point_on_surface_fallback": origin_stats.tracts_point_on_surface_fallback,
        "origin_block_groups_matched": origin_stats.block_groups_matched,
        "origin_population_total": origin_stats.population_total,
        "matrix_batches": matrix_stats.batches,
        "matrix_batches_read": matrix_stats.batches_read,
        "matrix_batches_fetched": matrix_stats.batches_fetched,
        "matrix_retries": matrix_stats.retries,
        "routed_tracts": matrix_stats.routed,
        "unroutable_tracts": matrix_stats.unroutable,
        "unroutable_tract_slugs": matrix_stats.unroutable_slugs,
        "source_snap_distance_max_m": matrix_stats.source_snap_distance_max_m,
        "destination_snap_distance_max_m": matrix_stats.destination_snap_distance_max_m,
        "ors_engine_versions": matrix_stats.engine_versions,
        "ors_engine_graph_dates": matrix_stats.engine_graph_dates,
        "ors_engine_osm_dates": matrix_stats.engine_osm_dates,
        "ors_endpoint": ORS_MATRIX_URL,
    }
