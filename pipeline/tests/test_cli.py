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
