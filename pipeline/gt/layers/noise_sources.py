from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import math
from pathlib import Path
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

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


FRA_RAIL_LAYER = (
    "https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/"
    "NTAD_North_American_Rail_Network_Lines/FeatureServer/0"
)
FRA_ACTIVE_FREIGHT_NET_CODES = ("M", "I", "O", "S", "Y")
FRA_FIELDS = [
    "OBJECTID",
    "FRAARCID",
    "NET",
    "RROWNER1",
    "RROWNER2",
    "RROWNER3",
    "TRKRGHTS1",
    "TRKRGHTS2",
    "TRKRGHTS3",
]
OSM_TAGS: dict[str, list[str]] = {
    "amenity": [
        "fire_station",
        "police",
        "hospital",
        "bar",
        "pub",
        "nightclub",
    ],
    "landuse": ["industrial"],
}
SIREN_AMENITIES = {"fire_station", "police", "hospital"}
NIGHTLIFE_AMENITIES = {"bar", "pub", "nightclub"}
PROJECTED_CRS = "EPSG:5070"
QUERY_BUFFER_M = 10_000.0
NIGHTLIFE_BUFFER_M = 300.0

TRACT_METRICS = {
    "noise_siren_density",
    "noise_nightlife_density",
    "noise_industrial_land_pct",
    "noise_freight_rail_density",
}
LISTING_METRICS = {
    "noise_siren_distance_m",
    "noise_nightlife_count_300m",
    "noise_industrial_distance_m",
    "noise_freight_rail_distance_m",
}
SUPPORTED_METRICS = TRACT_METRICS | LISTING_METRICS


@dataclass(frozen=True)
class RegionMetric:
    region_slug: str
    value: float


@dataclass(frozen=True)
class ListingMetric:
    listing_id: int
    value: float


@dataclass(frozen=True)
class SourceBundle:
    siren: gpd.GeoDataFrame
    nightlife: gpd.GeoDataFrame
    industrial: gpd.GeoDataFrame
    freight_rail: gpd.GeoDataFrame
    stats: dict[str, Any]


def run_noise_sources(
    manifest_path: Path, region_slug: str, grain: str
) -> tuple[ValidationReport, Path]:
    manifest = load_layer_manifest(manifest_path)
    if manifest.metric_key not in SUPPORTED_METRICS:
        raise ValueError(f"Unsupported supplemental noise metric: {manifest.metric_key}")
    if grain not in {"tract", "listing", "both"}:
        raise ValueError("grain must be tract, listing, or both")

    compute_tract = manifest.metric_key in TRACT_METRICS and grain in {"tract", "both"}
    compute_listing = manifest.metric_key in LISTING_METRICS and grain in {"listing", "both"}
    if not compute_tract and not compute_listing:
        supported = "tract" if manifest.metric_key in TRACT_METRICS else "listing"
        raise ValueError(f"{manifest.metric_key} supports {supported} grain only")

    with psycopg.connect(database_url(), autocommit=True) as conn:
        tracts = _read_tracts(conn, region_slug)
        listings = _read_listings(conn, region_slug)
    if tracts.empty:
        raise RuntimeError(f"No census tract regions found for {region_slug}")
    if listings.empty:
        raise RuntimeError(f"No frozen listings found for {region_slug}")

    sources = _fetch_sources(region_slug, tracts)
    _assert_relevant_source(manifest.metric_key, sources)
    region_metrics, listing_metrics, reduction_stats = _compute_metric(
        manifest.metric_key, tracts, listings, sources
    )

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
                sources.stats,
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
        and checks["relevant_source_features"] > 0
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
        SELECT id, address, state, geom AS geometry
        FROM listings
        WHERE region_slug = %s
        ORDER BY id
        """,
        conn,
        params=(region_slug,),
        geom_col="geometry",
    )


def _query_polygon(tracts: gpd.GeoDataFrame) -> BaseGeometry:
    return (
        gpd.GeoSeries([box(*tracts.total_bounds)], crs="EPSG:4326")
        .to_crs(PROJECTED_CRS)
        .buffer(QUERY_BUFFER_M)
        .to_crs("EPSG:4326")
        .iloc[0]
    )


def _fetch_sources(region_slug: str, tracts: gpd.GeoDataFrame) -> SourceBundle:
    query_polygon = _query_polygon(tracts)
    osm, osm_stats = _fetch_osm(region_slug, query_polygon)
    rail, rail_stats = _fetch_freight_rail(region_slug, query_polygon.bounds)

    amenities = osm.get("amenity", pd.Series(index=osm.index, dtype=object)).fillna("")
    landuse = osm.get("landuse", pd.Series(index=osm.index, dtype=object)).fillna("")
    siren = osm.loc[amenities.astype(str).isin(SIREN_AMENITIES)].copy()
    nightlife = osm.loc[amenities.astype(str).isin(NIGHTLIFE_AMENITIES)].copy()
    industrial = osm.loc[
        (landuse.astype(str) == "industrial")
        & osm.geometry.geom_type.isin({"Polygon", "MultiPolygon"})
    ].copy()

    stats = {
        "query_buffer_m": QUERY_BUFFER_M,
        "query_bounds": [float(value) for value in query_polygon.bounds],
        "osm_retrieval_date": osm_stats["retrieval_date"],
        "osm_features": len(osm),
        "osm_siren_features": len(siren),
        "osm_siren_amenity_counts": _value_counts(siren, "amenity"),
        "osm_nightlife_features": len(nightlife),
        "osm_nightlife_amenity_counts": _value_counts(nightlife, "amenity"),
        "osm_industrial_polygons": len(industrial),
        "fra_service_url": FRA_RAIL_LAYER,
        "fra_service_description": rail_stats["service_description"],
        "fra_service_last_edit_ms": rail_stats["service_last_edit_ms"],
        "fra_object_ids": rail_stats["object_ids"],
        "fra_features": len(rail),
        "fra_chunks_read": rail_stats["chunks_read"],
        "fra_chunks_fetched": rail_stats["chunks_fetched"],
        "fra_chunk_retries": rail_stats["chunk_retries"],
        "fra_net_counts": _value_counts(rail, "NET"),
        "fra_active_net_codes": list(FRA_ACTIVE_FREIGHT_NET_CODES),
    }
    return SourceBundle(siren, nightlife, industrial, rail, stats)


def _fetch_osm(
    region_slug: str, query_polygon: BaseGeometry
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    cache_dir = repo_root() / "data" / "raw" / "noise_sources" / region_slug
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "osm.geojson"
    request_path = cache_dir / "osm_request.json"
    request_payload = {
        "retrieval_date": date.today().isoformat(),
        "query_bounds": [float(value) for value in query_polygon.bounds],
        "query_buffer_m": QUERY_BUFFER_M,
        "tags": OSM_TAGS,
    }
    if cache_path.exists():
        frame = gpd.read_file(cache_path)
        cached_request = json.loads(request_path.read_text()) if request_path.exists() else {}
        retrieval_date = str(cached_request.get("retrieval_date") or "unknown")
    else:
        ox.settings.cache_folder = (
            repo_root() / "data" / "raw" / "noise_sources" / "osmnx-cache"
        )
        frame = ox.features_from_polygon(query_polygon, OSM_TAGS).reset_index()
        frame = frame.to_crs("EPSG:4326")
        keep = [
            column
            for column in ("element", "osmid", "amenity", "landuse", "name", "geometry")
            if column in frame.columns
        ]
        frame = frame[keep].copy()
        cache_path.write_text(frame.to_json(drop_id=True))
        request_path.write_text(json.dumps(request_payload, indent=2, sort_keys=True))
        retrieval_date = request_payload["retrieval_date"]
    frame = frame.loc[frame.geometry.notna() & ~frame.geometry.is_empty].copy()
    return frame, {"retrieval_date": retrieval_date}


def _fetch_freight_rail(
    region_slug: str, bounds: tuple[float, float, float, float]
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    cache_dir = repo_root() / "data" / "raw" / "noise_sources" / region_slug / "fra"
    chunks_dir = cache_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = cache_dir / "service.json"
    ids_path = cache_dir / "object_ids.json"

    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text())
    else:
        metadata, _ = _request_json(FRA_RAIL_LAYER, {"f": "pjson"})
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True))

    where = f"NET IN ({','.join(repr(value) for value in FRA_ACTIVE_FREIGHT_NET_CODES)})"
    if ids_path.exists():
        object_ids = [int(value) for value in json.loads(ids_path.read_text())["object_ids"]]
    else:
        minx, miny, maxx, maxy = bounds
        payload, _ = _request_json(
            f"{FRA_RAIL_LAYER}/query",
            {
                "f": "json",
                "where": where,
                "returnIdsOnly": "true",
                "geometry": f"{minx},{miny},{maxx},{maxy}",
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
            },
        )
        if "error" in payload:
            raise RuntimeError(f"FRA object-id query failed: {payload['error']}")
        object_ids = sorted(int(value) for value in payload.get("objectIds") or [])
        ids_path.write_text(
            json.dumps(
                {
                    "where": where,
                    "query_bounds": [float(value) for value in bounds],
                    "object_ids": object_ids,
                },
                indent=2,
                sort_keys=True,
            )
        )

    frames: list[gpd.GeoDataFrame] = []
    chunks_read = 0
    chunks_fetched = 0
    retries = 0
    for start in range(0, len(object_ids), 500):
        ids = object_ids[start : start + 500]
        if not ids:
            continue
        path = chunks_dir / f"{ids[0]}_{ids[-1]}.geojson"
        chunks_read += 1
        if path.exists():
            frame = gpd.read_file(path)
        else:
            payload, chunk_retries = _request_json(
                f"{FRA_RAIL_LAYER}/query",
                {
                    "f": "geojson",
                    "objectIds": ",".join(str(value) for value in ids),
                    "outFields": ",".join(FRA_FIELDS),
                    "returnGeometry": "true",
                    "outSR": "4326",
                },
            )
            if "error" in payload:
                raise RuntimeError(f"FRA feature query failed: {payload['error']}")
            path.write_text(json.dumps(payload))
            frame = gpd.GeoDataFrame.from_features(
                payload.get("features") or [], crs="EPSG:4326"
            )
            chunks_fetched += 1
            retries += chunk_retries
        frames.append(frame)

    if frames:
        rail = gpd.GeoDataFrame(
            pd.concat(frames, ignore_index=True), geometry="geometry", crs="EPSG:4326"
        )
        rail = rail.loc[
            rail.geometry.notna()
            & ~rail.geometry.is_empty
            & rail.geometry.geom_type.isin({"LineString", "MultiLineString"})
        ].copy()
    else:
        rail = gpd.GeoDataFrame(columns=FRA_FIELDS + ["geometry"], crs="EPSG:4326")
    editing_info = metadata.get("editingInfo") or {}
    return rail, {
        "service_description": str(metadata.get("description") or ""),
        "service_last_edit_ms": editing_info.get("lastEditDate"),
        "object_ids": len(object_ids),
        "chunks_read": chunks_read,
        "chunks_fetched": chunks_fetched,
        "chunk_retries": retries,
    }


def _request_json(url: str, params: dict[str, str]) -> tuple[dict[str, Any], int]:
    encoded = urlencode(params).encode("utf-8")
    use_post = url.endswith("/query")
    last_error: Exception | None = None
    for attempt in range(8):
        try:
            request = Request(
                url if use_post else f"{url}?{encoded.decode('utf-8')}",
                data=encoded if use_post else None,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Groundtruth supplemental-noise ingestion",
                },
            )
            with urlopen(request, timeout=180) as response:
                return json.load(response), attempt
        except Exception as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def _value_counts(frame: gpd.GeoDataFrame, column: str) -> dict[str, int]:
    if frame.empty or column not in frame:
        return {}
    return {
        str(key): int(value)
        for key, value in frame[column].dropna().astype(str).value_counts().items()
    }


def _assert_relevant_source(metric_key: str, sources: SourceBundle) -> None:
    source = _source_for_metric(metric_key, sources)
    if source.empty:
        raise RuntimeError(f"No source features found for {metric_key}")


def _source_for_metric(metric_key: str, sources: SourceBundle) -> gpd.GeoDataFrame:
    if "siren" in metric_key:
        return sources.siren
    if "nightlife" in metric_key:
        return sources.nightlife
    if "industrial" in metric_key:
        return sources.industrial
    if "freight_rail" in metric_key:
        return sources.freight_rail
    raise ValueError(f"Unsupported supplemental noise metric: {metric_key}")


def _compute_metric(
    metric_key: str,
    tracts: gpd.GeoDataFrame,
    listings: gpd.GeoDataFrame,
    sources: SourceBundle,
) -> tuple[list[RegionMetric], list[ListingMetric], dict[str, Any]]:
    source = _source_for_metric(metric_key, sources)
    if metric_key == "noise_siren_density":
        metrics, stats = _point_density(tracts, source)
        return metrics, [], stats
    if metric_key == "noise_nightlife_density":
        metrics, stats = _point_density(tracts, source)
        return metrics, [], stats
    if metric_key == "noise_industrial_land_pct":
        metrics, stats = _polygon_share(tracts, source)
        return metrics, [], stats
    if metric_key == "noise_freight_rail_density":
        metrics, stats = _line_density(tracts, source)
        return metrics, [], stats
    if metric_key == "noise_nightlife_count_300m":
        metrics, stats = _listing_buffer_count(listings, source, NIGHTLIFE_BUFFER_M)
        return [], metrics, stats
    metrics, stats = _listing_distance(listings, source)
    return [], metrics, stats


def _representative_points(source: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    projected = source[["geometry"]].to_crs(PROJECTED_CRS).copy()
    projected["geometry"] = projected.geometry.representative_point()
    return projected


def _point_density(
    tracts: gpd.GeoDataFrame, source: gpd.GeoDataFrame
) -> tuple[list[RegionMetric], dict[str, Any]]:
    tracts_work = tracts[["slug", "geometry"]].to_crs(PROJECTED_CRS).copy()
    points = _representative_points(source)
    joined = gpd.sjoin(points, tracts_work, how="inner", predicate="within")
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
        "relevant_source_features": len(source),
        "source_features_inside_tracts": len(joined),
        "tract_density_mean": float(values.mean()),
        "tract_density_p90": float(values.quantile(0.9)),
        "tract_density_max": float(values.max()),
        "tracts_with_zero_sources": int((values == 0).sum()),
    }


def _polygon_share(
    tracts: gpd.GeoDataFrame, source: gpd.GeoDataFrame
) -> tuple[list[RegionMetric], dict[str, Any]]:
    tracts_work = tracts[["slug", "geometry"]].to_crs(PROJECTED_CRS).copy()
    source_union = unary_union(list(source.to_crs(PROJECTED_CRS).geometry))
    shares = []
    for row in tracts_work.itertuples():
        area = float(row.geometry.area)
        share = row.geometry.intersection(source_union).area / area if area > 0 else math.nan
        shares.append(min(max(float(share) * 100.0, 0.0), 100.0))
    values = pd.Series(shares, index=tracts_work["slug"], dtype="float64")
    metrics = [
        RegionMetric(region_slug=str(slug), value=float(value))
        for slug, value in values.items()
    ]
    return metrics, {
        "relevant_source_features": len(source),
        "tract_industrial_pct_mean": float(values.mean()),
        "tract_industrial_pct_p90": float(values.quantile(0.9)),
        "tract_industrial_pct_max": float(values.max()),
        "tracts_with_zero_industrial_land": int((values == 0).sum()),
    }


def _line_density(
    tracts: gpd.GeoDataFrame, source: gpd.GeoDataFrame
) -> tuple[list[RegionMetric], dict[str, Any]]:
    tracts_work = tracts[["slug", "geometry"]].to_crs(PROJECTED_CRS).copy()
    lines = source[["geometry"]].to_crs(PROJECTED_CRS).copy()
    spatial_index = lines.sindex
    values: dict[str, float] = {}
    for row in tracts_work.itertuples():
        candidate_indexes = list(spatial_index.query(row.geometry, predicate="intersects"))
        if candidate_indexes:
            candidates = lines.iloc[candidate_indexes]
            clipped = unary_union(list(candidates.geometry)).intersection(row.geometry)
            rail_km = float(clipped.length) / 1_000.0
        else:
            rail_km = 0.0
        area_sq_km = float(row.geometry.area) / 1_000_000.0
        values[str(row.slug)] = rail_km / area_sq_km if area_sq_km > 0 else math.nan
    series = pd.Series(values, dtype="float64")
    metrics = [
        RegionMetric(region_slug=str(slug), value=float(value))
        for slug, value in series.items()
    ]
    return metrics, {
        "relevant_source_features": len(source),
        "tract_rail_density_mean": float(series.mean()),
        "tract_rail_density_p90": float(series.quantile(0.9)),
        "tract_rail_density_max": float(series.max()),
        "tracts_with_zero_freight_rail": int((series == 0).sum()),
    }


def _listing_distance(
    listings: gpd.GeoDataFrame, source: gpd.GeoDataFrame
) -> tuple[list[ListingMetric], dict[str, Any]]:
    listings_work = listings[["id", "geometry"]].to_crs(PROJECTED_CRS)
    source_union = unary_union(list(source.to_crs(PROJECTED_CRS).geometry))
    distances = listings_work.geometry.distance(source_union).astype(float).clip(lower=0)
    metrics = [
        ListingMetric(listing_id=int(listing_id), value=float(distance))
        for listing_id, distance in zip(listings_work["id"], distances, strict=True)
    ]
    return metrics, {
        "relevant_source_features": len(source),
        "listing_distance_min_m": float(distances.min()),
        "listing_distance_p50_m": float(distances.quantile(0.5)),
        "listing_distance_p90_m": float(distances.quantile(0.9)),
        "listing_distance_max_m": float(distances.max()),
        "listings_within_300m": int((distances <= 300).sum()),
        "listings_within_500m": int((distances <= 500).sum()),
    }


def _listing_buffer_count(
    listings: gpd.GeoDataFrame, source: gpd.GeoDataFrame, buffer_m: float
) -> tuple[list[ListingMetric], dict[str, Any]]:
    listings_work = listings[["id", "geometry"]].to_crs(PROJECTED_CRS).copy()
    buffers = gpd.GeoDataFrame(
        {
            "listing_id": listings_work["id"].astype(int),
            "geometry": listings_work.geometry.buffer(buffer_m),
        },
        geometry="geometry",
        crs=PROJECTED_CRS,
    )
    points = _representative_points(source)
    joined = gpd.sjoin(points, buffers, how="inner", predicate="within")
    counts = joined["listing_id"].value_counts()
    values = listings_work["id"].astype(int).map(counts).fillna(0).astype(float)
    metrics = [
        ListingMetric(listing_id=int(listing_id), value=float(value))
        for listing_id, value in zip(listings_work["id"], values, strict=True)
    ]
    return metrics, {
        "relevant_source_features": len(source),
        "listing_buffer_m": buffer_m,
        "listing_count_mean": float(values.mean()),
        "listing_count_p90": float(values.quantile(0.9)),
        "listing_count_max": float(values.max()),
        "listings_with_zero_sources_in_buffer": int((values == 0).sum()),
        "listings_with_sources_in_buffer": int((values > 0).sum()),
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
    listing_grain = _listing_grain(manifest.metric_key)
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
                listing_grain,
                metric.value,
                manifest.vintage,
            )
            for metric in metrics
        ],
    )


def _listing_grain(metric_key: str) -> str:
    return "buffer_300m" if metric_key == "noise_nightlife_count_300m" else "point"


def _validation_checks(
    cur: psycopg.Cursor[Any],
    region_slug: str,
    manifest: LayerManifest,
    compute_tract: bool,
    compute_listing: bool,
    source_stats: dict[str, Any],
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
        SELECT count(*), min(value), max(value),
               count(*) FILTER (WHERE value::text IN ('NaN', 'Infinity', '-Infinity'))
        FROM staging.layer_region_metrics
        WHERE region_group = %s AND metric_key = %s AND vintage = %s
        """,
        (region_slug, manifest.metric_key, manifest.vintage),
    )
    tract_count, tract_min, tract_max, tract_nonfinite = cur.fetchone()
    cur.execute(
        """
        SELECT count(*), min(value), max(value),
               count(*) FILTER (WHERE value::text IN ('NaN', 'Infinity', '-Infinity'))
        FROM staging.layer_listing_metrics
        WHERE region_group = %s AND metric_key = %s AND vintage = %s AND grain = %s
        """,
        (region_slug, manifest.metric_key, manifest.vintage, _listing_grain(manifest.metric_key)),
    )
    listing_count, listing_min, listing_max, listing_nonfinite = cur.fetchone()
    bounds = [tract_min, tract_max] if compute_tract else [listing_min, listing_max]
    finite_bounds = [float(value) for value in bounds if value is not None]
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
        "listing_grain": _listing_grain(manifest.metric_key) if compute_listing else None,
        "nonfinite_values": int(tract_nonfinite or 0) + int(listing_nonfinite or 0),
        "range_allowed": list(manifest.allowed_range),
        "range_min": min(finite_bounds, default=math.nan),
        "range_max": max(finite_bounds, default=math.nan),
    } | source_stats | reduction_stats
