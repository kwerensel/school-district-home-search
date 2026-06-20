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
import pandas as pd
import psycopg
from shapely.geometry import LinearRing, MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry

from gt.db.migrate import database_url, repo_root
from gt.manifests import LayerManifest, load_layer_manifest
from gt.reports import ValidationReport, write_report

NFHL_FLOOD_HAZARD_ZONES = (
    "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28"
)
NFHL_FIELDS = [
    "OBJECTID",
    "FLD_ZONE",
    "ZONE_SUBTY",
    "SFHA_TF",
    "STATIC_BFE",
    "DEPTH",
    "SOURCE_CIT",
]


@dataclass(frozen=True)
class RegionMetric:
    region_slug: str
    value: float


@dataclass(frozen=True)
class ListingMetric:
    listing_id: int
    value: float


@dataclass(frozen=True)
class FetchStats:
    object_ids: int
    features: int
    chunks_read: int
    chunks_fetched: int
    chunk_retries: int
    zone_counts: dict[str, int]


def run_flood_sfha(manifest_path: Path, region_slug: str, grain: str) -> tuple[ValidationReport, Path]:
    manifest = load_layer_manifest(manifest_path)
    if manifest.metric_key != "flood_sfha":
        raise ValueError(f"Unsupported flood manifest metric: {manifest.metric_key}")
    if grain not in {"tract", "listing", "both"}:
        raise ValueError("grain must be tract, listing, or both")

    with psycopg.connect(database_url(), autocommit=True) as conn:
        tracts = _read_tracts(conn, region_slug)
        listings = _read_listings(conn, region_slug)
    if tracts.empty:
        raise RuntimeError(f"No census tract regions found for {region_slug}")
    if listings.empty:
        raise RuntimeError(f"No frozen listings found for {region_slug}")

    source, fetch_stats = _fetch_sfha_features(region_slug, tuple(tracts.total_bounds))

    region_metrics: list[RegionMetric] = []
    listing_metrics: list[ListingMetric] = []
    region_stats: dict[str, Any] = {}
    listing_stats: dict[str, Any] = {}
    if grain in {"tract", "both"}:
        region_metrics, region_stats = _compute_region_metrics(tracts, source)
    if grain in {"listing", "both"}:
        listing_metrics, listing_stats = _compute_listing_metrics(listings, source)

    with psycopg.connect(database_url(), autocommit=False) as conn:
        with conn.cursor() as cur:
            _clear_staging(cur, region_slug, manifest.metric_key)
            _stage_region_metrics(cur, region_slug, manifest, region_metrics)
            _stage_listing_metrics(cur, region_slug, manifest, listing_metrics)
            checks = _validation_checks(
                cur,
                region_slug,
                manifest,
                grain,
                fetch_stats,
                region_stats,
                listing_stats,
            )
        conn.commit()

    range_min, range_max = manifest.allowed_range
    needs_tract = grain in {"tract", "both"}
    needs_listing = grain in {"listing", "both"}
    promotable = (
        math.isfinite(checks["range_min"])
        and math.isfinite(checks["range_max"])
        and checks["range_min"] >= range_min
        and checks["range_max"] <= range_max
        and (not needs_tract or checks["tract_coverage"] >= 1.0)
        and (not needs_listing or checks["listing_point_coverage"] >= 1.0)
        and checks["tract_nonfinite"] == 0
        and checks["listing_point_nonfinite"] == 0
        and checks["source_features_fetched"] == checks["source_object_ids"]
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


def _fetch_sfha_features(
    region_slug: str, bounds: tuple[float, float, float, float]
) -> tuple[gpd.GeoDataFrame, FetchStats]:
    cache_dir = repo_root() / "data" / "raw" / "flood_sfha" / region_slug
    chunks_dir = cache_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    object_ids = _cached_object_ids(cache_dir, bounds)
    rows: list[dict[str, Any]] = []
    chunks_read = 0
    chunks_fetched = 0
    retries = 0
    chunk_size = 50
    for start in range(0, len(object_ids), chunk_size):
        ids = object_ids[start : start + chunk_size]
        features, fetched, chunk_retries = _cached_features(chunks_dir, ids)
        chunks_read += 1
        chunks_fetched += 1 if fetched else 0
        retries += chunk_retries
        for feature in features:
            attrs = feature.get("attributes") or {}
            geometry = _esri_polygon_to_shape(feature.get("geometry") or {})
            if geometry is None or geometry.is_empty:
                continue
            rows.append(attrs | {"geometry": geometry})

    frame = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    zone_counts = (
        {str(key): int(value) for key, value in frame["FLD_ZONE"].value_counts().to_dict().items()}
        if not frame.empty
        else {}
    )
    stats = FetchStats(
        object_ids=len(object_ids),
        features=len(frame),
        chunks_read=chunks_read,
        chunks_fetched=chunks_fetched,
        chunk_retries=retries,
        zone_counts=zone_counts,
    )
    return frame, stats


def _cached_object_ids(cache_dir: Path, bounds: tuple[float, float, float, float]) -> list[int]:
    path = cache_dir / "object_ids.json"
    if path.exists():
        payload = json.loads(path.read_text())
        return [int(value) for value in payload["object_ids"]]

    minx, miny, maxx, maxy = bounds
    geometry = json.dumps(
        {
            "xmin": minx,
            "ymin": miny,
            "xmax": maxx,
            "ymax": maxy,
            "spatialReference": {"wkid": 4326},
        }
    )
    payload = _arcgis_query(
        {
            "where": "SFHA_TF='T'",
            "returnIdsOnly": "true",
            "geometry": geometry,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
        }
    )
    object_ids = sorted(int(value) for value in payload.get("objectIds") or [])
    path.write_text(json.dumps({"object_ids": object_ids}, indent=2))
    return object_ids


def _cached_features(chunks_dir: Path, object_ids: list[int]) -> tuple[list[dict[str, Any]], bool, int]:
    path = chunks_dir / f"{object_ids[0]}_{object_ids[-1]}.json"
    if path.exists():
        payload = json.loads(path.read_text())
        return list(payload.get("features") or []), False, 0

    features, retries = _fetch_features_for_ids(object_ids)
    path.write_text(json.dumps({"features": features}))
    return features, True, retries


def _fetch_features_for_ids(object_ids: list[int]) -> tuple[list[dict[str, Any]], int]:
    try:
        payload, retries = _arcgis_query_with_retry_count(
            {
                "objectIds": ",".join(str(value) for value in object_ids),
                "outFields": ",".join(NFHL_FIELDS),
                "returnGeometry": "true",
                "outSR": "4326",
            }
        )
        return list(payload.get("features") or []), retries
    except Exception:
        if len(object_ids) == 1:
            raise
        mid = len(object_ids) // 2
        left, left_retries = _fetch_features_for_ids(object_ids[:mid])
        right, right_retries = _fetch_features_for_ids(object_ids[mid:])
        return left + right, left_retries + right_retries


def _arcgis_query(params: dict[str, str]) -> dict[str, Any]:
    payload, _ = _arcgis_query_with_retry_count(params)
    return payload


def _arcgis_query_with_retry_count(params: dict[str, str]) -> tuple[dict[str, Any], int]:
    data = urlencode({"f": "json"} | params).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(8):
        try:
            request = Request(
                f"{NFHL_FLOOD_HAZARD_ZONES}/query",
                data=data,
                headers={"User-Agent": "Groundtruth flood_sfha ingestion"},
            )
            with urlopen(request, timeout=180) as response:
                payload = json.load(response)
            if "error" in payload:
                message = payload["error"].get("message", "unknown ArcGIS error")
                raise RuntimeError(f"NFHL query failed: {message}")
            return payload, attempt
        except Exception as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def _esri_polygon_to_shape(geometry: dict[str, Any]) -> BaseGeometry | None:
    rings = geometry.get("rings") or []
    if not rings:
        return None
    polygons = [_polygon_from_ring_group(group) for group in _group_esri_rings(rings)]
    polygons = [poly for poly in polygons if poly is not None and not poly.is_empty]
    if not polygons:
        return None
    if len(polygons) == 1:
        return polygons[0]
    return MultiPolygon(polygons)


def _group_esri_rings(rings: list[list[list[float]]]) -> list[tuple[list[list[float]], list[list[list[float]]]]]:
    outers: list[list[list[float]]] = []
    holes: list[list[list[float]]] = []
    for ring in rings:
        if len(ring) < 4:
            continue
        line = LinearRing(ring)
        if line.is_ccw:
            holes.append(ring)
        else:
            outers.append(ring)
    if not outers:
        return [(ring, []) for ring in rings if len(ring) >= 4]

    grouped: list[tuple[list[list[float]], list[list[list[float]]]]] = [(outer, []) for outer in outers]
    outer_polys = [Polygon(outer) for outer in outers]
    for hole in holes:
        point = Point(hole[0])
        for idx, outer in enumerate(outer_polys):
            if outer.contains(point) or outer.touches(point):
                grouped[idx][1].append(hole)
                break
    return grouped


def _polygon_from_ring_group(
    group: tuple[list[list[float]], list[list[list[float]]]]
) -> Polygon | None:
    outer, holes = group
    polygon = Polygon(outer, holes)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty:
        return None
    if isinstance(polygon, Polygon):
        return polygon
    return max(polygon.geoms, key=lambda geom: geom.area) if hasattr(polygon, "geoms") else None


def _compute_region_metrics(
    tracts: gpd.GeoDataFrame, source: gpd.GeoDataFrame
) -> tuple[list[RegionMetric], dict[str, Any]]:
    tracts_work = tracts[["slug", "geometry"]].to_crs("EPSG:5070").copy()
    tracts_work["tract_area"] = tracts_work.geometry.area
    source_work = source[["FLD_ZONE", "geometry"]].to_crs("EPSG:5070").copy()

    intersections = gpd.overlay(
        tracts_work,
        source_work,
        how="intersection",
        keep_geom_type=False,
    )
    shares = pd.Series(0.0, index=tracts_work["slug"], dtype="float64")
    if not intersections.empty:
        intersections["sfha_area"] = intersections.geometry.area
        tract_area = tracts_work.set_index("slug")["tract_area"]
        shares = (
            intersections.groupby("slug")["sfha_area"]
            .sum()
            .div(tract_area)
            .clip(upper=1)
            .reindex(tracts_work["slug"], fill_value=0)
        )
    shares = shares.fillna(0).clip(lower=0, upper=1)

    metrics = [
        RegionMetric(region_slug=str(slug), value=float(value))
        for slug, value in shares.items()
    ]
    nonzero = shares[shares > 0]
    stats = {
        "tracts_with_sfha": int((shares > 0).sum()),
        "tract_sfha_share_mean": float(shares.mean()),
        "tract_sfha_share_p50": float(shares.quantile(0.5)),
        "tract_sfha_share_p90": float(shares.quantile(0.9)),
        "tract_sfha_share_max": float(shares.max()),
        "tract_sfha_share_min_nonzero": float(nonzero.min()) if not nonzero.empty else 0.0,
        "overlay_rows": int(len(intersections)),
    }
    return metrics, stats


def _compute_listing_metrics(
    listings: gpd.GeoDataFrame, source: gpd.GeoDataFrame
) -> tuple[list[ListingMetric], dict[str, Any]]:
    if source.empty:
        flooded_ids: set[int] = set()
    else:
        joined = gpd.sjoin(
            listings[["id", "geometry"]],
            source[["FLD_ZONE", "geometry"]],
            how="left",
            predicate="within",
        )
        flooded_ids = set(int(value) for value in joined.dropna(subset=["FLD_ZONE"])["id"].unique())
    metrics = [
        ListingMetric(listing_id=int(row.id), value=1.0 if int(row.id) in flooded_ids else 0.0)
        for row in listings.itertuples()
    ]
    return metrics, {
        "listing_point_sfha": len(flooded_ids),
        "listing_point_sfha_share": len(flooded_ids) / len(listings) if len(listings) else 0,
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
            (
                region_slug,
                manifest.metric_key,
                metric.listing_id,
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
    fetch_stats: FetchStats,
    region_stats: dict[str, Any],
    listing_stats: dict[str, Any],
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
        SELECT count(*)
        FROM staging.layer_region_metrics
        WHERE region_group = %s
          AND metric_key = %s
          AND vintage = %s
          AND value::text = 'NaN'
        """,
        (region_slug, manifest.metric_key, manifest.vintage),
    )
    tract_nonfinite = int(cur.fetchone()[0])
    cur.execute(
        """
        SELECT count(*), coalesce(min(value), 0), coalesce(max(value), 0), coalesce(sum(value), 0)
        FROM staging.layer_listing_metrics
        WHERE region_group = %s
          AND metric_key = %s
          AND vintage = %s
          AND grain = 'point'
        """,
        (region_slug, manifest.metric_key, manifest.vintage),
    )
    listing_count, listing_min, listing_max, listing_sum = cur.fetchone()
    cur.execute(
        """
        SELECT count(*)
        FROM staging.layer_listing_metrics
        WHERE region_group = %s
          AND metric_key = %s
          AND vintage = %s
          AND grain = 'point'
          AND value::text = 'NaN'
        """,
        (region_slug, manifest.metric_key, manifest.vintage),
    )
    listing_nonfinite = int(cur.fetchone()[0])
    value_bounds = [float(region_min), float(region_max), float(listing_min), float(listing_max)]
    finite_value_bounds = [value for value in value_bounds if math.isfinite(value)]
    return {
        "metric_key": manifest.metric_key,
        "region": region_slug,
        "grain": grain,
        "tracts_expected": expected_tracts,
        "tracts_computed": int(tract_count),
        "tract_coverage": int(tract_count) / expected_tracts if expected_tracts else 0,
        "tract_nonfinite": tract_nonfinite,
        "listings_expected": expected_listings,
        "listing_point_computed": int(listing_count),
        "listing_point_coverage": int(listing_count) / expected_listings if expected_listings else 0,
        "listing_point_nonfinite": listing_nonfinite,
        "listing_buffer_100m_computed": 0,
        "listing_buffer_100m_coverage": 0,
        "listing_buffer_500m_computed": 0,
        "listing_buffer_500m_coverage": 0,
        "listing_point_positive": int(listing_sum),
        "range_allowed": list(manifest.allowed_range),
        "range_min": min(finite_value_bounds) if finite_value_bounds else float("nan"),
        "range_max": max(finite_value_bounds) if finite_value_bounds else float("nan"),
        "source_object_ids": fetch_stats.object_ids,
        "source_features_fetched": fetch_stats.features,
        "source_chunks_read": fetch_stats.chunks_read,
        "source_chunks_fetched": fetch_stats.chunks_fetched,
        "source_chunk_retries": fetch_stats.chunk_retries,
        "source_zone_counts": fetch_stats.zone_counts,
    } | region_stats | listing_stats
