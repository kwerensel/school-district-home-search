from __future__ import annotations

from pathlib import Path

import typer

from gt.db.migrate import run_migrations
from gt.layers import (
    promote_layer,
    render_layer_qa,
    run_canopy_height,
    run_effective_tax_rate,
    run_flood_sfha,
    run_light_pollution,
    run_risk_index,
    run_tree_canopy,
    run_walkability,
)
from gt.manifests import LayerManifest, RegionManifest, load_manifest
from gt.region import add_region, promote_region, render_region_qa, validate_region_report
from gt.reports import read_report
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

region_app = typer.Typer(help="Region scaffold commands.")
app.add_typer(region_app, name="region")

manifest_app = typer.Typer(help="Manifest validation commands.")
app.add_typer(manifest_app, name="manifest")

qa_app = typer.Typer(help="Visual QA scaffolding commands.")
app.add_typer(qa_app, name="qa")

layer_app = typer.Typer(help="Layer runner commands.")
app.add_typer(layer_app, name="layer")


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


@region_app.command("add")
def region_add(manifest: Path) -> None:
    """Stage TIGER/NCES region geometry and write a validation report."""
    report, path = add_region(manifest)
    payload = report.as_dict() | {"report_path": str(path)}
    typer.echo(json_dumps(payload))


@manifest_app.command("validate")
def manifest_validate(
    manifest_type: str = typer.Argument(..., help="'region' or 'layer'."),
    manifest: Path = typer.Argument(..., help="Path to a YAML manifest."),
) -> None:
    """Validate a region or layer manifest."""
    models = {"region": RegionManifest, "layer": LayerManifest}
    if manifest_type not in models:
        raise typer.BadParameter("manifest_type must be 'region' or 'layer'")
    parsed = load_manifest(manifest, models[manifest_type])
    typer.echo(json_dumps(parsed.model_dump(mode="json")))


@app.command()
def validate(
    report: str = typer.Option("latest", help="Report name in data/reports."),
    region: str | None = typer.Option(None, help="Re-run public region checks."),
) -> None:
    """Re-run checks when possible, then fail when the report is not promotable."""
    if region:
        validation, path = validate_region_report(region)
        payload = validation.as_dict() | {"report_path": str(path)}
    else:
        payload = read_report(report)
    typer.echo(json_dumps(payload))
    if not payload.get("promotable", False):
        raise typer.Exit(1)


@app.command()
def promote(report: str = typer.Option("latest", help="Report name in data/reports.")) -> None:
    """Refuse promotion unless a report is explicitly promotable."""
    payload = read_report(report)
    if not payload.get("promotable", False):
        typer.echo("Promotion refused: validation report is not promotable.")
        raise typer.Exit(1)
    if payload.get("report_type") == "region_scaffold":
        promote_region(str(payload["target"]))
        typer.echo(f"Promoted region scaffold for {payload['target']}.")
        return
    if payload.get("report_type") == "layer":
        metric_key, region_slug = str(payload["target"]).split(":", 1)
        promote_layer(_layer_manifest_path(metric_key), region_slug)
        typer.echo(f"Promoted {metric_key} for {region_slug}.")
        return
    typer.echo("Promotion scaffold accepted; no promoter is registered for this report type.")


@qa_app.command("map")
def qa_map(layer: str, region: str = typer.Option(..., help="Region slug.")) -> None:
    """Render a region-boundary or staged metric QA map."""
    if layer in {"regions", "geometry", "boundaries"}:
        path = render_region_qa(region)
    else:
        path = render_layer_qa(_layer_manifest_path(layer), region)
    typer.echo(str(path))


@layer_app.command("run")
def layer_run(
    key: str,
    region: str = typer.Option(..., help="Region slug."),
    grain: str = typer.Option("both", help="tract, listing, or both."),
) -> None:
    """Run an approved layer into staging and write a validation report."""
    if grain not in {"tract", "listing", "both"}:
        raise typer.BadParameter("grain must be tract, listing, or both")
    layer_runners = {
        "canopy_height_m": run_canopy_height,
        "effective_tax_rate": run_effective_tax_rate,
        "flood_sfha": run_flood_sfha,
        "light_pollution_radiance": run_light_pollution,
        "risk_index": run_risk_index,
        "tree_canopy_pct": run_tree_canopy,
        "walkability_index": run_walkability,
    }
    runner = layer_runners.get(key)
    if runner is None:
        typer.echo(f"Layer '{key}' is not implemented yet.")
        raise typer.Exit(1)
    report, path = runner(_layer_manifest_path(key), region, grain)
    payload = report.as_dict() | {"report_path": str(path)}
    typer.echo(json_dumps(payload))


def _layer_manifest_path(key: str) -> Path:
    return Path("manifests") / "layers" / f"{key}.yaml"


def json_dumps(value: object) -> str:
    import json

    return json.dumps(value, indent=2, sort_keys=True)
