from __future__ import annotations

import typer

from gt.db.migrate import run_migrations
from gt.recovery.load_frozen import load_frozen_dataset

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


db_app = typer.Typer(help="Database migration and recovery commands.")
app.add_typer(db_app, name="db")


@db_app.command("migrate")
def db_migrate() -> None:
    """Apply SQL migrations in order against DATABASE_URL."""
    applied = run_migrations()
    if not applied:
        typer.echo("No migrations found.")
        return
    for migration in applied:
        typer.echo(f"Applied {migration}")


@db_app.command("load-frozen")
def db_load_frozen() -> None:
    """Recover local PostGIS tables from frozen GeoJSON and official boundaries."""
    report = load_frozen_dataset()
    typer.echo(json_dumps(report.as_dict()))


def json_dumps(value: object) -> str:
    import json

    return json.dumps(value, indent=2, sort_keys=True)
