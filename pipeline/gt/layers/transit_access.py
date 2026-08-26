from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import math
import os
import time

import geopandas as gpd
import pandas as pd
import psycopg
from shapely.geometry import Point, box

from gt.db.migrate import database_url, repo_root
from gt.manifests import LayerManifest, load_layer_manifest
from gt.reports import ValidationReport, write_report


TRANSITLAND_STOPS_URL = "https://transit.land/api/v2/rest/stops"
METRIC_KEYS = {"transit_access", "transit_distance_m"}
PROJECTED_CRS = "EPSG:5070"
QUERY_BUFFER_M = 10_000.0
PAGE_LIMIT = 1_000


@dataclass(frozen=True)
class RegionMetric:
    region_slug: str
    value: float


@dataclass(frozen=True)
class ListingMetric:
    listing_id: int
    value: float


@dataclass(frozen=True)
class TransitlandStats:
    pages_read: int
    pages_fetched: int
    page_retries: int
    raw_stop_records: int
    unique_stops: int
    duplicate_stops_removed: int
    invalid_stop_geometries: int
    feed_versions: dict[str, dict[str, str]]
    query_bbox: tuple[float, float, float, float]


def run_transit_access(
    manifest_path: Path, region_slug: str, grain: str
) -> tuple[ValidationReport, Path]:
    manifest = load_layer_manifest(manifest_path)
    if manifest.metric_key not in METRIC_KEYS:
        raise ValueError(f"Unsupported transit manifest metric: {manifest.metric_key}")
    if grain not in {"tract", "listing", "both"}:
        raise ValueError("grain must be tract, listing, or both")

    compute_tract = manifest.metric_key == "transit_access" and grain in {"tract", "both"}
    compute_listing = manifest.metric_key == "transit_distance_m" and grain in {
        "listing",
        "both",
    }
    if not compute_tract and not compute_listing:
        supported = "tract" if manifest.metric_key == "transit_access" else "listing"
        raise ValueError(f"{manifest.metric_key} supports {supported} grain only")

    api_key = os.environ.get("TRANSITLAND_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Set TRANSITLAND_API_KEY before running Transitland layers")

    with psycopg.connect(database_url(), autocommit=True) as conn:
        tracts = _read_tracts(conn, region_slug)
        listings = _read_listings(conn, region_slug)
    if tracts.empty:
        raise RuntimeError(f"No census tract regions found for {region_slug}")
    if listings.empty:
        raise RuntimeError(f"No frozen listings found for {region_slug}")

    stops, source_stats = _fetch_stops(region_slug, tracts, api_key)
    if stops.empty:
        raise RuntimeError(f"Transitland returned no valid active-feed stops for {region_slug}")

    region_metrics: list[RegionMetric] = []
    listing_metrics: list[ListingMetric] = []
    reduction_stats: dict[str, Any]
    if compute_tract:
        region_metrics, reduction_stats = _compute_region_metrics(tracts, stops)
    else:
        listing_metrics, reduction_stats = _compute_listing_metrics(listings, stops)

    with psycopg.connect(database_url(), autocommit=False) as conn:
        with conn.cursor() as cur:
            _clear_staging(cur, region_slug, manifest.metric_key)
            _stage_region_metrics(cur, region_slug, manifest, region_metrics)
            _stage_listing_metrics(cur, region_slug, manifest, listing_metrics)
            checks = _validation_checks(
                cur,
                region_slug,
                manifest,
                compute_tract,
                compute_listing,
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
        and checks["source_unique_stops"] > 0
        and checks["feed_version_count"] > 0
        and checks["invalid_stop_geometries"] == 0
        and (not compute_tract or checks["tract_coverage"] >= manifest.coverage_threshold)
        and (
            not compute_listing
            or checks["listing_point_coverage"] >= manifest.coverage_threshold
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


def _query_bbox(tracts: gpd.GeoDataFrame) -> tuple[float, float, float, float]:
    polygon = gpd.GeoSeries([box(*tracts.total_bounds)], crs="EPSG:4326")
    buffered = polygon.to_crs(PROJECTED_CRS).buffer(QUERY_BUFFER_M).to_crs("EPSG:4326")
    return tuple(float(value) for value in buffered.iloc[0].bounds)


def _fetch_stops(
    region_slug: str, tracts: gpd.GeoDataFrame, api_key: str
) -> tuple[gpd.GeoDataFrame, TransitlandStats]:
    bbox = _query_bbox(tracts)
    cache_dir = repo_root() / "data" / "raw" / "transitland" / region_slug
    pages_dir = cache_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    request_path = cache_dir / "request.json"
    request_payload = {
        "endpoint": TRANSITLAND_STOPS_URL,
        "bbox": list(bbox),
        "limit": PAGE_LIMIT,
        "active_feed_versions": True,
    }
    if request_path.exists() and json.loads(request_path.read_text()) != request_payload:
        raise RuntimeError(
            f"Cached Transitland request differs for {region_slug}; preserve the old evidence "
            "and move the cache directory before rerunning"
        )
    request_path.write_text(json.dumps(request_payload, indent=2, sort_keys=True))

    next_url: str | None = f"{TRANSITLAND_STOPS_URL}?{urlencode({'bbox': ','.join(str(v) for v in bbox), 'limit': PAGE_LIMIT})}"
    payloads: list[dict[str, Any]] = []
    pages_read = 0
    pages_fetched = 0
    retries = 0
    page_number = 1
    while next_url:
        page_path = pages_dir / f"page_{page_number:04d}.json"
        pages_read += 1
        if page_path.exists():
            payload = json.loads(page_path.read_text())
        else:
            payload, page_retries = _request_json(next_url, api_key)
            page_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
            pages_fetched += 1
            retries += page_retries
        if not isinstance(payload.get("stops"), list):
            raise RuntimeError(f"Transitland page {page_number} has no stops array")
        payloads.append(payload)
        next_value = (payload.get("meta") or {}).get("next")
        next_url = str(next_value) if next_value else None
        page_number += 1

    records = [record for payload in payloads for record in payload["stops"]]
    stops, invalid_count, feed_versions = _deduplicate_stops(records)
    return stops, TransitlandStats(
        pages_read=pages_read,
        pages_fetched=pages_fetched,
        page_retries=retries,
        raw_stop_records=len(records),
        unique_stops=len(stops),
        duplicate_stops_removed=len(records) - len(stops) - invalid_count,
        invalid_stop_geometries=invalid_count,
        feed_versions=feed_versions,
        query_bbox=bbox,
    )


def _request_json(url: str, api_key: str) -> tuple[dict[str, Any], int]:
    last_error: Exception | None = None
    for attempt in range(8):
        try:
            request = Request(
                url,
                headers={
                    "apikey": api_key,
                    "Accept": "application/json",
                    "User-Agent": "Groundtruth transit-access ingestion",
                },
            )
            with urlopen(request, timeout=120) as response:
                return json.load(response), attempt
        except HTTPError as exc:
            last_error = exc
            if exc.code != 429 and not 500 <= exc.code < 600:
                raise RuntimeError(f"Transitland request failed with HTTP {exc.code}") from exc
            retry_after = exc.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else 1.5 * (attempt + 1)
            time.sleep(min(delay, 30))
        except Exception as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def _deduplicate_stops(
    records: list[dict[str, Any]],
) -> tuple[gpd.GeoDataFrame, int, dict[str, dict[str, str]]]:
    unique: dict[str, dict[str, Any]] = {}
    feed_versions: dict[str, dict[str, str]] = {}
    invalid = 0
    for record in records:
        geometry = record.get("geometry") or {}
        coordinates = geometry.get("coordinates")
        if (
            geometry.get("type") != "Point"
            or not isinstance(coordinates, list)
            or len(coordinates) < 2
            or not all(isinstance(value, (int, float)) for value in coordinates[:2])
        ):
            invalid += 1
            continue
        identity = str(record.get("onestop_id") or f"id:{record.get('id')}")
        unique.setdefault(
            identity,
            {
                "identity": identity,
                "geometry": Point(float(coordinates[0]), float(coordinates[1])),
            },
        )
        version = record.get("feed_version") or {}
        sha1 = version.get("sha1")
        if sha1:
            feed = version.get("feed") or {}
            feed_versions[str(sha1)] = {
                "feed_onestop_id": str(feed.get("onestop_id") or ""),
                "fetched_at": str(version.get("fetched_at") or ""),
            }
    frame = gpd.GeoDataFrame(list(unique.values()), geometry="geometry", crs="EPSG:4326")
    return frame, invalid, feed_versions


def _compute_region_metrics(
    tracts: gpd.GeoDataFrame, stops: gpd.GeoDataFrame
) -> tuple[list[RegionMetric], dict[str, Any]]:
    tracts_work = tracts[["slug", "geometry"]].to_crs(PROJECTED_CRS).copy()
    stops_work = stops[["geometry"]].to_crs(PROJECTED_CRS)
    joined = gpd.sjoin(stops_work, tracts_work, how="inner", predicate="within")
    counts = joined["slug"].value_counts()
    areas_sq_km = tracts_work.set_index("slug").geometry.area / 1_000_000.0
    values = pd.Series(
        {
            str(slug): float(counts.get(slug, 0)) / float(area)
            for slug, area in areas_sq_km.items()
        },
        dtype="float64",
    )
    metrics = [
        RegionMetric(region_slug=str(slug), value=float(value))
        for slug, value in values.items()
    ]
    return metrics, {
        "query_buffer_m": QUERY_BUFFER_M,
        "stops_inside_region_tracts": int(len(joined)),
        "stops_outside_region_tracts": int(len(stops_work) - len(joined)),
        "tract_stop_density_mean": float(values.mean()),
        "tract_stop_density_p50": float(values.quantile(0.5)),
        "tract_stop_density_p90": float(values.quantile(0.9)),
        "tract_stop_density_max": float(values.max()),
        "tracts_with_zero_stops": int((values == 0).sum()),
    }


def _compute_listing_metrics(
    listings: gpd.GeoDataFrame, stops: gpd.GeoDataFrame
) -> tuple[list[ListingMetric], dict[str, Any]]:
    listings_work = listings[["id", "geometry"]].to_crs(PROJECTED_CRS)
    stops_work = stops[["geometry"]].to_crs(PROJECTED_CRS)
    nearest = gpd.sjoin_nearest(
        listings_work,
        stops_work,
        how="left",
        distance_col="distance_m",
    )
    distances = nearest.groupby("id")["distance_m"].min().reindex(listings_work["id"])
    metrics = [
        ListingMetric(listing_id=int(listing_id), value=float(distance))
        for listing_id, distance in distances.items()
        if pd.notna(distance)
    ]
    return metrics, {
        "query_buffer_m": QUERY_BUFFER_M,
        "listing_distance_min_m": float(distances.min()),
        "listing_distance_p50_m": float(distances.quantile(0.5)),
        "listing_distance_p90_m": float(distances.quantile(0.9)),
        "listing_distance_max_m": float(distances.max()),
        "listings_within_400m": int((distances <= 400).sum()),
        "listings_within_800m": int((distances <= 800).sum()),
        "listings_without_nearest_stop": int(distances.isna().sum()),
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
        VALUES (%s, %s, %s, 'point', %s, %s)
        ON CONFLICT (region_group, metric_key, listing_id, grain, vintage) DO UPDATE SET
          value = EXCLUDED.value
        """,
        [
            (region_slug, manifest.metric_key, metric.listing_id, metric.value, manifest.vintage)
            for metric in metrics
        ],
    )


def _validation_checks(
    cur: psycopg.Cursor[Any],
    region_slug: str,
    manifest: LayerManifest,
    compute_tract: bool,
    compute_listing: bool,
    source_stats: TransitlandStats,
    reduction_stats: dict[str, Any],
) -> dict[str, Any]:
    cur.execute(
        "SELECT count(*) FROM regions WHERE region_group = %s AND region_type = 'census_tract'",
        (region_slug,),
    )
    expected_tracts = int(cur.fetchone()[0])
    cur.execute("SELECT count(*) FROM listings WHERE region_slug = %s", (region_slug,))
    expected_listings = int(cur.fetchone()[0])
    cur.execute(
        """
        SELECT count(*), coalesce(min(value), 0), coalesce(max(value), 0),
               count(*) FILTER (WHERE value::text IN ('NaN', 'Infinity', '-Infinity'))
        FROM staging.layer_region_metrics
        WHERE region_group = %s AND metric_key = %s AND vintage = %s
        """,
        (region_slug, manifest.metric_key, manifest.vintage),
    )
    tract_count, tract_min, tract_max, tract_nonfinite = cur.fetchone()
    cur.execute(
        """
        SELECT count(*), coalesce(min(value), 0), coalesce(max(value), 0),
               count(*) FILTER (WHERE value::text IN ('NaN', 'Infinity', '-Infinity'))
        FROM staging.layer_listing_metrics
        WHERE region_group = %s AND metric_key = %s AND vintage = %s AND grain = 'point'
        """,
        (region_slug, manifest.metric_key, manifest.vintage),
    )
    listing_count, listing_min, listing_max, listing_nonfinite = cur.fetchone()
    relevant_bounds = (
        [float(tract_min), float(tract_max)]
        if compute_tract
        else [float(listing_min), float(listing_max)]
    )
    feed_versions = source_stats.feed_versions
    fetched_dates = sorted(
        value["fetched_at"] for value in feed_versions.values() if value["fetched_at"]
    )
    return {
        "metric_key": manifest.metric_key,
        "region": region_slug,
        "grain": "tract" if compute_tract else "listing",
        "tracts_expected": expected_tracts,
        "tracts_computed": int(tract_count),
        "tract_coverage": int(tract_count) / expected_tracts if expected_tracts else 0,
        "listings_expected": expected_listings,
        "listing_point_computed": int(listing_count),
        "listing_point_coverage": int(listing_count) / expected_listings if expected_listings else 0,
        "nonfinite_values": int(tract_nonfinite) + int(listing_nonfinite),
        "range_allowed": list(manifest.allowed_range),
        "range_min": min(relevant_bounds),
        "range_max": max(relevant_bounds),
        "transitland_pages_read": source_stats.pages_read,
        "transitland_pages_fetched": source_stats.pages_fetched,
        "transitland_page_retries": source_stats.page_retries,
        "source_raw_stop_records": source_stats.raw_stop_records,
        "source_unique_stops": source_stats.unique_stops,
        "source_duplicate_stops_removed": source_stats.duplicate_stops_removed,
        "invalid_stop_geometries": source_stats.invalid_stop_geometries,
        "feed_version_count": len(feed_versions),
        "feed_version_sha1s": sorted(feed_versions),
        "feed_onestop_ids": sorted(
            {value["feed_onestop_id"] for value in feed_versions.values() if value["feed_onestop_id"]}
        ),
        "feed_version_fetched_at_min": fetched_dates[0] if fetched_dates else None,
        "feed_version_fetched_at_max": fetched_dates[-1] if fetched_dates else None,
        "query_bbox": list(source_stats.query_bbox),
    } | reduction_stats
