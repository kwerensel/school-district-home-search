from typer.testing import CliRunner

from gt.cli import app


def test_help() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Groundtruth deterministic geospatial pipeline" in result.output

