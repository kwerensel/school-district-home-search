from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import math
import time

import geopandas as gpd
import osmnx as ox
import pandas as pd
import psycopg
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from gt.db.migrate import database_url, repo_root
from gt.manifests import LayerManifest, load_layer_manifest
from gt.reports import ValidationReport, write_report


PADUS_LAYER = (
    "https://services.arcgis.com/v01gqwM5QqNysAAi/arcgis/rest/services/"
    "PADUS_Public_Access/FeatureServer/0"
)
PADUS_FIELDS = ["OBJECTID", "Pub_Access", "Unit_Nm", "DesTp_Desc"]
OSM_TAGS: dict[str, list[str]] = {
    "leisure": [
        "park",
        "garden",
        "playground",
        "recreation_ground",
        "nature_reserve",
        "pitch",
    ],
    "boundary": ["protected_area"],
    "landuse": ["recreation_ground", "village_green"],
}
PRIVATE_ACCESS = {"private", "no", "customers", "permit", "members"}
METRIC_KEYS = {"park_access", "park_distance_m"}
PROJECTED_CRS = "EPSG:5070"
ACCESS_BUFFER_M = 800.0


@dataclass(frozen=True)
class RegionMetric:
    region_slug: str
    value: float


@dataclass(frozen=True)
class ListingMetric:
    listing_id: int
    value: float


@dataclass(frozen=True)
class SourceStats:
    padus_object_ids: int
    padus_features: int
    padus_chunks_read: int
    padus_chunks_fetched: int
    padus_chunk_retries: int
    padus_access_counts: dict[str, int]
    osm_features: int
    osm_excluded_private: int
    osm_tag_counts: dict[str, int]
    source_features_open: int
    source_invalid_fixed: int


def run_park_access(
    manifest_path: Path, region_slug: str, grain: str
) -> tuple[ValidationReport, Path]:
    manifest = load_layer_manifest(manifest_path)
    if manifest.metric_key not in METRIC_KEYS:
        raise ValueError(f"Unsupported park manifest metric: {manifest.metric_key}")
    if grain not in {"tract", "listing", "both"}:
        raise ValueError("grain must be tract, listing, or both")

    compute_tract = manifest.metric_key == "park_access" and grain in {"tract", "both"}
    compute_listing = manifest.metric_key == "park_distance_m" and grain in {"listing", "both"}
    if not compute_tract and not compute_listing:
        supported = "tract" if manifest.metric_key == "park_access" else "listing"
        raise ValueError(f"{manifest.metric_key} supports {supported} grain only")

    with psycopg.connect(database_url(), autocommit=True) as conn:
        tracts = _read_tracts(conn, region_slug)
        listings = _read_listings(conn, region_slug)
    if tracts.empty:
        raise RuntimeError(f"No census tract regions found for {region_slug}")
    if listings.empty:
        raise RuntimeError(f"No frozen listings found for {region_slug}")

    source, source_stats = _fetch_sources(region_slug, tracts)
    if source.empty:
        raise RuntimeError(f"No open-access park polygons found for {region_slug}")

    region_metrics: list[RegionMetric] = []
    listing_metrics: list[ListingMetric] = []
    reduction_stats: dict[str, Any] = {}
    if compute_tract:
        region_metrics, reduction_stats = _compute_region_metrics(tracts, source)
    if compute_listing:
        listing_metrics, reduction_stats = _compute_listing_metrics(listings, source)

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
        and checks["source_features_open"] > 0
        and checks["padus_features"] == checks["padus_object_ids"]
        and (
            not compute_tract
            or checks["tract_coverage"] >= manifest.coverage_threshold
        )
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


def _fetch_sources(
    region_slug: str, tracts: gpd.GeoDataFrame
) -> tuple[gpd.GeoDataFrame, SourceStats]:
    query_polygon = _query_polygon(tracts)
    padus, padus_stats = _fetch_padus(region_slug, query_polygon.bounds)
    osm, osm_stats = _fetch_osm(region_slug, query_polygon)

    open_padus = padus.loc[padus["Pub_Access"] == "OA", ["geometry"]].copy()
    open_padus["source"] = "padus"
    open_osm = osm[["geometry"]].copy()
    open_osm["source"] = "osm"
    combined = gpd.GeoDataFrame(
        pd.concat([open_padus, open_osm], ignore_index=True),
        geometry="geometry",
        crs="EPSG:4326",
    )
    combined, invalid_fixed = _clean_polygon_frame(combined)
    return combined, SourceStats(
        padus_object_ids=padus_stats["object_ids"],
        padus_features=padus_stats["features"],
        padus_chunks_read=padus_stats["chunks_read"],
        padus_chunks_fetched=padus_stats["chunks_fetched"],
        padus_chunk_retries=padus_stats["chunk_retries"],
        padus_access_counts=padus_stats["access_counts"],
        osm_features=osm_stats["features"],
        osm_excluded_private=osm_stats["excluded_private"],
        osm_tag_counts=osm_stats["tag_counts"],
        source_features_open=len(combined),
        source_invalid_fixed=invalid_fixed,
    )


def _query_polygon(tracts: gpd.GeoDataFrame) -> BaseGeometry:
    bounds = box(*tracts.total_bounds)
    return (
        gpd.GeoSeries([bounds], crs="EPSG:4326")
        .to_crs(PROJECTED_CRS)
        .buffer(ACCESS_BUFFER_M)
        .to_crs("EPSG:4326")
        .iloc[0]
    )


def _fetch_padus(
    region_slug: str, bounds: tuple[float, float, float, float]
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    cache_dir = repo_root() / "data" / "raw" / "park_access" / region_slug / "padus"
    chunks_dir = cache_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    ids_path = cache_dir / "object_ids.json"
    if ids_path.exists():
        object_ids = [int(value) for value in json.loads(ids_path.read_text())["object_ids"]]
    else:
        minx, miny, maxx, maxy = bounds
        payload, _ = _arcgis_query(
            {
                "where": "Pub_Access IN ('OA','RA','XA')",
                "returnIdsOnly": "true",
                "geometry": f"{minx},{miny},{maxx},{maxy}",
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
            }
        )
        object_ids = sorted(int(value) for value in payload.get("objectIds") or [])
        ids_path.write_text(json.dumps({"object_ids": object_ids}, indent=2))

    frames: list[gpd.GeoDataFrame] = []
    chunks_read = 0
    chunks_fetched = 0
    retries = 0
    for start in range(0, len(object_ids), 50):
        ids = object_ids[start : start + 50]
        if not ids:
            continue
        path = chunks_dir / f"{ids[0]}_{ids[-1]}.geojson"
        chunks_read += 1
        if path.exists():
            frame = gpd.read_file(path)
        else:
            payload, chunk_retries = _arcgis_query(
                {
                    "objectIds": ",".join(str(value) for value in ids),
                    "outFields": ",".join(PADUS_FIELDS),
                    "returnGeometry": "true",
                    "outSR": "4326",
                },
                output_format="geojson",
            )
            path.write_text(json.dumps(payload))
            frame = gpd.GeoDataFrame.from_features(payload.get("features") or [], crs="EPSG:4326")
            chunks_fetched += 1
            retries += chunk_retries
        frames.append(frame)

    if frames:
        padus = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry", crs="EPSG:4326")
    else:
        padus = gpd.GeoDataFrame(columns=PADUS_FIELDS + ["geometry"], geometry="geometry", crs="EPSG:4326")
    access_counts = {
        str(key): int(value)
        for key, value in padus.get("Pub_Access", pd.Series(dtype=str)).value_counts().to_dict().items()
    }
    return padus, {
        "object_ids": len(object_ids),
        "features": len(padus),
        "chunks_read": chunks_read,
        "chunks_fetched": chunks_fetched,
        "chunk_retries": retries,
        "access_counts": access_counts,
    }


def _arcgis_query(
    params: dict[str, str], output_format: str = "json"
) -> tuple[dict[str, Any], int]:
    data = urlencode({"f": output_format} | params).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(8):
        try:
            request = Request(
                f"{PADUS_LAYER}/query",
                data=data,
                headers={"User-Agent": "Groundtruth park-access ingestion"},
            )
            with urlopen(request, timeout=180) as response:
                payload = json.load(response)
            if "error" in payload:
                message = payload["error"].get("message", "unknown ArcGIS error")
                raise RuntimeError(f"PAD-US query failed: {message}")
            return payload, attempt
        except Exception as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def _fetch_osm(
    region_slug: str, query_polygon: BaseGeometry
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    cache_path = repo_root() / "data" / "raw" / "park_access" / region_slug / "osm.geojson"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    ox.settings.cache_folder = repo_root() / "data" / "raw" / "park_access" / "osmnx-cache"
    if cache_path.exists():
        frame = gpd.read_file(cache_path)
    else:
        frame = ox.features_from_polygon(query_polygon, OSM_TAGS).reset_index()
        frame = frame.to_crs("EPSG:4326")
        cache_path.write_text(frame.to_json(drop_id=True))

    polygon_types = {"Polygon", "MultiPolygon"}
    frame = frame.loc[frame.geometry.geom_type.isin(polygon_types)].copy()
    access = frame.get("access", pd.Series(index=frame.index, dtype=object)).fillna("")
    excluded = access.astype(str).str.lower().isin(PRIVATE_ACCESS)
    tag_counts: dict[str, int] = {}
    for key in OSM_TAGS:
        if key not in frame:
            continue
        for value, count in frame[key].dropna().astype(str).value_counts().items():
            tag_counts[f"{key}={value}"] = int(count)
    frame = frame.loc[~excluded, ["geometry"]].copy()
    frame, invalid_fixed = _clean_polygon_frame(frame)
    return frame, {
        "features": len(frame),
        "excluded_private": int(excluded.sum()),
        "invalid_fixed": invalid_fixed,
        "tag_counts": tag_counts,
    }


def _clean_polygon_frame(frame: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, int]:
    if frame.empty:
        return frame, 0
    work = frame.loc[frame.geometry.notna() & ~frame.geometry.is_empty].copy()
    invalid = ~work.geometry.is_valid
    invalid_fixed = int(invalid.sum())
    if invalid_fixed:
        work.loc[invalid, "geometry"] = work.loc[invalid].geometry.make_valid()
    work = work.loc[
        work.geometry.notna()
        & ~work.geometry.is_empty
        & work.geometry.geom_type.isin({"Polygon", "MultiPolygon"})
    ].copy()
    return work, invalid_fixed


def _source_union(source: gpd.GeoDataFrame) -> BaseGeometry:
    geometries = source.to_crs(PROJECTED_CRS).geometry
    return unary_union(list(geometries))


def _compute_region_metrics(
    tracts: gpd.GeoDataFrame, source: gpd.GeoDataFrame
) -> tuple[list[RegionMetric], dict[str, Any]]:
    tracts_work = tracts[["slug", "geometry"]].to_crs(PROJECTED_CRS).copy()
    accessible = _source_union(source).buffer(ACCESS_BUFFER_M)
    shares = []
    for row in tracts_work.itertuples():
        area = row.geometry.area
        share = row.geometry.intersection(accessible).area / area if area > 0 else float("nan")
        shares.append(min(max(float(share), 0.0), 1.0))
    values = pd.Series(shares, index=tracts_work["slug"], dtype="float64")
    metrics = [
        RegionMetric(region_slug=str(slug), value=float(value))
        for slug, value in values.items()
    ]
    return metrics, {
        "access_buffer_m": ACCESS_BUFFER_M,
        "tract_access_share_mean": float(values.mean()),
        "tract_access_share_p50": float(values.quantile(0.5)),
        "tract_access_share_p90": float(values.quantile(0.9)),
        "tract_access_share_max": float(values.max()),
        "tracts_full_access": int((values >= 0.999999).sum()),
        "tracts_zero_access": int((values <= 0).sum()),
    }


def _compute_listing_metrics(
    listings: gpd.GeoDataFrame, source: gpd.GeoDataFrame
) -> tuple[list[ListingMetric], dict[str, Any]]:
    listings_work = listings[["id", "geometry"]].to_crs(PROJECTED_CRS)
    parks = _source_union(source)
    distances = listings_work.geometry.distance(parks).astype(float).clip(lower=0)
    metrics = [
        ListingMetric(listing_id=int(listing_id), value=float(distance))
        for listing_id, distance in zip(listings_work["id"], distances, strict=True)
    ]
    return metrics, {
        "listing_distance_min_m": float(distances.min()),
        "listing_distance_p50_m": float(distances.quantile(0.5)),
        "listing_distance_p90_m": float(distances.quantile(0.9)),
        "listing_distance_max_m": float(distances.max()),
        "listings_inside_access_polygon": int((distances == 0).sum()),
        "listings_within_800m": int((distances <= ACCESS_BUFFER_M).sum()),
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
    source_stats: SourceStats,
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
        "padus_object_ids": source_stats.padus_object_ids,
        "padus_features": source_stats.padus_features,
        "padus_chunks_read": source_stats.padus_chunks_read,
        "padus_chunks_fetched": source_stats.padus_chunks_fetched,
        "padus_chunk_retries": source_stats.padus_chunk_retries,
        "padus_access_counts": source_stats.padus_access_counts,
        "osm_features": source_stats.osm_features,
        "osm_excluded_private": source_stats.osm_excluded_private,
        "osm_tag_counts": source_stats.osm_tag_counts,
        "source_features_open": source_stats.source_features_open,
        "source_invalid_fixed": source_stats.source_invalid_fixed,
    } | reduction_stats
