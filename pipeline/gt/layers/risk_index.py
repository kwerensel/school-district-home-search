from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen
import json

import psycopg

from gt.db.migrate import database_url
from gt.manifests import LayerManifest, RegionManifest, load_layer_manifest, load_region_manifest
from gt.reports import ValidationReport, write_report

NRI_TRACT_SERVICE = (
    "https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/"
    "National_Risk_Index_Census_Tracts/FeatureServer/0"
)
NRI_FIELDS = [
    "NRI_ID",
    "STATEABBRV",
    "STCOFIPS",
    "TRACTFIPS",
    "RISK_SCORE",
    "RISK_SPCTL",
    "RISK_RATNG",
    "EAL_SCORE",
    "EAL_SPCTL",
    "SOVI_SCORE",
    "RESL_SCORE",
]


@dataclass(frozen=True)
class RiskMetric:
    region_slug: str
    value: float
    rating: str | None


def run_risk_index(manifest_path: Path, region_slug: str, grain: str) -> tuple[ValidationReport, Path]:
    manifest = load_layer_manifest(manifest_path)
    if manifest.metric_key != "risk_index":
        raise ValueError(f"Unsupported risk index manifest metric: {manifest.metric_key}")
    if grain not in {"tract", "both"}:
        raise ValueError("risk_index supports tract grain only")

    region_manifest = load_region_manifest(Path("manifests") / "regions" / f"{region_slug}.yaml")
    with psycopg.connect(database_url(), autocommit=False) as conn:
        with conn.cursor() as cur:
            local_tracts = _local_tracts(cur, region_slug)
            if not local_tracts:
                raise RuntimeError(f"No census tract regions found for {region_slug}")
            source_rows = _fetch_nri_rows(region_manifest)
            metrics = _join_metrics(local_tracts, source_rows)
            _clear_staging(cur, region_slug, manifest.metric_key)
            _stage_region_metrics(cur, region_slug, manifest, metrics)
            checks = _validation_checks(cur, region_slug, manifest, grain, metrics)
        conn.commit()

    range_min, range_max = manifest.allowed_range
    promotable = (
        checks["range_min"] >= range_min
        and checks["range_max"] <= range_max
        and checks["tract_coverage"] >= manifest.coverage_threshold
        and checks["nri_rows_duplicate_tracts"] == 0
        and checks["nri_rows_missing_risk_score"] == 0
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


def _local_tracts(cur: psycopg.Cursor[Any], region_slug: str) -> dict[str, str]:
    cur.execute(
        """
        SELECT source_id, slug
        FROM regions
        WHERE region_group = %s
          AND region_type = 'census_tract'
        ORDER BY source_id
        """,
        (region_slug,),
    )
    return {str(source_id): str(slug) for source_id, slug in cur.fetchall()}


def _fetch_nri_rows(region_manifest: RegionManifest) -> dict[str, dict[str, Any]]:
    where = " OR ".join(f"STCOFIPS='{county}'" for county in region_manifest.counties)
    params = {
        "f": "json",
        "where": where,
        "outFields": ",".join(NRI_FIELDS),
        "returnGeometry": "false",
        "resultRecordCount": "2000",
        "orderByFields": "STCOFIPS,TRACTFIPS",
    }
    with urlopen(f"{NRI_TRACT_SERVICE}/query?{urlencode(params)}", timeout=60) as response:
        payload = json.load(response)
    if "error" in payload:
        message = payload["error"].get("message", "unknown ArcGIS error")
        raise RuntimeError(f"NRI service query failed: {message}")
    if payload.get("exceededTransferLimit"):
        raise RuntimeError("NRI service query exceeded transfer limit; add pagination before ingest")

    rows: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    for feature in payload.get("features", []):
        attrs = feature.get("attributes") or {}
        tract_fips = attrs.get("TRACTFIPS")
        if not tract_fips:
            continue
        if tract_fips in rows:
            duplicates.add(str(tract_fips))
        rows[str(tract_fips)] = attrs
    if duplicates:
        sample = ", ".join(sorted(duplicates)[:5])
        raise RuntimeError(f"NRI service returned duplicate tract rows: {sample}")
    return rows


def _join_metrics(
    local_tracts: dict[str, str], source_rows: dict[str, dict[str, Any]]
) -> list[RiskMetric]:
    missing = sorted(set(local_tracts) - set(source_rows))
    if missing:
        sample = ", ".join(missing[:5])
        raise RuntimeError(f"Missing NRI rows for local tract source_ids: {sample}")
    metrics: list[RiskMetric] = []
    for source_id, slug in local_tracts.items():
        row = source_rows[source_id]
        value = row.get("RISK_SCORE")
        if value is None:
            raise RuntimeError(f"NRI row has null RISK_SCORE for tract {source_id}")
        metrics.append(RiskMetric(region_slug=slug, value=float(value), rating=row.get("RISK_RATNG")))
    return metrics


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
    metrics: list[RiskMetric],
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
    metrics: list[RiskMetric],
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
    rating_counts: dict[str, int] = {}
    for metric in metrics:
        if metric.rating:
            rating_counts[metric.rating] = rating_counts.get(metric.rating, 0) + 1
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
        "nri_rows_fetched": len(metrics),
        "nri_rows_duplicate_tracts": 0,
        "nri_rows_missing_risk_score": 0,
        "risk_rating_counts": rating_counts,
    }
