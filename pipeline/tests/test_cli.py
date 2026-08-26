from typer.testing import CliRunner

from gt.cli import app


def test_help() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Groundtruth deterministic geospatial pipeline" in result.output


def test_region_manifest_validates() -> None:
    result = CliRunner().invoke(
        app,
        [
            "manifest",
            "validate",
            "region",
            "manifests/regions/hudson-valley.yaml",
        ],
    )

    assert result.exit_code == 0
    assert "hudson-valley" in result.output


def test_canopy_height_layer_manifest_validates() -> None:
    result = CliRunner().invoke(
        app,
        [
            "manifest",
            "validate",
            "layer",
            "manifests/layers/canopy_height_m.yaml",
        ],
    )

    assert result.exit_code == 0
    assert "canopy_height_m" in result.output


def test_tree_canopy_layer_manifest_validates() -> None:
    result = CliRunner().invoke(
        app,
        [
            "manifest",
            "validate",
            "layer",
            "manifests/layers/tree_canopy_pct.yaml",
        ],
    )

    assert result.exit_code == 0
    assert "tree_canopy_pct" in result.output


def test_risk_index_layer_manifest_validates() -> None:
    result = CliRunner().invoke(
        app,
        [
            "manifest",
            "validate",
            "layer",
            "manifests/layers/risk_index.yaml",
        ],
    )

    assert result.exit_code == 0
    assert "risk_index" in result.output


def test_walkability_index_layer_manifest_validates() -> None:
    result = CliRunner().invoke(
        app,
        [
            "manifest",
            "validate",
            "layer",
            "manifests/layers/walkability_index.yaml",
        ],
    )

    assert result.exit_code == 0
    assert "walkability_index" in result.output


def test_flood_sfha_layer_manifest_validates() -> None:
    result = CliRunner().invoke(
        app,
        [
            "manifest",
            "validate",
            "layer",
            "manifests/layers/flood_sfha.yaml",
        ],
    )

    assert result.exit_code == 0
    assert "flood_sfha" in result.output


def test_effective_tax_rate_layer_manifest_validates() -> None:
    result = CliRunner().invoke(
        app,
        [
            "manifest",
            "validate",
            "layer",
            "manifests/layers/effective_tax_rate.yaml",
        ],
    )

    assert result.exit_code == 0
    assert "effective_tax_rate" in result.output


def test_light_pollution_layer_manifest_validates() -> None:
    result = CliRunner().invoke(
        app,
        [
            "manifest",
            "validate",
            "layer",
            "manifests/layers/light_pollution_radiance.yaml",
        ],
    )

    assert result.exit_code == 0
    assert "light_pollution_radiance" in result.output


def test_median_home_value_layer_manifest_validates() -> None:
    result = CliRunner().invoke(
        app,
        [
            "manifest",
            "validate",
            "layer",
            "manifests/layers/median_home_value.yaml",
        ],
    )

    assert result.exit_code == 0
    assert "median_home_value" in result.output


def test_park_access_layer_manifest_validates() -> None:
    result = CliRunner().invoke(
        app,
        [
            "manifest",
            "validate",
            "layer",
            "manifests/layers/park_access.yaml",
        ],
    )

    assert result.exit_code == 0
    assert "park_access" in result.output


def test_park_distance_layer_manifest_validates() -> None:
    result = CliRunner().invoke(
        app,
        [
            "manifest",
            "validate",
            "layer",
            "manifests/layers/park_distance_m.yaml",
        ],
    )

    assert result.exit_code == 0
    assert "park_distance_m" in result.output


def test_credential_gated_access_manifests_validate() -> None:
    manifests = [
        "transit_access.yaml",
        "transit_distance_m.yaml",
        "commute_minutes_center_city_philadelphia.yaml",
        "commute_minutes_grand_central.yaml",
    ]
    for manifest in manifests:
        result = CliRunner().invoke(
            app,
            ["manifest", "validate", "layer", f"manifests/layers/{manifest}"],
        )

        assert result.exit_code == 0, result.output


def test_aqi_manifest_validates() -> None:
    result = CliRunner().invoke(
        app,
        [
            "manifest",
            "validate",
            "layer",
            "manifests/layers/aqi_annual_mean.yaml",
        ],
    )

    assert result.exit_code == 0
    assert "aqi_annual_mean" in result.output


def test_layer_runner_accepts_aqi_key_before_database_work(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = CliRunner().invoke(
        app,
        ["layer", "run", "aqi_annual_mean", "--region", "pa-mainline", "--grain", "tract"],
    )

    assert result.exit_code != 0
    assert "not implemented yet" not in result.output


def test_layer_runner_accepts_park_keys_before_database_work(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for key in ("park_access", "park_distance_m"):
        result = CliRunner().invoke(
            app,
            ["layer", "run", key, "--region", "hudson-valley", "--grain", "both"],
        )

        assert result.exit_code != 0
        assert "not implemented yet" not in result.output


def test_layer_runner_accepts_transit_and_commute_keys_before_database_work(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("TRANSITLAND_API_KEY", "test")
    monkeypatch.setenv("ORS_API_KEY", "test")
    cases = [
        ("transit_access", "pa-mainline"),
        ("transit_distance_m", "hudson-valley"),
        ("commute_minutes_center_city_philadelphia", "pa-mainline"),
        ("commute_minutes_grand_central", "hudson-valley"),
    ]
    for key, region in cases:
        result = CliRunner().invoke(
            app,
            ["layer", "run", key, "--region", region, "--grain", "both"],
        )

        assert result.exit_code != 0
        assert "not implemented yet" not in result.output


def test_region_add_requires_database_url(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = CliRunner().invoke(
        app,
        ["region", "add", "manifests/regions/pa-mainline.yaml"],
    )

    assert result.exit_code != 0


def test_layer_runner_rejects_invalid_grain() -> None:
    result = CliRunner().invoke(
        app,
        ["layer", "run", "canopy_height_m", "--region", "hudson-valley", "--grain", "bad"],
    )

    assert result.exit_code != 0


def test_layer_runner_accepts_tree_canopy_key_before_database_work(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = CliRunner().invoke(
        app,
        ["layer", "run", "tree_canopy_pct", "--region", "hudson-valley", "--grain", "both"],
    )

    assert result.exit_code != 0
    assert "not implemented yet" not in result.output


def test_layer_runner_accepts_risk_index_key_before_database_work(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = CliRunner().invoke(
        app,
        ["layer", "run", "risk_index", "--region", "hudson-valley", "--grain", "tract"],
    )

    assert result.exit_code != 0
    assert "not implemented yet" not in result.output


def test_layer_runner_accepts_walkability_key_before_database_work(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = CliRunner().invoke(
        app,
        ["layer", "run", "walkability_index", "--region", "hudson-valley", "--grain", "both"],
    )

    assert result.exit_code != 0
    assert "not implemented yet" not in result.output


def test_layer_runner_accepts_flood_sfha_key_before_database_work(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = CliRunner().invoke(
        app,
        ["layer", "run", "flood_sfha", "--region", "hudson-valley", "--grain", "both"],
    )

    assert result.exit_code != 0
    assert "not implemented yet" not in result.output


def test_layer_runner_accepts_effective_tax_key_before_database_work(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = CliRunner().invoke(
        app,
        ["layer", "run", "effective_tax_rate", "--region", "hudson-valley", "--grain", "tract"],
    )

    assert result.exit_code != 0
    assert "not implemented yet" not in result.output


def test_layer_runner_accepts_light_pollution_key_before_database_work(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = CliRunner().invoke(
        app,
        [
            "layer",
            "run",
            "light_pollution_radiance",
            "--region",
            "hudson-valley",
            "--grain",
            "tract",
        ],
    )

    assert result.exit_code != 0
    assert "not implemented yet" not in result.output


def test_layer_runner_accepts_median_home_value_key_before_database_work(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = CliRunner().invoke(
        app,
        ["layer", "run", "median_home_value", "--region", "hudson-valley", "--grain", "tract"],
    )

    assert result.exit_code != 0
    assert "not implemented yet" not in result.output


def test_layer_manifest_validates(tmp_path) -> None:
    manifest = tmp_path / "light_pollution_radiance.yaml"
    manifest.write_text(
        """
metric_key: light_pollution_radiance
name: Light pollution radiance
source: VIIRS VNL V2 annual median
source_urls:
  - https://example.com/viirs.tif
vintage: "2024"
units: nW/cm2/sr
direction: lower_better
native_resolution: ~500m
allowed_range: [0, 500]
reduction_method: zonal_mean
coverage_threshold: 0.99
grains:
  - tract
notes: Neighborhood context only at this native resolution.
"""
    )

    result = CliRunner().invoke(app, ["manifest", "validate", "layer", str(manifest)])

    assert result.exit_code == 0
    assert "light_pollution_radiance" in result.output
