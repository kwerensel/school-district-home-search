from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import urlretrieve
import csv

import psycopg

from gt.db.migrate import database_url, repo_root
from gt.manifests import LayerManifest, load_layer_manifest
from gt.reports import ValidationReport, write_report

ACS_BASE_URL = "https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData"
ACS_TABLES = {
    "taxes": ("acsdt5y2024-b25103.dat", "B25103_E001"),
    "values": ("acsdt5y2024-b25077.dat", "B25077_E001"),
}


@dataclass(frozen=True)
class TaxMetric:
    region_slug: str
    value: float


@dataclass(frozen=True)
class SourceStats:
    source_regions_expected: int
    source_regions_with_tax: int
    source_regions_with_value: int
    source_regions_valid: int
    source_regions_invalid: int
    missing_source_ids: list[str]
    invalid_source_ids: list[str]


def run_effective_tax_rate(
    manifest_path: Path, region_slug: str, grain: str
) -> tuple[ValidationReport, Path]:
    manifest = load_layer_manifest(manifest_path)
    if manifest.metric_key != "effective_tax_rate":
        raise ValueError(f"Unsupported effective tax manifest metric: {manifest.metric_key}")
    if grain not in {"tract", "both"}:
        raise ValueError("effective_tax_rate supports tract grain only")

    paths = _ensure_source_files()
    with psycopg.connect(database_url(), autocommit=False) as conn:
        with conn.cursor() as cur:
            source_ids = _county_subdivision_source_ids(cur, region_slug)
            rates, source_stats = _read_source_rates(paths, source_ids)
            metrics = _compute_tract_metrics(cur, region_slug, rates)
            _clear_staging(cur, region_slug, manifest.metric_key)
            _stage_region_metrics(cur, region_slug, manifest, metrics)
            checks = _validation_checks(cur, region_slug, manifest, grain, metrics, source_stats)
        conn.commit()

    range_min, range_max = manifest.allowed_range
    promotable = (
        checks["range_min"] >= range_min
        and checks["range_max"] <= range_max
        and checks["tract_coverage"] >= manifest.coverage_threshold
        and checks["source_regions_invalid"] == 0
        and checks["missing_source_region_count"] == 0
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


def _ensure_source_files() -> dict[str, Path]:
    raw_dir = repo_root() / "data" / "raw" / "acs" / "2024" / "table-based-SF"
    raw_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for key, (filename, _field) in ACS_TABLES.items():
        path = raw_dir / filename
        if not path.exists():
            urlretrieve(f"{ACS_BASE_URL}/{filename}", path)
        paths[key] = path
    return paths


def _county_subdivision_source_ids(cur: psycopg.Cursor[Any], region_slug: str) -> list[str]:
    cur.execute(
        """
        SELECT source_id
        FROM regions
        WHERE region_group = %s
          AND region_type = 'municipality'
          AND slug LIKE 'mun-cousub-%%'
        ORDER BY source_id
        """,
        (region_slug,),
    )
    return [str(row[0]) for row in cur.fetchall()]


def _read_source_rates(paths: dict[str, Path], source_ids: list[str]) -> tuple[dict[str, float], SourceStats]:
    source_set = set(source_ids)
    taxes = _read_acs_values(paths["taxes"], ACS_TABLES["taxes"][1], source_set)
    values = _read_acs_values(paths["values"], ACS_TABLES["values"][1], source_set)
    rates: dict[str, float] = {}
    invalid_source_ids: list[str] = []
    for source_id in source_ids:
        tax = taxes.get(source_id)
        value = values.get(source_id)
        if tax is None or value is None or tax < 0 or value <= 0:
            invalid_source_ids.append(source_id)
            continue
        rates[source_id] = tax / value

    missing_source_ids = sorted(source_set - (set(taxes) & set(values)))
    return rates, SourceStats(
        source_regions_expected=len(source_ids),
        source_regions_with_tax=len(taxes),
        source_regions_with_value=len(values),
        source_regions_valid=len(rates),
        source_regions_invalid=len(invalid_source_ids),
        missing_source_ids=missing_source_ids,
        invalid_source_ids=invalid_source_ids,
    )


def _read_acs_values(path: Path, field: str, source_ids: set[str]) -> dict[str, float]:
    values: dict[str, float] = {}
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="|")
        for row in reader:
            source_id = _source_id_from_geo_id(row["GEO_ID"])
            if source_id not in source_ids:
                continue
            value = row.get(field)
            if value is None or value == "":
                continue
            values[source_id] = float(value)
            if len(values) == len(source_ids):
                break
    return values


def _source_id_from_geo_id(geo_id: str) -> str:
    return geo_id.rsplit("US", 1)[-1]


def _compute_tract_metrics(
    cur: psycopg.Cursor[Any], region_slug: str, rates: dict[str, float]
) -> list[TaxMetric]:
    cur.execute(
        """
        SELECT child.slug, parent.source_id, ro.area_weight
        FROM region_overlaps ro
        JOIN regions child ON child.id = ro.child_region_id
        JOIN regions parent ON parent.id = ro.parent_region_id
        WHERE child.region_group = %s
          AND child.region_type = 'census_tract'
          AND parent.region_type = 'municipality'
          AND parent.slug LIKE 'mun-cousub-%%'
        ORDER BY child.slug, parent.source_id
        """,
        (region_slug,),
    )
    tract_weighted: dict[str, float] = {}
    tract_weights: dict[str, float] = {}
    for tract_slug, source_id, weight in cur.fetchall():
        rate = rates.get(str(source_id))
        if rate is None:
            continue
        tract_slug = str(tract_slug)
        weight = float(weight)
        tract_weighted[tract_slug] = tract_weighted.get(tract_slug, 0.0) + rate * weight
        tract_weights[tract_slug] = tract_weights.get(tract_slug, 0.0) + weight

    metrics: list[TaxMetric] = []
    for tract_slug in sorted(tract_weighted):
        weight_sum = tract_weights[tract_slug]
        if weight_sum <= 0:
            continue
        metrics.append(TaxMetric(region_slug=tract_slug, value=tract_weighted[tract_slug] / weight_sum))
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
    metrics: list[TaxMetric],
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
    metrics: list[TaxMetric],
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
    values = sorted(metric.value for metric in metrics)
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
        "rate_mean": sum(values) / len(values) if values else 0,
        "rate_p50": _percentile(values, 0.5),
        "rate_p90": _percentile(values, 0.9),
        "source_regions_expected": source_stats.source_regions_expected,
        "source_regions_with_tax": source_stats.source_regions_with_tax,
        "source_regions_with_value": source_stats.source_regions_with_value,
        "source_regions_valid": source_stats.source_regions_valid,
        "source_regions_invalid": source_stats.source_regions_invalid,
        "missing_source_region_count": len(source_stats.missing_source_ids),
        "missing_source_region_sample": source_stats.missing_source_ids[:10],
        "invalid_source_region_sample": source_stats.invalid_source_ids[:10],
    }


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    index = q * (len(values) - 1)
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    fraction = index - lower
    return values[lower] * (1 - fraction) + values[upper] * fraction
