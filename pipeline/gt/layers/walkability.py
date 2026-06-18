from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen
import json

import geopandas as gpd
import pandas as pd
import psycopg
from shapely.geometry import LinearRing, MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry

from gt.db.migrate import database_url
from gt.manifests import LayerManifest, RegionManifest, load_layer_manifest, load_region_manifest
from gt.reports import ValidationReport, write_report

NWI_SERVICE = "https://geodata.epa.gov/arcgis/rest/services/OA/WalkabilityIndex/MapServer/0"
NWI_FIELDS = [
    "OBJECTID",
    "NatWalkInd",
    "CountHU",
    "HH",
    "GEOID10",
    "GEOID20",
    "STATEFP",
    "COUNTYFP",
    "TRACTCE",
    "BLKGRPCE",
]


@dataclass(frozen=True)
class RegionMetric:
    region_slug: str
    value: float


@dataclass(frozen=True)
class ListingMetric:
    listing_id: int
    value: float


def run_walkability(manifest_path: Path, region_slug: str, grain: str) -> tuple[ValidationReport, Path]:
    manifest = load_layer_manifest(manifest_path)
    if manifest.metric_key != "walkability_index":
        raise ValueError(f"Unsupported walkability manifest metric: {manifest.metric_key}")
    if grain not in {"tract", "listing", "both"}:
        raise ValueError("grain must be tract, listing, or both")

    region_manifest = load_region_manifest(Path("manifests") / "regions" / f"{region_slug}.yaml")
    with psycopg.connect(database_url(), autocommit=True) as conn:
        tracts = _read_tracts(conn, region_slug)
        listings = _read_listings(conn, region_slug)
    if tracts.empty:
        raise RuntimeError(f"No census tract regions found for {region_slug}")
    if listings.empty:
        raise RuntimeError(f"No frozen listings found for {region_slug}")

    source = _fetch_nwi_block_groups(region_manifest)
    source = _clean_source(source, manifest)

    region_metrics: list[RegionMetric] = []
    listing_metrics: list[ListingMetric] = []
    overlap_stats: dict[str, Any] = {}
    listing_stats: dict[str, Any] = {}
    if grain in {"tract", "both"}:
        region_metrics, overlap_stats = _compute_region_metrics(tracts, source)
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
                source,
                overlap_stats,
                listing_stats,
            )
        conn.commit()

    range_min, range_max = manifest.allowed_range
    needs_tract = grain in {"tract", "both"}
    needs_listing = grain in {"listing", "both"}
    promotable = (
        checks["range_min"] >= range_min
        and checks["range_max"] <= range_max
        and (not needs_tract or checks["tract_coverage"] >= manifest.coverage_threshold)
        and (not needs_listing or checks["listing_point_coverage"] >= manifest.coverage_threshold)
        and checks["source_rows_missing_score"] == 0
        and checks["source_rows_missing_weight"] == 0
        and checks["source_duplicate_geoids"] == 0
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
        SELECT id, slug, source_id, geom AS geometry
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


def _fetch_nwi_block_groups(region_manifest: RegionManifest) -> gpd.GeoDataFrame:
    frames = [_fetch_county_block_groups(county_fips) for county_fips in region_manifest.counties]
    frame = pd.concat(frames, ignore_index=True)
    return gpd.GeoDataFrame(frame, geometry="geometry", crs="EPSG:4326")


def _fetch_county_block_groups(county_fips: str) -> gpd.GeoDataFrame:
    rows: list[dict[str, Any]] = []
    offset = 0
    page_size = 2000
    while True:
        params = {
            "f": "json",
            "where": f"STATEFP='{county_fips[:2]}' AND COUNTYFP='{county_fips[2:]}'",
            "outFields": ",".join(NWI_FIELDS),
            "returnGeometry": "true",
            "outSR": "4326",
            "resultRecordCount": str(page_size),
            "resultOffset": str(offset),
            "orderByFields": "GEOID20,OBJECTID",
        }
        with urlopen(f"{NWI_SERVICE}/query?{urlencode(params)}", timeout=120) as response:
            payload = json.load(response)
        if "error" in payload:
            message = payload["error"].get("message", "unknown ArcGIS error")
            raise RuntimeError(f"NWI service query failed for {county_fips}: {message}")

        features = payload.get("features", [])
        for feature in features:
            attrs = feature.get("attributes") or {}
            geometry = _esri_polygon_to_shape(feature.get("geometry") or {})
            if geometry is None or geometry.is_empty:
                continue
            rows.append(attrs | {"geometry": geometry})

        if len(features) < page_size and not payload.get("exceededTransferLimit"):
            break
        offset += page_size

    if not rows:
        raise RuntimeError(f"NWI service returned no block groups for county {county_fips}")
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


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


def _clean_source(source: gpd.GeoDataFrame, manifest: LayerManifest) -> gpd.GeoDataFrame:
    frame = source.copy()
    frame["score"] = pd.to_numeric(frame["NatWalkInd"], errors="coerce")
    frame["count_hu"] = pd.to_numeric(frame.get("CountHU"), errors="coerce")
    frame["hh"] = pd.to_numeric(frame.get("HH"), errors="coerce")
    frame["weight"] = frame["count_hu"].where(frame["count_hu"].notna(), frame["hh"])
    missing_score = frame["score"].isna()
    missing_weight = frame["weight"].isna()
    if missing_score.any():
        raise RuntimeError(f"NWI rows missing NatWalkInd: {int(missing_score.sum())}")
    if missing_weight.any():
        raise RuntimeError(f"NWI rows missing CountHU/HH weight: {int(missing_weight.sum())}")
    range_min, range_max = manifest.allowed_range
    out_of_range = ~frame["score"].between(range_min, range_max)
    if out_of_range.any():
        raise RuntimeError(f"NWI rows outside allowed score range: {int(out_of_range.sum())}")
    frame["weight"] = frame["weight"].clip(lower=0)
    frame["source_geoid"] = frame["GEOID20"].fillna(frame["GEOID10"]).map(_clean_code)
    if frame["source_geoid"].duplicated().any():
        duplicates = sorted(frame.loc[frame["source_geoid"].duplicated(), "source_geoid"].unique())
        sample = ", ".join(duplicates[:5])
        raise RuntimeError(f"NWI service returned duplicate source GEOIDs: {sample}")
    return frame


def _compute_region_metrics(
    tracts: gpd.GeoDataFrame, source: gpd.GeoDataFrame
) -> tuple[list[RegionMetric], dict[str, Any]]:
    tracts_work = tracts[["slug", "source_id", "geometry"]].to_crs("EPSG:5070").copy()
    source_work = source[["source_geoid", "score", "weight", "geometry"]].to_crs("EPSG:5070").copy()
    source_work["source_area"] = source_work.geometry.area
    direct_tracts = _direct_tract_values(tracts, source)

    intersections = gpd.overlay(
        tracts_work,
        source_work,
        how="intersection",
        keep_geom_type=False,
    )
    if intersections.empty:
        raise RuntimeError("NWI block groups did not overlap local census tracts")
    intersections["intersection_area"] = intersections.geometry.area
    intersections = intersections[
        (intersections["source_area"] > 0) & (intersections["intersection_area"] > 0)
    ].copy()
    intersections["distributed_weight"] = (
        intersections["weight"]
        * intersections["intersection_area"]
        / intersections["source_area"]
    )
    intersections["weighted_score"] = intersections["score"] * intersections["distributed_weight"]
    grouped = intersections.groupby("slug", as_index=False).agg(
        weighted_score=("weighted_score", "sum"),
        distributed_weight=("distributed_weight", "sum"),
    )
    grouped = grouped[grouped["distributed_weight"] > 0].copy()
    grouped["value"] = grouped["weighted_score"] / grouped["distributed_weight"]

    metrics = [
        RegionMetric(region_slug=str(row.slug), value=float(row.value))
        for row in grouped.itertuples()
    ]
    computed = {metric.region_slug for metric in metrics}
    expected = set(str(slug) for slug in tracts["slug"])
    direct_computed = set(direct_tracts)
    expected_source_ids = set(str(value) for value in tracts["source_id"])
    missing = sorted(expected - computed)
    if missing:
        sample = ", ".join(missing[:5])
        raise RuntimeError(f"Missing NWI overlap coverage for tract slugs: {sample}")
    stats = {
        "direct_tract_join_computed": len(direct_computed),
        "overlap_tracts_requiring_fallback": len(expected_source_ids - direct_computed),
        "source_block_groups_overlapped": int(intersections["source_geoid"].nunique()),
        "source_block_groups_zero_overlap": int(len(set(source["source_geoid"]) - set(intersections["source_geoid"]))),
        "overlap_rows": int(len(intersections)),
    }
    return metrics, stats


def _direct_tract_values(tracts: gpd.GeoDataFrame, source: gpd.GeoDataFrame) -> set[str]:
    direct = source.copy()
    direct["tract_fips"] = (
        direct["STATEFP"].map(lambda value: _clean_code(value, width=2))
        + direct["COUNTYFP"].map(lambda value: _clean_code(value, width=3))
        + direct["TRACTCE"].map(lambda value: _clean_code(value, width=6))
    )
    direct = direct[direct["weight"] > 0].copy()
    grouped = direct.groupby("tract_fips").agg(weight=("weight", "sum"))
    tract_source_ids = set(str(value) for value in tracts["source_id"])
    return set(grouped[grouped["weight"] > 0].index).intersection(tract_source_ids)


def _clean_code(value: Any, width: int | None = None) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(width) if width else text


def _compute_listing_metrics(
    listings: gpd.GeoDataFrame, source: gpd.GeoDataFrame
) -> tuple[list[ListingMetric], dict[str, Any]]:
    joined = gpd.sjoin(
        listings[["id", "geometry"]],
        source[["source_geoid", "score", "geometry"]],
        how="left",
        predicate="within",
    )
    joined = joined.dropna(subset=["score"]).drop_duplicates(subset=["id"])
    expected = set(int(value) for value in listings["id"])
    seen = set(int(value) for value in joined["id"])
    unmatched = sorted(expected - seen)
    metrics = [
        ListingMetric(listing_id=int(row.id), value=float(row.score))
        for row in joined.itertuples()
    ]
    stats = {
        "listing_unmatched_ids": unmatched[:50],
        "listing_unmatched_count": len(unmatched),
        "listing_source_block_groups": int(joined["source_geoid"].nunique()) if not joined.empty else 0,
    }
    return metrics, stats


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
    source: gpd.GeoDataFrame,
    overlap_stats: dict[str, Any],
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
        SELECT count(*), coalesce(min(value), 0), coalesce(max(value), 0)
        FROM staging.layer_listing_metrics
        WHERE region_group = %s
          AND metric_key = %s
          AND vintage = %s
          AND grain = 'point'
        """,
        (region_slug, manifest.metric_key, manifest.vintage),
    )
    listing_count, listing_min, listing_max = cur.fetchone()
    value_bounds: list[float] = []
    if int(tract_count):
        value_bounds.extend([float(region_min), float(region_max)])
    if int(listing_count):
        value_bounds.extend([float(listing_min), float(listing_max)])
    if not value_bounds:
        value_bounds = [0.0]
    duplicate_geoids = int(source["source_geoid"].duplicated().sum())
    missing_score = int(source["score"].isna().sum())
    missing_weight = int(source["weight"].isna().sum())
    return {
        "metric_key": manifest.metric_key,
        "region": region_slug,
        "grain": grain,
        "tracts_expected": expected_tracts,
        "tracts_computed": int(tract_count),
        "tract_coverage": int(tract_count) / expected_tracts if expected_tracts else 0,
        "listings_expected": expected_listings,
        "listing_point_computed": int(listing_count),
        "listing_point_coverage": int(listing_count) / expected_listings if expected_listings else 0,
        "listing_buffer_100m_computed": 0,
        "listing_buffer_100m_coverage": 0,
        "listing_buffer_500m_computed": 0,
        "listing_buffer_500m_coverage": 0,
        "range_allowed": list(manifest.allowed_range),
        "range_min": min(value_bounds),
        "range_max": max(value_bounds),
        "source_rows_fetched": int(len(source)),
        "source_rows_missing_score": missing_score,
        "source_rows_missing_weight": missing_weight,
        "source_duplicate_geoids": duplicate_geoids,
        "source_score_min": float(source["score"].min()),
        "source_score_mean": float(source["score"].mean()),
        "source_score_max": float(source["score"].max()),
        "source_weight_field": "CountHU with HH fallback",
    } | overlap_stats | listing_stats
