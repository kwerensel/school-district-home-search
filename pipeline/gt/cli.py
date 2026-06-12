from __future__ import annotations

import typer

app = typer.Typer(
    name="gt",
    help="Groundtruth deterministic geospatial pipeline.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Run Groundtruth pipeline commands."""


@app.command()
def version() -> None:
    """Print the pipeline CLI version."""
    typer.echo("gt 0.1.0")

