from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zipfile import ZipFile
import csv

import psycopg

from gt.db.migrate import database_url, repo_root
from gt.manifests import LayerManifest, load_layer_manifest
from gt.reports import ValidationReport, write_report

ZCTA_BLOCK_REL = repo_root() / "data" / "raw" / "census" / "tab20_zcta520_tabblock20_natl.txt"
PL_PATHS = {
    "36": (
        repo_root() / "data" / "raw" / "census" / "pl2020" / "ny2020.pl.zip",
        "nygeo2020.pl",
        "ny000022020.pl",
    ),
    "42": (
        repo_root() / "data" / "raw" / "census" / "pl2020" / "pa2020.pl.zip",
        "pageo2020.pl",
        "pa000022020.pl",
    ),
}
ZHVI_PATH = repo_root() / "data" / "raw" / "Zip_zhvi_uc_sfr_tier_0.33_0.67_sm_sa_month.csv"
ACS_B25077_PATH = repo_root() / "data" / "raw" / "acs" / "2024" / "table-based-SF" / "acsdt5y2024-b25077.dat"

PL_SUMLEV_BLOCK = "750"
PL_GEO_LOGRECNO = 7
PL_GEO_BLOCK_GEOID = 9
PL_GEO_UNIFIED_SCHOOL_DISTRICT = 82
PL_SEG_LOGRECNO = 4
PL_SEG_H1_TOTAL = -3


@dataclass(frozen=True)
class DistrictMetric:
    region_slug: str
    value: float


@dataclass(frozen=True)
class DistrictSource:
    slug: str
    source_id: str
    state_fips: str


@dataclass(frozen=True)
class BlockAssignment:
    district_slug: str
    housing_units: float


@dataclass(frozen=True)
class SourceValue:
    value: float
    source: str


@dataclass(frozen=True)
class CrosswalkStats:
    zcta_count: int
    zcta_district_rows: int
    block_rows_matched: int
    housing_units_total: float
    zillow_housing_units: float
    acs_housing_units: float
    missing_value_housing_units: float


def run_median_home_value(
    manifest_path: Path, region_slug: str, grain: str
) -> tuple[ValidationReport, Path]:
    manifest = load_layer_manifest(manifest_path)
    if manifest.metric_key != "median_home_value":
        raise ValueError(f"Unsupported median home value manifest metric: {manifest.metric_key}")
    if grain not in {"tract", "both"}:
        raise ValueError("median_home_value supports regional grain only")

    _require_sources()
    with psycopg.connect(database_url(), autocommit=False) as conn:
        with conn.cursor() as cur:
            districts = _read_district_sources(cur, region_slug)
            if not districts:
                raise RuntimeError(f"No school-district regions found for {region_slug}")

            zcta_values, latest_vintage = _read_zcta_values()
            if latest_vintage != manifest.vintage.removesuffix("-zhvi"):
                raise RuntimeError(
                    f"Manifest vintage {manifest.vintage} does not match latest ZHVI {latest_vintage}"
                )
            acs_values = _read_acs_zcta_values()
            block_assignments = _read_block_assignments(districts)
            zcta_district_hu, stats = _read_zcta_district_housing(
                block_assignments,
                zcta_values,
                acs_values,
            )
            metrics = _compute_district_metrics(zcta_district_hu, zcta_values, acs_values)
            _write_crosswalk_artifact(region_slug, zcta_district_hu)
            _clear_staging(cur, region_slug, manifest.metric_key)
            _stage_region_metrics(cur, region_slug, manifest, metrics)
            checks = _validation_checks(cur, region_slug, manifest, grain, metrics, stats)
        conn.commit()

    range_min, range_max = manifest.allowed_range
    promotable = (
        checks["district_coverage"] >= manifest.coverage_threshold
        and checks["range_min"] >= range_min
        and checks["range_max"] <= range_max
        and checks["missing_value_hu_share"] <= 0.01
        and checks["zcta_district_rows"] > 0
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


def _require_sources() -> None:
    missing = [
        path
        for path in [ZCTA_BLOCK_REL, ZHVI_PATH, ACS_B25077_PATH, *(path for path, _, _ in PL_PATHS.values())]
        if not path.exists()
    ]
    if missing:
        raise FileNotFoundError("Missing median_home_value source files: " + ", ".join(map(str, missing)))


def _read_district_sources(cur: psycopg.Cursor[Any], region_slug: str) -> list[DistrictSource]:
    cur.execute(
        """
        SELECT slug, source_id, state
        FROM regions
        WHERE region_group = %s
          AND region_type = 'school_district'
          AND source_id IS NOT NULL
        ORDER BY source_id
        """,
        (region_slug,),
    )
    return [
        DistrictSource(slug=str(slug), source_id=str(source_id), state_fips=_state_fips(str(state)))
        for slug, source_id, state in cur.fetchall()
    ]


def _state_fips(state: str) -> str:
    if state == "NY":
        return "36"
    if state == "PA":
        return "42"
    raise ValueError(f"Unsupported state abbreviation for median_home_value: {state}")


def _read_zcta_values() -> tuple[dict[str, SourceValue], str]:
    with ZHVI_PATH.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise RuntimeError(f"{ZHVI_PATH} has no header")
        date_columns = [field for field in reader.fieldnames if field[:4].isdigit()]
        if not date_columns:
            raise RuntimeError(f"{ZHVI_PATH} has no date columns")
        latest = date_columns[-1]
        values: dict[str, SourceValue] = {}
        for row in reader:
            raw = row.get(latest)
            zcta = _normalize_zcta(row.get("RegionName", ""))
            if not zcta or not raw:
                continue
            value = _safe_float(raw)
            if value is None or value <= 0:
                continue
            values[zcta] = SourceValue(value=value, source="zillow_zhvi")
    return values, latest


def _read_acs_zcta_values() -> dict[str, SourceValue]:
    values: dict[str, SourceValue] = {}
    with ACS_B25077_PATH.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="|")
        for row in reader:
            geo_id = row.get("GEO_ID", "")
            if not geo_id.startswith("860Z200US"):
                continue
            zcta = _normalize_zcta(geo_id.rsplit("US", 1)[-1])
            value = _safe_float(row.get("B25077_E001", ""))
            if zcta and value is not None and value > 0:
                values[zcta] = SourceValue(value=value, source="acs_b25077")
    return values


def _read_block_assignments(districts: list[DistrictSource]) -> dict[str, BlockAssignment]:
    by_state: dict[str, dict[str, str]] = {}
    for district in districts:
        by_state.setdefault(district.state_fips, {})[district.source_id] = district.slug

    assignments: dict[str, BlockAssignment] = {}
    for state_fips, district_slug_by_source in by_state.items():
        pl_path, geo_name, seg2_name = PL_PATHS[state_fips]
        housing_by_logrecno = _read_housing_units(pl_path, seg2_name)
        with ZipFile(pl_path) as archive, archive.open(geo_name) as handle:
            for raw in handle:
                parts = raw.decode("latin1").rstrip("\n").split("|")
                if len(parts) <= PL_GEO_UNIFIED_SCHOOL_DISTRICT or parts[2] != PL_SUMLEV_BLOCK:
                    continue
                source_id = state_fips + parts[PL_GEO_UNIFIED_SCHOOL_DISTRICT]
                district_slug = district_slug_by_source.get(source_id)
                if district_slug is None:
                    continue
                housing_units = housing_by_logrecno.get(parts[PL_GEO_LOGRECNO], 0)
                if housing_units <= 0:
                    continue
                assignments[parts[PL_GEO_BLOCK_GEOID]] = BlockAssignment(
                    district_slug=district_slug,
                    housing_units=float(housing_units),
                )
    return assignments


def _read_housing_units(pl_path: Path, seg2_name: str) -> dict[str, int]:
    values: dict[str, int] = {}
    with ZipFile(pl_path) as archive, archive.open(seg2_name) as handle:
        for raw in handle:
            parts = raw.decode("latin1").rstrip("\n").split("|")
            if len(parts) < 8:
                continue
            value = _safe_int(parts[PL_SEG_H1_TOTAL])
            if value is not None:
                values[parts[PL_SEG_LOGRECNO]] = value
    return values


def _read_zcta_district_housing(
    block_assignments: dict[str, BlockAssignment],
    zcta_values: dict[str, SourceValue],
    acs_values: dict[str, SourceValue],
) -> tuple[dict[tuple[str, str], float], CrosswalkStats]:
    zcta_district_hu: dict[tuple[str, str], float] = {}
    zctas: set[str] = set()
    block_rows_matched = 0
    housing_units_total = 0.0
    zillow_housing_units = 0.0
    acs_housing_units = 0.0
    missing_value_housing_units = 0.0

    with ZCTA_BLOCK_REL.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="|")
        for row in reader:
            zcta = _normalize_zcta(row.get("GEOID_ZCTA5_20", ""))
            block_geoid = row.get("GEOID_TABBLOCK_20", "")
            if not zcta or not block_geoid:
                continue
            assignment = block_assignments.get(block_geoid)
            if assignment is None:
                continue

            allocation = _block_part_allocation(row)
            if allocation <= 0:
                continue
            housing_units = assignment.housing_units * allocation
            if housing_units <= 0:
                continue

            key = (zcta, assignment.district_slug)
            zcta_district_hu[key] = zcta_district_hu.get(key, 0.0) + housing_units
            zctas.add(zcta)
            block_rows_matched += 1
            housing_units_total += housing_units
            if zcta in zcta_values:
                zillow_housing_units += housing_units
            elif zcta in acs_values:
                acs_housing_units += housing_units
            else:
                missing_value_housing_units += housing_units

    return zcta_district_hu, CrosswalkStats(
        zcta_count=len(zctas),
        zcta_district_rows=len(zcta_district_hu),
        block_rows_matched=block_rows_matched,
        housing_units_total=housing_units_total,
        zillow_housing_units=zillow_housing_units,
        acs_housing_units=acs_housing_units,
        missing_value_housing_units=missing_value_housing_units,
    )


def _block_part_allocation(row: dict[str, str]) -> float:
    block_land = _safe_float(row.get("AREALAND_TABBLOCK_20", "")) or 0.0
    part_land = _safe_float(row.get("AREALAND_PART", "")) or 0.0
    if block_land > 0:
        return min(max(part_land / block_land, 0.0), 1.0)
    block_area = block_land + (_safe_float(row.get("AREAWATER_TABBLOCK_20", "")) or 0.0)
    part_area = part_land + (_safe_float(row.get("AREAWATER_PART", "")) or 0.0)
    if block_area <= 0:
        return 0.0
    return min(max(part_area / block_area, 0.0), 1.0)


def _compute_district_metrics(
    zcta_district_hu: dict[tuple[str, str], float],
    zcta_values: dict[str, SourceValue],
    acs_values: dict[str, SourceValue],
) -> list[DistrictMetric]:
    weighted: dict[str, float] = {}
    weights: dict[str, float] = {}
    for (zcta, district_slug), housing_units in zcta_district_hu.items():
        source_value = zcta_values.get(zcta) or acs_values.get(zcta)
        if source_value is None:
            continue
        weighted[district_slug] = weighted.get(district_slug, 0.0) + source_value.value * housing_units
        weights[district_slug] = weights.get(district_slug, 0.0) + housing_units
    return [
        DistrictMetric(region_slug=district_slug, value=weighted[district_slug] / weights[district_slug])
        for district_slug in sorted(weighted)
        if weights[district_slug] > 0
    ]


def _write_crosswalk_artifact(region_slug: str, zcta_district_hu: dict[tuple[str, str], float]) -> None:
    path = repo_root() / "data" / "intermediate" / "census" / f"zcta_district_hu_{region_slug}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["zcta", "district_slug", "housing_units"])
        for (zcta, district_slug), housing_units in sorted(zcta_district_hu.items()):
            writer.writerow([zcta, district_slug, f"{housing_units:.6f}"])


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
    metrics: list[DistrictMetric],
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
    metrics: list[DistrictMetric],
    stats: CrosswalkStats,
) -> dict[str, Any]:
    cur.execute(
        """
        SELECT count(*)
        FROM regions
        WHERE region_group = %s
          AND region_type = 'school_district'
        """,
        (region_slug,),
    )
    expected_districts = int(cur.fetchone()[0])
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
    district_count, range_min, range_max = cur.fetchone()
    values = sorted(metric.value for metric in metrics)
    total_hu = stats.housing_units_total
    return {
        "metric_key": manifest.metric_key,
        "region": region_slug,
        "grain": grain,
        "districts_expected": expected_districts,
        "districts_computed": int(district_count),
        "district_coverage": int(district_count) / expected_districts if expected_districts else 0,
        "listings_expected": expected_listings,
        "listing_point_computed": 0,
        "listing_point_coverage": 0,
        "range_allowed": list(manifest.allowed_range),
        "range_min": float(range_min),
        "range_max": float(range_max),
        "value_mean": sum(values) / len(values) if values else 0,
        "value_p50": _percentile(values, 0.5),
        "value_p90": _percentile(values, 0.9),
        "zcta_count": stats.zcta_count,
        "zcta_district_rows": stats.zcta_district_rows,
        "block_rows_matched": stats.block_rows_matched,
        "housing_units_total": stats.housing_units_total,
        "zillow_housing_units": stats.zillow_housing_units,
        "acs_housing_units": stats.acs_housing_units,
        "missing_value_housing_units": stats.missing_value_housing_units,
        "zillow_hu_share": stats.zillow_housing_units / total_hu if total_hu else 0,
        "acs_fallback_hu_share": stats.acs_housing_units / total_hu if total_hu else 0,
        "missing_value_hu_share": stats.missing_value_housing_units / total_hu if total_hu else 0,
    }


def _normalize_zcta(value: str) -> str:
    value = value.strip()
    if not value or not value.isdigit():
        return ""
    return value.zfill(5)


def _safe_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _safe_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


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
