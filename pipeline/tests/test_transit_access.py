import geopandas as gpd
import pytest
from shapely.geometry import Point, box

from gt.layers.transit_access import (
    _compute_listing_metrics,
    _compute_region_metrics,
    _deduplicate_stops,
)


def test_deduplicate_stops_uses_stable_onestop_identity_and_keeps_feed_evidence() -> None:
    records = [
        {
            "id": 1,
            "onestop_id": "s-test-stop",
            "geometry": {"type": "Point", "coordinates": [-75.1, 40.0]},
            "feed_version": {
                "sha1": "abc123",
                "fetched_at": "2026-08-01T00:00:00Z",
                "feed": {"onestop_id": "f-test"},
            },
        },
        {
            "id": 2,
            "onestop_id": "s-test-stop",
            "geometry": {"type": "Point", "coordinates": [-75.1, 40.0]},
            "feed_version": {
                "sha1": "def456",
                "fetched_at": "2026-08-02T00:00:00Z",
                "feed": {"onestop_id": "f-test-2"},
            },
        },
        {"id": 3, "geometry": None, "feed_version": None},
    ]

    stops, invalid, versions = _deduplicate_stops(records)

    assert len(stops) == 1
    assert invalid == 1
    assert set(versions) == {"abc123", "def456"}


def test_transit_density_includes_zero_stop_tracts() -> None:
    tracts = gpd.GeoDataFrame(
        {"slug": ["tract-a", "tract-b"]},
        geometry=[box(-75.2, 40.0, -75.19, 40.01), box(-75.18, 40.0, -75.17, 40.01)],
        crs="EPSG:4326",
    )
    stops = gpd.GeoDataFrame(
        {"identity": ["s-a", "s-b"]},
        geometry=[Point(-75.195, 40.005), Point(-75.196, 40.006)],
        crs="EPSG:4326",
    )

    metrics, stats = _compute_region_metrics(tracts, stops)
    values = {metric.region_slug: metric.value for metric in metrics}

    assert values["tract-a"] > 0
    assert values["tract-b"] == 0
    assert stats["tracts_with_zero_stops"] == 1


def test_listing_distance_uses_nearest_stop() -> None:
    listings = gpd.GeoDataFrame(
        {"id": [1, 2]},
        geometry=[Point(-75.1, 40.0), Point(-75.2, 40.0)],
        crs="EPSG:4326",
    )
    stops = gpd.GeoDataFrame(
        {"identity": ["s-a"]},
        geometry=[Point(-75.1, 40.001)],
        crs="EPSG:4326",
    )

    metrics, stats = _compute_listing_metrics(listings, stops)
    values = {metric.listing_id: metric.value for metric in metrics}

    assert values[1] == pytest.approx(111, rel=0.1)
    assert values[2] > 8_000
    assert stats["listings_without_nearest_stop"] == 0
