from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg
import pytest


DATABASE_URL = os.environ.get("DATABASE_URL")


pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL is required for golden database checks",
)


def fetch_one(query: str, params: tuple[object, ...] = ()) -> object:
    assert DATABASE_URL is not None
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()[0]


def test_frozen_listing_counts() -> None:
    assert fetch_one("SELECT count(*) FROM listings") == 4505
    assert fetch_one("SELECT count(*) FROM listings WHERE state = 'PA'") == 251
    assert fetch_one("SELECT count(*) FROM listings WHERE state = 'NY'") == 4254
    assert fetch_one("SELECT count(*) FROM listings WHERE district_id IS NULL") == 0


@pytest.mark.parametrize(
    ("address", "state", "district"),
    [
        ("145 Walnut Ave, Ardmore, PA 19003", "PA", "Lower Merion"),
        ("754 Oak View Rd, Ardmore, PA 19003", "PA", "Haverford Township"),
        ("315 Walnut Ave, Wayne, PA 19087", "PA", "Radnor Township"),
        ("100 Euclid Ave, Ardsley, NY 10502", "NY", "Ardsley"),
        ("17 Cowdray Park Dr, Armonk, NY 10504", "NY", "Byram Hills"),
        ("6 N Island Dr, Rye, NY 10580", "NY", "Rye"),
    ],
)
def test_pinned_address_districts(address: str, state: str, district: str) -> None:
    actual = fetch_one(
        """
        SELECT d.name_display
        FROM listings l
        JOIN school_districts d ON d.id = l.district_id
        WHERE l.address = %s
          AND l.state = %s
        """,
        (address, state),
    )
    assert actual == district


def test_nearest_fallbacks_are_documented_and_capped() -> None:
    assert fetch_one("SELECT count(*) FROM listings WHERE assignment_method = 'nearest'") == 4
    assert (
        fetch_one(
            """
            SELECT count(*)
            FROM listings
            WHERE assignment_method = 'nearest'
              AND assignment_dist_m > 500
            """
        )
        == 0
    )


def test_geometry_srid_and_validity() -> None:
    checks = [
        "SELECT count(*) FROM listings WHERE ST_SRID(geom) <> 4326",
        "SELECT count(*) FROM school_districts WHERE ST_SRID(geom) <> 4326",
        "SELECT count(*) FROM listings WHERE NOT ST_IsValid(geom)",
        "SELECT count(*) FROM school_districts WHERE NOT ST_IsValid(geom)",
    ]
    for query in checks:
        assert fetch_one(query) == 0


def test_frozen_geojson_represented_once() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    geojson = json.loads((repo_root / "app/public/data/listings.geojson").read_text())
    expected_ids = {
        f"{feature['properties']['state']}-{feature['properties']['id']}"
        for feature in geojson["features"]
    }

    assert len(expected_ids) == 4505
    assert fetch_one("SELECT count(DISTINCT source_id) FROM listings") == len(expected_ids)
    assert fetch_one("SELECT count(*) FROM listings WHERE source_id IS NULL") == 0


def test_recovered_assignments_match_saved_display_names() -> None:
    assert (
        fetch_one(
            """
            SELECT count(*)
            FROM listings l
            JOIN staging.recovered_listings rl ON rl.source_id = l.source_id
            JOIN school_districts d ON d.id = l.district_id
            WHERE normalize_name_for_compare(d.name_display)
               <> normalize_name_for_compare(rl.saved_school_district)
            """
        )
        == 0
    )
