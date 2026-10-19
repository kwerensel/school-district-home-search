import json

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point

from gt.gvi_research import (
    RoadSample, aggregate_segmented_images, image_coverage, mapillary_coverage,
    paired_correlation, sample_listing_roads,
)


def frames():
    listings = gpd.GeoDataFrame({"id": [1, 2]}, geometry=[Point(0, 10), Point(2000, 0)], crs=5070).to_crs(4326)
    roads = gpd.GeoDataFrame(geometry=[LineString([(-200, 0), (200, 0)])], crs=5070).to_crs(4326)
    return listings, roads


def test_sampling_is_metric_bounded_and_independent_of_road_direction():
    listings, roads = frames()
    result = sample_listing_roads(listings, roads)
    reversed_roads = roads.copy()
    reversed_roads.geometry = reversed_roads.geometry.reverse()
    assert result == sample_listing_roads(listings.iloc[::-1], reversed_roads)
    assert len(result) == 5
    assert {p.listing_id for p in result} == {1}
    assert all(p.distance_m <= 150 for p in result)
    assert len({p.sample_id for p in result}) == 5
    duplicate_roads = gpd.GeoDataFrame(geometry=[roads.geometry.iloc[0]] * 2, crs=4326)
    assert result == sample_listing_roads(listings, duplicate_roads)


def test_sampling_rejects_unasserted_crs_or_expanded_radius():
    listings, roads = frames()
    with pytest.raises(ValueError, match="EPSG:4326"):
        sample_listing_roads(listings.to_crs(5070), roads)
    with pytest.raises(ValueError):
        sample_listing_roads(listings, roads, radius_m=151)


def test_coverage_deduplicates_images_and_retains_uncovered_listings():
    samples = [RoadSample(1, "a", -75, 40, 1), RoadSample(1, "b", -75, 40, 2)]
    images = [{"id": "1", "longitude": -75, "latitude": 40}] * 2
    images += [{"id": "far", "longitude": -75, "latitude": 41}]
    result = image_coverage(samples, images, listing_ids=[1, 2])
    assert result[0]["candidate_image_count"] == 1
    assert not result[0]["coverage_eligible"]
    assert result[1]["candidate_image_count"] == 0


def test_segmentation_count_is_successful_unique_images_not_metadata_count():
    assert aggregate_segmented_images({"a": .2, "b": None}) == {
        "gvi_streetlevel": None, "gvi_streetlevel_n_images": 1,
        "display_source": "estimated from satellite",
    }
    assert aggregate_segmented_images({"a": .2, "b": .4, "c": .6})["gvi_streetlevel"] == pytest.approx(.4)
    with pytest.raises(ValueError):
        aggregate_segmented_images({"a": float("nan")})


def test_correlation_is_paired_and_honest_without_inference():
    assert paired_correlation({}, {})["reason"] == "insufficient_pairs"
    assert paired_correlation({1: 1, 2: 1, 3: 1}, {1: .2, 2: .3, 3: .4})["reason"] == "constant_values"
    result = paired_correlation({1: .2, 2: .4, 3: .6, 4: None}, {1: .1, 2: .2, 3: .3, 5: .9})
    assert result["paired_count"] == 3
    assert result["pearson_r"] == pytest.approx(1)


def test_mapillary_adapter_bounds_pagination_and_never_caches_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("MAPILLARY_ACCESS_TOKEN", "private-test-token")
    requests = []
    def fetch(request):
        requests.append(request)
        assert "private-test-token" not in request.full_url
        return {"data": [{"id": "1", "computed_geometry": {"type": "Point", "coordinates": [-75, 40]}}],
                "paging": {"next": "https://elsewhere.invalid/?access_token=private-test-token", "cursors": {"after": "page2"}}}
    result = mapillary_coverage((-75.01, 39.99, -74.99, 40.01), cache_dir=tmp_path, max_pages=2, requester=fetch)
    assert len(requests) == 2
    assert "after=page2" in requests[1].full_url
    assert result["truncated"]
    assert not result["imagery_downloaded"]
    assert len(result["images"]) == 1
    assert "private-test-token" not in next(tmp_path.iterdir()).read_text()
    assert mapillary_coverage((-75.01, 39.99, -74.99, 40.01), cache_dir=tmp_path, max_pages=2) == result


def test_provider_errors_are_sanitized(tmp_path, monkeypatch):
    monkeypatch.setenv("MAPILLARY_ACCESS_TOKEN", "secret")
    def fail(request):
        raise ValueError("secret")
    with pytest.raises(RuntimeError, match="metadata request failed") as error:
        mapillary_coverage((-75.01, 39.99, -74.99, 40.01), cache_dir=tmp_path, requester=fail)
    assert "secret" not in str(error.value)
