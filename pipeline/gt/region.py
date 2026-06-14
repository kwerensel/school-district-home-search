from __future__ import annotations

import re
import urllib.request
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import psycopg
from psycopg import sql
from shapely.geometry.base import BaseGeometry

from gt.db.migrate import database_url, repo_root
from gt.manifests import RegionManifest, load_region_manifest
from gt.normalize import normalize_district_name
from gt.reports import ValidationReport, write_report

SCHOOL_YEAR = "SY2223"
DISTRICT_URL = "https://nces.ed.gov/programs/edge/data/EDGE_SCHOOLDISTRICT_TL23_SY2223.zip"
DISTRICT_SHP_IN_ZIP = (
    "EDGE_SCHOOLDISTRICT_TL23_SY2223/"
    "EDGE_SCHOOLDISTRICT_TL_23_SY2223.shp"
)
STATE_ABBR = {"36": "NY", "42": "PA"}
TIGER_URLS = {
    "tract": "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_{state}_tract.zip",
    "cousub": "https://www2.census.gov/geo/tiger/TIGER2023/COUSUB/tl_2023_{state}_cousub.zip",
    "place": "https://www2.census.gov/geo/tiger/TIGER2023/PLACE/tl_2023_{state}_place.zip",
}


def validate_region_manifest(path: Path) -> RegionManifest:
    return load_region_manifest(path)


def add_region(path: Path) -> tuple[ValidationReport, Path]:
    manifest = validate_region_manifest(path)
    with psycopg.connect(database_url(), autocommit=False) as conn:
        with conn.cursor() as cur:
            _clear_staging(cur, manifest.slug)
            counts = _stage_region(cur, manifest)
            checks = _validate_staging(cur, manifest.slug) | counts
        conn.commit()

    promotable = (
        checks["census_tract_regions"] > 0
        and checks["school_district_regions"] > 0
        and checks["invalid_geometries"] == 0
        and checks["non_4326_geometries"] == 0
        and checks["district_overlap_weight_min"] >= 0.99
        and checks["district_overlap_weight_max"] <= 1.01
    )
    report = ValidationReport(
        report_type="region_scaffold",
        target=manifest.slug,
        checks=checks,
        promotable=promotable,
        status="staged",
    )
    path_out = write_report(report, f"region_{manifest.slug}_latest.json")
    return report, path_out


def scaffold_region_add(path: Path) -> tuple[ValidationReport, Path]:
    """Backward-compatible alias for tests and older callers."""
    return add_region(path)


def validate_region_report(region_slug: str) -> tuple[ValidationReport, Path]:
    with psycopg.connect(database_url(), autocommit=False) as conn:
        with conn.cursor() as cur:
            checks = _validate_public(cur, region_slug)
        conn.commit()
    promotable = (
        checks["census_tract_regions"] > 0
        and checks["school_district_regions"] > 0
        and checks["invalid_geometries"] == 0
        and checks["non_4326_geometries"] == 0
        and checks["district_overlap_weight_min"] >= 0.99
        and checks["district_overlap_weight_max"] <= 1.01
    )
    report = ValidationReport(
        report_type="region_scaffold",
        target=region_slug,
        checks=checks,
        promotable=promotable,
        status="promoted" if promotable else "failed",
    )
    path_out = write_report(report, f"region_{region_slug}_latest.json")
    return report, path_out


def promote_region(region_slug: str) -> None:
    with psycopg.connect(database_url(), autocommit=False) as conn:
        with conn.cursor() as cur:
            _promote(cur, region_slug)
        conn.commit()


def render_region_qa(region_slug: str) -> Path:
    import os

    qa_dir = repo_root() / "data" / "reports" / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(qa_dir / ".matplotlib-cache"))
    os.environ.setdefault("XDG_CACHE_HOME", str(qa_dir / ".cache"))

    import matplotlib.pyplot as plt

    with psycopg.connect(database_url()) as conn:
        tracts = gpd.read_postgis(
            """
            SELECT slug, name, geom
            FROM regions
            WHERE region_group = %s
              AND region_type = 'census_tract'
            """,
            conn,
            params=(region_slug,),
            geom_col="geom",
        )
        districts = gpd.read_postgis(
            """
            SELECT slug, name, geom
            FROM regions
            WHERE region_group = %s
              AND region_type = 'school_district'
            """,
            conn,
            params=(region_slug,),
            geom_col="geom",
        )
    if tracts.empty or districts.empty:
        raise RuntimeError(f"No promoted tract/district regions found for {region_slug}")

    path = qa_dir / f"{region_slug}_tracts_districts.png"

    fig, ax = plt.subplots(figsize=(10, 10))
    districts.boundary.plot(ax=ax, color="#1d4ed8", linewidth=1.0)
    tracts.boundary.plot(ax=ax, color="#111827", linewidth=0.25, alpha=0.65)
    ax.set_title(f"{region_slug}: tract boundaries over district boundaries")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def _stage_region(cur: psycopg.Cursor[Any], manifest: RegionManifest) -> dict[str, int]:
    state = manifest.state_fips[0]
    if state not in STATE_ABBR:
        raise ValueError(f"Unsupported state FIPS for seed manifest: {state}")

    tracts = _load_tiger("tract", state)
    tracts = tracts[tracts["COUNTYFP"].isin([county[2:] for county in manifest.counties])]
    tracts = _clean(tracts)
    county_union = tracts.geometry.union_all()

    cousubs = _load_tiger("cousub", state)
    cousubs = _clean(cousubs[cousubs["COUNTYFP"].isin([county[2:] for county in manifest.counties])])

    places = _load_tiger("place", state)
    places = _clean(places[places.intersects(county_union)])

    districts = _load_districts(manifest.state_fips, county_union)

    _insert_school_districts(cur, districts, manifest.slug, STATE_ABBR[state])
    _insert_regions(cur, _tract_regions(tracts, manifest.slug, STATE_ABBR[state]))
    _insert_regions(cur, _municipality_regions(cousubs, "cousub", manifest.slug, STATE_ABBR[state]))
    _insert_regions(cur, _municipality_regions(places, "place", manifest.slug, STATE_ABBR[state]))
    _insert_regions(cur, _district_regions(districts, manifest.slug, STATE_ABBR[state]))
    _insert_overlaps(cur, tracts, districts, "sd", manifest.slug)
    municipalities = _municipality_frame(cousubs, places)
    _insert_overlaps(cur, tracts, municipalities, "mun", manifest.slug)

    checks = {
        "slug": manifest.slug,
        "tracts_loaded": len(tracts),
        "county_subdivisions_loaded": len(cousubs),
        "places_loaded": len(places),
        "school_districts_loaded": len(districts),
    }
    return checks


def _clear_staging(cur: psycopg.Cursor[Any], region_slug: str) -> None:
    for table in (
        "region_scaffold_overlaps",
        "region_scaffold_regions",
        "region_scaffold_school_districts",
    ):
        cur.execute(
            sql.SQL("DELETE FROM staging.{} WHERE region_group = %s").format(sql.Identifier(table)),
            (region_slug,),
        )


def _data_path(*parts: str) -> Path:
    path = repo_root() / "data" / "raw" / Path(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _ensure_download(url: str, path: Path) -> Path:
    if not path.exists():
        with urllib.request.urlopen(url, timeout=300) as response:
            path.write_bytes(response.read())
    return path


def _load_tiger(kind: str, state_fips: str) -> gpd.GeoDataFrame:
    filename = TIGER_URLS[kind].format(state=state_fips).rsplit("/", 1)[-1]
    path = _ensure_download(TIGER_URLS[kind].format(state=state_fips), _data_path("tiger", filename))
    return gpd.read_file(path).to_crs("EPSG:4326")


def _load_districts(state_fips: list[str], county_union: BaseGeometry) -> gpd.GeoDataFrame:
    path = _ensure_download(
        DISTRICT_URL,
        _data_path("school_districts", "EDGE_SCHOOLDISTRICT_TL23_SY2223.zip"),
    )
    frame = gpd.read_file(f"zip://{path.resolve()}!{DISTRICT_SHP_IN_ZIP}").to_crs("EPSG:4326")
    frame = frame[frame["STATEFP"].isin(state_fips)]
    frame = _clean(frame[frame.intersects(county_union)])
    return frame


def _clean(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    frame = frame.copy()
    frame["geometry"] = frame.geometry.make_valid()
    frame = frame[~frame.geometry.is_empty & frame.geometry.notna()]
    return frame.to_crs("EPSG:4326")


def _slug(value: str) -> str:
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", value.lower()))


def _multi_wkb(geom: BaseGeometry) -> bytes:
    return geom.wkb


def _insert_school_districts(
    cur: psycopg.Cursor[Any], frame: gpd.GeoDataFrame, region_group: str, state: str
) -> None:
    for _, row in frame.iterrows():
        name_raw = str(row["NAME"])
        cur.execute(
            """
            INSERT INTO staging.region_scaffold_school_districts
              (nces_geoid, name_raw, name_display, state, school_year, geom, region_group)
            VALUES
              (%s, %s, %s, %s, %s, ST_Multi(ST_MakeValid(ST_GeomFromWKB(%s, 4326))), %s)
            ON CONFLICT (nces_geoid) DO UPDATE SET
              name_raw = EXCLUDED.name_raw,
              name_display = EXCLUDED.name_display,
              state = EXCLUDED.state,
              school_year = EXCLUDED.school_year,
              geom = EXCLUDED.geom,
              region_group = EXCLUDED.region_group
            """,
            (
                str(row["GEOID"]),
                name_raw,
                normalize_district_name(name_raw),
                state,
                SCHOOL_YEAR,
                _multi_wkb(row.geometry),
                region_group,
            ),
        )


def _insert_regions(cur: psycopg.Cursor[Any], rows: list[dict[str, Any]]) -> None:
    for row in rows:
        cur.execute(
            """
            INSERT INTO staging.region_scaffold_regions
              (region_type, slug, name, state, source_id, district_source_id, geom, region_group)
            VALUES
              (%s::region_type, %s, %s, %s, %s, %s,
               ST_Multi(ST_MakeValid(ST_GeomFromWKB(%s, 4326))), %s)
            ON CONFLICT (slug) DO UPDATE SET
              region_type = EXCLUDED.region_type,
              name = EXCLUDED.name,
              state = EXCLUDED.state,
              source_id = EXCLUDED.source_id,
              district_source_id = EXCLUDED.district_source_id,
              geom = EXCLUDED.geom,
              region_group = EXCLUDED.region_group
            """,
            (
                row["region_type"],
                row["slug"],
                row["name"],
                row["state"],
                row["source_id"],
                row.get("district_source_id"),
                _multi_wkb(row["geom"]),
                row["region_group"],
            ),
        )


def _tract_regions(frame: gpd.GeoDataFrame, region_group: str, state: str) -> list[dict[str, Any]]:
    return [
        {
            "region_type": "census_tract",
            "slug": f"tract-{row['GEOID']}",
            "name": f"Tract {row['NAME']}",
            "state": state,
            "source_id": str(row["GEOID"]),
            "geom": row.geometry,
            "region_group": region_group,
        }
        for _, row in frame.iterrows()
    ]


def _municipality_regions(
    frame: gpd.GeoDataFrame, source: str, region_group: str, state: str
) -> list[dict[str, Any]]:
    prefix = "mun-cousub" if source == "cousub" else "mun-place"
    return [
        {
            "region_type": "municipality",
            "slug": f"{prefix}-{row['GEOID']}",
            "name": str(row["NAME"]),
            "state": state,
            "source_id": str(row["GEOID"]),
            "geom": row.geometry,
            "region_group": region_group,
        }
        for _, row in frame.iterrows()
    ]


def _district_regions(frame: gpd.GeoDataFrame, region_group: str, state: str) -> list[dict[str, Any]]:
    return [
        {
            "region_type": "school_district",
            "slug": f"sd-{_slug(str(row['GEOID']))}",
            "name": normalize_district_name(str(row["NAME"])),
            "state": state,
            "source_id": str(row["GEOID"]),
            "district_source_id": str(row["GEOID"]),
            "geom": row.geometry,
            "region_group": region_group,
        }
        for _, row in frame.iterrows()
    ]


def _municipality_frame(cousubs: gpd.GeoDataFrame, places: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    c = cousubs[["GEOID", "NAME", "geometry"]].copy()
    c["slug"] = "mun-cousub-" + c["GEOID"].astype(str)
    p = places[["GEOID", "NAME", "geometry"]].copy()
    p["slug"] = "mun-place-" + p["GEOID"].astype(str)
    return gpd.GeoDataFrame(
        pd.concat([c, p], ignore_index=True),
        geometry="geometry",
        crs="EPSG:4326",
    )


def _insert_overlaps(
    cur: psycopg.Cursor[Any],
    tracts: gpd.GeoDataFrame,
    parents: gpd.GeoDataFrame,
    parent_kind: str,
    region_group: str,
) -> None:
    if parents.empty:
        return
    tract_work = tracts[["GEOID", "geometry"]].copy().to_crs("EPSG:5070")
    parent_columns = ["GEOID", "geometry"]
    if "slug" in parents.columns:
        parent_columns.append("slug")
    parent_work = parents[parent_columns].copy()
    if "slug" not in parent_work.columns:
        parent_work["slug"] = "sd-" + parent_work["GEOID"].astype(str).map(_slug)
    parent_work = parent_work.to_crs("EPSG:5070")
    joined = gpd.overlay(tract_work, parent_work, how="intersection", keep_geom_type=False)
    joined["intersection_area"] = joined.geometry.area
    tract_area = tract_work.set_index("GEOID").geometry.area.to_dict()
    if parent_kind == "sd":
        tract_area = joined.groupby("GEOID_1")["intersection_area"].sum().to_dict()
    for _, row in joined.iterrows():
        child_slug = f"tract-{row['GEOID_1']}"
        parent_slug = row["slug"] if parent_kind == "mun" else f"sd-{_slug(str(row['GEOID_2']))}"
        denominator = tract_area[row["GEOID_1"]]
        if denominator == 0:
            continue
        weight = float(row["intersection_area"] / denominator)
        if weight <= 0:
            continue
        cur.execute(
            """
            INSERT INTO staging.region_scaffold_overlaps
              (child_slug, parent_slug, area_weight, region_group)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (child_slug, parent_slug) DO UPDATE SET
              area_weight = EXCLUDED.area_weight,
              region_group = EXCLUDED.region_group
            """,
            (child_slug, parent_slug, weight, region_group),
        )


def _validate_staging(cur: psycopg.Cursor[Any], region_slug: str) -> dict[str, Any]:
    return _validate_tables(cur, region_slug, "staging.region_scaffold_regions", "staging.region_scaffold_overlaps")


def _validate_public(cur: psycopg.Cursor[Any], region_slug: str) -> dict[str, Any]:
    return _validate_tables(cur, region_slug, "regions", "region_overlaps")


def _validate_tables(
    cur: psycopg.Cursor[Any], region_slug: str, regions_table: str, overlaps_table: str
) -> dict[str, Any]:
    if regions_table == "regions":
        child_expr = "child.id"
        parent_expr = "parent.id"
        overlap_join = f"{overlaps_table} ro ON ro.child_region_id = child.id"
        parent_join = "regions parent ON parent.id = ro.parent_region_id"
    else:
        child_expr = "child.slug"
        parent_expr = "parent.slug"
        overlap_join = f"{overlaps_table} ro ON ro.child_slug = child.slug"
        parent_join = f"{regions_table} parent ON parent.slug = ro.parent_slug"

    cur.execute(
        f"""
        SELECT region_type::text, count(*)
        FROM {regions_table}
        WHERE region_group = %s
        GROUP BY region_type
        """,
        (region_slug,),
    )
    counts = {row[0]: int(row[1]) for row in cur.fetchall()}
    cur.execute(
        f"""
        SELECT count(*)
        FROM {regions_table}
        WHERE region_group = %s
          AND (NOT ST_IsValid(geom) OR ST_IsEmpty(geom))
        """,
        (region_slug,),
    )
    invalid = int(cur.fetchone()[0])
    cur.execute(
        f"""
        SELECT count(*)
        FROM {regions_table}
        WHERE region_group = %s
          AND ST_SRID(geom) <> 4326
        """,
        (region_slug,),
    )
    non_4326 = int(cur.fetchone()[0])
    cur.execute(
        f"""
        WITH district_weights AS (
          SELECT {child_expr} AS child_id, sum(ro.area_weight) AS weight_sum
          FROM {regions_table} child
          JOIN {overlap_join}
          JOIN {parent_join}
          WHERE child.region_group = %s
            AND child.region_type = 'census_tract'
            AND parent.region_type = 'school_district'
          GROUP BY {child_expr}
        )
        SELECT coalesce(min(weight_sum), 0), coalesce(max(weight_sum), 0)
        FROM district_weights
        """,
        (region_slug,),
    )
    min_weight, max_weight = cur.fetchone()
    if regions_table == "regions":
        cur.execute(
            f"""
            SELECT count(*)
            FROM {overlaps_table} ro
            JOIN regions child ON child.id = ro.child_region_id
            WHERE child.region_group = %s
            """,
            (region_slug,),
        )
    else:
        cur.execute(
            f"""
            SELECT count(*)
            FROM {overlaps_table} ro
            WHERE ro.region_group = %s
            """,
            (region_slug,),
        )
    overlaps = int(cur.fetchone()[0])
    return {
        "census_tract_regions": counts.get("census_tract", 0),
        "municipality_regions": counts.get("municipality", 0),
        "school_district_regions": counts.get("school_district", 0),
        "overlap_rows": overlaps,
        "invalid_geometries": invalid,
        "non_4326_geometries": non_4326,
        "district_overlap_weight_min": float(min_weight),
        "district_overlap_weight_max": float(max_weight),
    }


def _promote(cur: psycopg.Cursor[Any], region_slug: str) -> None:
    cur.execute(
        """
        INSERT INTO school_districts (nces_geoid, name_raw, name_display, state, school_year, geom)
        SELECT nces_geoid, name_raw, name_display, state, school_year, geom
        FROM staging.region_scaffold_school_districts
        WHERE region_group = %s
        ON CONFLICT (nces_geoid) DO UPDATE SET
          name_raw = EXCLUDED.name_raw,
          name_display = EXCLUDED.name_display,
          state = EXCLUDED.state,
          school_year = EXCLUDED.school_year,
          geom = EXCLUDED.geom
        """,
        (region_slug,),
    )
    cur.execute(
        """
        DELETE FROM region_overlaps ro
        USING regions child, regions parent
        WHERE ro.child_region_id = child.id
          AND ro.parent_region_id = parent.id
          AND child.region_group = %s
        """,
        (region_slug,),
    )
    cur.execute("DELETE FROM regions WHERE region_group = %s", (region_slug,))
    cur.execute(
        """
        INSERT INTO regions
          (region_type, slug, name, state, source_id, district_id, geom, region_group)
        SELECT sr.region_type, sr.slug, sr.name, sr.state, sr.source_id, sd.id, sr.geom, sr.region_group
        FROM staging.region_scaffold_regions sr
        LEFT JOIN school_districts sd ON sd.nces_geoid = sr.district_source_id
        WHERE sr.region_group = %s
        """,
        (region_slug,),
    )
    cur.execute(
        """
        INSERT INTO region_overlaps (child_region_id, parent_region_id, area_weight)
        SELECT child.id, parent.id, so.area_weight
        FROM staging.region_scaffold_overlaps so
        JOIN regions child ON child.slug = so.child_slug
        JOIN regions parent ON parent.slug = so.parent_slug
        WHERE so.region_group = %s
        ON CONFLICT (child_region_id, parent_region_id) DO UPDATE SET
          area_weight = EXCLUDED.area_weight
        """,
        (region_slug,),
    )
    cur.execute("REFRESH MATERIALIZED VIEW district_metrics")
