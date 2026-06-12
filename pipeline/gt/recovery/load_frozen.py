from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import psycopg
from psycopg import sql
from shapely.geometry import shape

from gt.db.migrate import database_url, repo_root
from gt.normalize import normalize_district_name

SCHOOL_YEAR = "SY2223"
DISTRICT_URL = "https://nces.ed.gov/programs/edge/data/EDGE_SCHOOLDISTRICT_TL23_SY2223.zip"
DISTRICT_ZIP_NAME = "EDGE_SCHOOLDISTRICT_TL23_SY2223.zip"
DISTRICT_SHP_IN_ZIP = (
    "EDGE_SCHOOLDISTRICT_TL23_SY2223/"
    "EDGE_SCHOOLDISTRICT_TL_23_SY2223.shp"
)
STATE_FIPS = {"NY": "36", "PA": "42"}

GOOD_DISTRICTS = {
    "Haverford Township",
    "Lower Merion",
    "Upper Darby",
    "Ardsley",
    "Blind Brook-Rye",
    "Briarcliff Manor",
    "Bronxville",
    "Byram Hills",
    "Chappaqua",
    "Edgemont",
    "Harrison",
    "Irvington",
    "Pelham",
    "Rye City",
    "Scarsdale",
    "Nanuet",
    "Pearl River",
    "South Orangetown",
    "Haldane",
    "Cornwall",
    "Warwick Valley",
}


@dataclass(frozen=True)
class RecoveryReport:
    listings_loaded: int
    districts_loaded: int
    assigned_within: int
    assigned_nearest: int
    unassigned: int
    mismatched_saved_names: int

    def as_dict(self) -> dict[str, int]:
        return {
            "listings_loaded": self.listings_loaded,
            "districts_loaded": self.districts_loaded,
            "assigned_within": self.assigned_within,
            "assigned_nearest": self.assigned_nearest,
            "unassigned": self.unassigned,
            "mismatched_saved_names": self.mismatched_saved_names,
        }


def write_report(report: RecoveryReport) -> Path:
    reports_dir = repo_root() / "data" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": "phase_1_recovery",
        "source": "frozen_listing_geojson_plus_nces_edge_sy2223",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "promotable": report.unassigned == 0 and report.mismatched_saved_names == 0,
        **report.as_dict(),
    }
    path = reports_dir / "phase1_recovery_latest.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return path


def data_dir() -> Path:
    path = repo_root() / "data" / "raw" / "school_districts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_boundary_zip() -> Path:
    path = data_dir() / DISTRICT_ZIP_NAME
    if not path.exists():
        with urllib.request.urlopen(DISTRICT_URL, timeout=300) as response:
            path.write_bytes(response.read())
    return path


def _create_staging_tables(cur: psycopg.Cursor[Any]) -> None:
    cur.execute("DROP TABLE IF EXISTS staging.recovered_school_districts")
    cur.execute("DROP TABLE IF EXISTS staging.recovered_listings")
    cur.execute(
        """
        CREATE TABLE staging.recovered_school_districts (
          nces_geoid text PRIMARY KEY,
          name_raw text NOT NULL,
          name_display text NOT NULL,
          state text NOT NULL,
          school_year text NOT NULL,
          geom geometry(MultiPolygon, 4326) NOT NULL CHECK (ST_IsValid(geom))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE staging.recovered_listings (
          source_id text PRIMARY KEY,
          source text NOT NULL,
          region_slug text NOT NULL,
          address text,
          city text,
          state text,
          zip text,
          county text,
          price integer,
          beds integer,
          baths double precision,
          url text,
          saved_school_district text,
          saved_good_district boolean NOT NULL,
          geom geometry(Point, 4326) NOT NULL
        )
        """
    )


def _load_districts(cur: psycopg.Cursor[Any]) -> int:
    count = 0
    zip_path = ensure_boundary_zip().resolve()
    frame = gpd.read_file(f"zip://{zip_path}!{DISTRICT_SHP_IN_ZIP}").to_crs("EPSG:4326")
    frame = frame[frame["STATEFP"].isin(STATE_FIPS.values())]
    fips_to_state = {fips: state for state, fips in STATE_FIPS.items()}
    for _, row in frame.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        name_raw = str(row["NAME"])
        cur.execute(
            """
            INSERT INTO staging.recovered_school_districts
              (nces_geoid, name_raw, name_display, state, school_year, geom)
            VALUES
              (%s, %s, %s, %s, %s, ST_Multi(ST_MakeValid(ST_GeomFromWKB(%s, 4326))))
            ON CONFLICT (nces_geoid) DO UPDATE SET
              name_raw = EXCLUDED.name_raw,
              name_display = EXCLUDED.name_display,
              state = EXCLUDED.state,
              school_year = EXCLUDED.school_year,
              geom = EXCLUDED.geom
            """,
            (
                str(row["GEOID"]),
                name_raw,
                normalize_district_name(name_raw),
                fips_to_state[str(row["STATEFP"])],
                SCHOOL_YEAR,
                geom.wkb,
            ),
        )
        count += 1
    return count


def _load_listings(cur: psycopg.Cursor[Any]) -> int:
    listings_path = repo_root() / "app" / "public" / "data" / "listings.geojson"
    features = json.loads(listings_path.read_text())["features"]
    for feature in features:
        props = feature["properties"]
        geom = shape(feature["geometry"])
        state = props.get("state")
        region_slug = "hudson-valley" if state == "NY" else "pa-mainline"
        source_id = f"{state}-{props.get('id')}"
        cur.execute(
            """
            INSERT INTO staging.recovered_listings
              (source_id, source, region_slug, address, city, state, zip, county,
               price, beds, baths, url, saved_school_district, saved_good_district, geom)
            VALUES
              (%s, 'rentcast', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
               ST_SetSRID(ST_GeomFromWKB(%s), 4326))
            ON CONFLICT (source_id) DO UPDATE SET
              region_slug = EXCLUDED.region_slug,
              address = EXCLUDED.address,
              city = EXCLUDED.city,
              state = EXCLUDED.state,
              zip = EXCLUDED.zip,
              county = EXCLUDED.county,
              price = EXCLUDED.price,
              beds = EXCLUDED.beds,
              baths = EXCLUDED.baths,
              url = EXCLUDED.url,
              saved_school_district = EXCLUDED.saved_school_district,
              saved_good_district = EXCLUDED.saved_good_district,
              geom = EXCLUDED.geom
            """,
            (
                source_id,
                region_slug,
                props.get("address"),
                props.get("city"),
                state,
                props.get("zip"),
                props.get("county_name"),
                props.get("price"),
                props.get("beds"),
                props.get("baths"),
                props.get("url"),
                props.get("school_district"),
                bool(props.get("good_district")),
                geom.wkb,
            ),
        )
    return len(features)


def _promote(cur: psycopg.Cursor[Any]) -> None:
    cur.execute(
        """
        DELETE FROM listings
        WHERE source = 'rentcast'
          AND state IN ('NY', 'PA')
        """
    )
    cur.execute(
        """
        DELETE FROM district_quality
        WHERE district_id IN (
          SELECT id
          FROM school_districts
          WHERE state IN ('NY', 'PA')
            AND nces_geoid NOT IN (SELECT nces_geoid FROM staging.recovered_school_districts)
        )
        """
    )
    cur.execute(
        """
        DELETE FROM school_districts
        WHERE state IN ('NY', 'PA')
          AND nces_geoid NOT IN (SELECT nces_geoid FROM staging.recovered_school_districts)
        """
    )
    cur.execute(
        """
        INSERT INTO school_districts (nces_geoid, name_raw, name_display, state, school_year, geom)
        SELECT nces_geoid, name_raw, name_display, state, school_year, geom
        FROM staging.recovered_school_districts
        ON CONFLICT (nces_geoid) DO UPDATE SET
          name_raw = EXCLUDED.name_raw,
          name_display = EXCLUDED.name_display,
          state = EXCLUDED.state,
          school_year = EXCLUDED.school_year,
          geom = EXCLUDED.geom
        """
    )
    cur.execute(
        """
        INSERT INTO listings
          (source_id, source, region_slug, address, city, state, zip, county, price,
           beds, baths, url, district_id, assignment_method, assignment_dist_m, geom)
        SELECT
          source_id, source, region_slug, address, city, state, zip, county, price,
          beds, baths, url, NULL, 'within', NULL, geom
        FROM staging.recovered_listings
        """
    )
    cur.execute(
        """
        UPDATE listings l
        SET district_id = d.id,
            assignment_method = 'within',
            assignment_dist_m = 0
        FROM school_districts d
        WHERE l.district_id IS NULL
          AND l.state = d.state
          AND ST_Contains(d.geom, l.geom)
        """
    )
    cur.execute(
        """
        WITH nearest AS (
          SELECT l.id AS listing_id, d.id AS district_id,
                 ST_Distance(l.geom::geography, d.geom::geography) AS dist_m
          FROM listings l
          CROSS JOIN LATERAL (
            SELECT id, geom
            FROM school_districts d
            WHERE d.state = l.state
            ORDER BY d.geom <-> l.geom
            LIMIT 1
          ) d
          WHERE l.district_id IS NULL
        )
        UPDATE listings l
        SET district_id = nearest.district_id,
            assignment_method = 'nearest',
            assignment_dist_m = nearest.dist_m
        FROM nearest
        WHERE l.id = nearest.listing_id
          AND nearest.dist_m <= 500
        """
    )
    cur.execute(
        """
        INSERT INTO district_quality (district_id, good_district, source, notes)
        SELECT DISTINCT d.id,
               d.name_display = ANY(%s),
               'curated_placeholder',
               'Recovered from frozen Explorer good_district placeholder list.'
        FROM school_districts d
        WHERE d.state IN ('NY', 'PA')
        ON CONFLICT (district_id) DO UPDATE SET
          good_district = EXCLUDED.good_district,
          source = EXCLUDED.source,
          notes = EXCLUDED.notes
        """,
        (list(GOOD_DISTRICTS),),
    )


def load_frozen_dataset() -> RecoveryReport:
    with psycopg.connect(database_url(), autocommit=False) as conn:
        with conn.cursor() as cur:
            _create_staging_tables(cur)
            districts = _load_districts(cur)
            listings = _load_listings(cur)
            _promote(cur)
            cur.execute("SELECT count(*) FROM listings WHERE assignment_method = 'within'")
            assigned_within = int(cur.fetchone()[0])
            cur.execute("SELECT count(*) FROM listings WHERE assignment_method = 'nearest'")
            assigned_nearest = int(cur.fetchone()[0])
            cur.execute("SELECT count(*) FROM listings WHERE district_id IS NULL")
            unassigned = int(cur.fetchone()[0])
            cur.execute(
                """
                SELECT count(*)
                FROM listings l
                JOIN staging.recovered_listings rl ON rl.source_id = l.source_id
                JOIN school_districts d ON d.id = l.district_id
                WHERE normalize_name_for_compare(d.name_display) <> normalize_name_for_compare(rl.saved_school_district)
                """
            )
            mismatched = int(cur.fetchone()[0])
        conn.commit()
    report = RecoveryReport(
        listings_loaded=listings,
        districts_loaded=districts,
        assigned_within=assigned_within,
        assigned_nearest=assigned_nearest,
        unassigned=unassigned,
        mismatched_saved_names=mismatched,
    )
    write_report(report)
    return report
