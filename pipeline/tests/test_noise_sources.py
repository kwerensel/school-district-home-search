import geopandas as gpd
from shapely.geometry import LineString, Point, box

from gt.layers.noise_sources import (
    FRA_ACTIVE_FREIGHT_NET_CODES,
    _line_density,
    _listing_buffer_count,
    _listing_distance,
    _listing_grain,
    _point_density,
    _polygon_share,
)


def _tracts() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "slug": ["tract-a", "tract-b"],
            "geometry": [box(0, 0, 1000, 1000), box(1000, 0, 2000, 1000)],
        },
        geometry="geometry",
        crs="EPSG:5070",
    )


def _listings() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"id": [1, 2], "geometry": [Point(100, 100), Point(1800, 800)]},
        geometry="geometry",
        crs="EPSG:5070",
    )


def test_operational_freight_proxy_excludes_inactive_and_transit_only_codes() -> None:
    assert set(FRA_ACTIVE_FREIGHT_NET_CODES) == {"M", "I", "O", "S", "Y"}
    assert set(FRA_ACTIVE_FREIGHT_NET_CODES).isdisjoint({"X", "A", "R", "T", "Z"})


def test_nightlife_count_keeps_its_300m_provenance_grain() -> None:
    assert _listing_grain("noise_nightlife_count_300m") == "buffer_300m"
    assert _listing_grain("noise_siren_distance_m") == "point"


def test_point_density_and_listing_buffer_count_preserve_zeroes() -> None:
    sources = gpd.GeoDataFrame(
        {"geometry": [Point(100, 100), Point(200, 200)]},
        geometry="geometry",
        crs="EPSG:5070",
    )

    tract_metrics, _ = _point_density(_tracts(), sources)
    listing_metrics, _ = _listing_buffer_count(_listings(), sources, 300)

    assert [metric.value for metric in tract_metrics] == [2.0, 0.0]
    assert [metric.value for metric in listing_metrics] == [2.0, 0.0]


def test_polygon_share_distance_and_line_density_use_meter_geometry() -> None:
    industrial = gpd.GeoDataFrame(
        {"geometry": [box(0, 0, 500, 1000)]},
        geometry="geometry",
        crs="EPSG:5070",
    )
    rail = gpd.GeoDataFrame(
        {"geometry": [LineString([(0, 500), (2000, 500)])]},
        geometry="geometry",
        crs="EPSG:5070",
    )

    industrial_metrics, _ = _polygon_share(_tracts(), industrial)
    rail_metrics, _ = _line_density(_tracts(), rail)
    distance_metrics, _ = _listing_distance(_listings(), industrial)

    assert [metric.value for metric in industrial_metrics] == [50.0, 0.0]
    assert [metric.value for metric in rail_metrics] == [1.0, 1.0]
    assert distance_metrics[0].value == 0.0
    assert distance_metrics[1].value == 1300.0
