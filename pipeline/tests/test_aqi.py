import geopandas as gpd
import pytest
from shapely.geometry import Point, box

from gt.layers.aqi import _annual_monitor_means, _interpolate_tracts


def _record(
    *,
    site: str,
    date: str,
    aqi: float | None,
    parameter: str = "44201",
    county: str = "001",
    longitude: float = -75.0,
) -> dict[str, object]:
    return {
        "state_code": "42",
        "county_code": county,
        "site_number": site,
        "date_local": date,
        "aqi": aqi,
        "parameter_code": parameter,
        "latitude": 40.0,
        "longitude": longitude,
    }


def test_monitor_means_take_maximum_aqi_per_site_day(monkeypatch) -> None:
    monkeypatch.setattr("gt.layers.aqi.MIN_MONITOR_DAYS", 2)
    records = [
        _record(site="0001", date="2025-01-01", aqi=25),
        _record(site="0001", date="2025-01-01", aqi=42, parameter="88101"),
        _record(site="0001", date="2025-01-01", aqi=42, parameter="88101"),
        _record(site="0001", date="2025-01-02", aqi=18),
        _record(site="0002", date="2025-01-01", aqi=12, longitude=-75.2),
        _record(site="0003", date="2025-01-01", aqi=None),
    ]

    monitors, stats = _annual_monitor_means(records)

    assert len(monitors) == 1
    assert monitors.iloc[0]["value"] == pytest.approx(30)
    assert monitors.iloc[0]["days"] == 2
    assert stats["rows_with_aqi"] == 5
    assert stats["rows_missing_aqi"] == 1
    assert stats["invalid_rows"] == 0
    assert stats["duplicate_site_days_removed"] == 2
    assert stats["monitors_below_minimum_days"] == 1
    assert stats["parameters_with_aqi"] == ["44201", "88101"]


def test_interpolation_uses_nearby_idw_then_county_fallback() -> None:
    tracts = gpd.GeoDataFrame(
        {
            "slug": ["near", "fallback"],
            "source_id": ["42001000100", "42003000100"],
        },
        geometry=[
            box(-75.02, 39.99, -74.98, 40.01),
            box(-76.52, 39.99, -76.48, 40.01),
        ],
        crs="EPSG:4326",
    )
    monitors = gpd.GeoDataFrame(
        {
            "site_id": ["near-a", "near-b", "county-fallback"],
            "county_fips": ["42001", "42001", "42003"],
            "value": [40.0, 80.0, 55.0],
            "days": [100, 100, 200],
        },
        geometry=[Point(-75.0, 40.0), Point(-75.1, 40.0), Point(-77.1, 40.0)],
        crs="EPSG:4326",
    )

    metrics, stats = _interpolate_tracts(tracts, monitors)
    values = {metric.region_slug: metric.value for metric in metrics}

    assert values["near"] == pytest.approx(40, abs=0.1)
    assert values["fallback"] == pytest.approx(55)
    assert stats["tracts_idw"] == 1
    assert stats["tracts_county_fallback"] == 1
    assert stats["tracts_missing"] == 0
