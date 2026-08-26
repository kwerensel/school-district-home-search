import geopandas as gpd
import pytest
from shapely.geometry import box

from gt.layers.commute_minutes import _matrix_durations, _population_weighted_origins


def test_matrix_durations_preserves_unroutable_cells() -> None:
    assert _matrix_durations({"durations": [[60], [None], [125.5]]}, 3) == [
        60.0,
        None,
        125.5,
    ]


def test_matrix_durations_rejects_wrong_shape() -> None:
    with pytest.raises(RuntimeError, match="expected 2"):
        _matrix_durations({"durations": [[60]]}, 2)


def test_population_weighted_origin_uses_block_group_populations(monkeypatch) -> None:
    tracts = gpd.GeoDataFrame(
        {"slug": ["tract-a"], "source_id": ["42001000100"]},
        geometry=[box(-75.2, 40.0, -75.0, 40.2)],
        crs="EPSG:4326",
    )
    block_groups = gpd.GeoDataFrame(
        {
            "GEOID": ["420010001001", "420010001002"],
            "INTPTLON": ["-75.18", "-75.02"],
            "INTPTLAT": ["40.02", "40.18"],
        },
        geometry=[box(-75.2, 40.0, -75.1, 40.1), box(-75.1, 40.1, -75.0, 40.2)],
        crs="EPSG:4326",
    )
    monkeypatch.setattr(
        "gt.layers.commute_minutes._load_block_group_populations",
        lambda _state, _counties: {"420010001001": 900, "420010001002": 100},
    )
    monkeypatch.setattr(
        "gt.layers.commute_minutes._load_block_groups",
        lambda _state, _counties: block_groups,
    )

    origins, stats = _population_weighted_origins(tracts, "42", ["42001"])

    assert origins.geometry.iloc[0].x < -75.1
    assert origins.geometry.iloc[0].y < 40.1
    assert stats.tracts_population_weighted == 1
    assert stats.tracts_point_on_surface_fallback == 0
    assert stats.population_total == 1_000


def test_population_weighted_origin_falls_back_for_zero_population(monkeypatch) -> None:
    tracts = gpd.GeoDataFrame(
        {"slug": ["tract-a"], "source_id": ["42001000100"]},
        geometry=[box(-75.2, 40.0, -75.0, 40.2)],
        crs="EPSG:4326",
    )
    block_groups = gpd.GeoDataFrame(
        {
            "GEOID": ["420010001001"],
            "INTPTLON": ["-75.1"],
            "INTPTLAT": ["40.1"],
        },
        geometry=[box(-75.2, 40.0, -75.0, 40.2)],
        crs="EPSG:4326",
    )
    monkeypatch.setattr(
        "gt.layers.commute_minutes._load_block_group_populations",
        lambda _state, _counties: {"420010001001": 0},
    )
    monkeypatch.setattr(
        "gt.layers.commute_minutes._load_block_groups",
        lambda _state, _counties: block_groups,
    )

    origins, stats = _population_weighted_origins(tracts, "42", ["42001"])

    assert not origins.geometry.iloc[0].is_empty
    assert stats.tracts_population_weighted == 0
    assert stats.tracts_point_on_surface_fallback == 1
