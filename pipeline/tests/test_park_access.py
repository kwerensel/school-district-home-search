import geopandas as gpd
import pytest
from shapely.geometry import Point, box

from gt.layers.park_access import _compute_listing_metrics, _compute_region_metrics


def test_tract_share_uses_800m_access_buffer() -> None:
    tract = gpd.GeoDataFrame(
        {"slug": ["test-tract"]},
        geometry=[box(0, 0, 0.02, 0.02)],
        crs="EPSG:4326",
    )
    parks = gpd.GeoDataFrame(
        geometry=[box(0.009, 0.009, 0.011, 0.011)],
        crs="EPSG:4326",
    )

    metrics, stats = _compute_region_metrics(tract, parks)

    assert len(metrics) == 1
    assert 0 < metrics[0].value < 1
    assert stats["access_buffer_m"] == 800


def test_listing_distance_is_zero_inside_and_positive_outside() -> None:
    listings = gpd.GeoDataFrame(
        {"id": [1, 2]},
        geometry=[Point(0.005, 0.005), Point(0.02, 0.005)],
        crs="EPSG:4326",
    )
    parks = gpd.GeoDataFrame(
        geometry=[box(0, 0, 0.01, 0.01)],
        crs="EPSG:4326",
    )

    metrics, stats = _compute_listing_metrics(listings, parks)
    values = {metric.listing_id: metric.value for metric in metrics}

    assert values[1] == pytest.approx(0)
    assert values[2] > 1000
    assert stats["listings_inside_access_polygon"] == 1
