from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import geopandas as gpd
import psycopg

from gt.db.migrate import database_url, repo_root
from gt.manifests import LayerManifest, load_layer_manifest


def promote_layer(manifest_path: Path, region_slug: str) -> None:
    manifest = load_layer_manifest(manifest_path)
    with psycopg.connect(database_url(), autocommit=False) as conn:
        with conn.cursor() as cur:
            _promote_metric_definition(cur, manifest)
            _promote_region_metrics(cur, manifest, region_slug)
            _promote_listing_metrics(cur, manifest, region_slug)
            cur.execute("REFRESH MATERIALIZED VIEW district_metrics")
        conn.commit()


def render_layer_qa(manifest_path: Path, region_slug: str) -> Path:
    manifest = load_layer_manifest(manifest_path)
    qa_dir = repo_root() / "data" / "reports" / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(qa_dir / ".matplotlib-cache"))
    os.environ.setdefault("XDG_CACHE_HOME", str(qa_dir / ".cache"))

    import matplotlib.pyplot as plt

    with psycopg.connect(database_url()) as conn:
        frame = gpd.read_postgis(
            """
            SELECT r.slug, r.name, r.geom, s.value
            FROM staging.layer_region_metrics s
            JOIN regions r ON r.slug = s.region_slug
            WHERE s.region_group = %s
              AND s.metric_key = %s
              AND s.vintage = %s
            """,
            conn,
            params=(region_slug, manifest.metric_key, manifest.vintage),
            geom_col="geom",
        )
        listing_frame = gpd.GeoDataFrame()
        if frame.empty:
            listing_frame = gpd.read_postgis(
                """
                SELECT l.id, l.geom, s.value
                FROM staging.layer_listing_metrics s
                JOIN listings l ON l.id = s.listing_id
                WHERE s.region_group = %s
                  AND s.metric_key = %s
                  AND s.vintage = %s
                  AND s.grain = 'point'
                """,
                conn,
                params=(region_slug, manifest.metric_key, manifest.vintage),
                geom_col="geom",
            )
    if frame.empty and listing_frame.empty:
        raise RuntimeError(f"No staged {manifest.metric_key} metrics for {region_slug}")

    path = qa_dir / f"{manifest.metric_key}_{region_slug}.png"
    fig, ax = plt.subplots(figsize=(10, 10))
    if not frame.empty:
        frame.plot(
            column="value",
            ax=ax,
            legend=True,
            cmap="Greens",
            linewidth=0.1,
            edgecolor="#374151",
        )
    else:
        listing_frame.plot(
            column="value",
            ax=ax,
            legend=True,
            cmap="viridis_r" if manifest.direction == "lower_better" else "viridis",
            markersize=3,
            alpha=0.8,
        )
    ax.set_title(f"{region_slug}: {manifest.name} ({manifest.units or 'value'})")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def _promote_metric_definition(cur: psycopg.Cursor[Any], manifest: LayerManifest) -> None:
    grain = "school_district" if manifest.metric_key == "median_home_value" else "census_tract"
    cur.execute(
        """
        INSERT INTO metric_definitions
          (metric_key, name, units, direction, source, grain, native_resolution, notes)
        VALUES
          (%s, %s, %s, %s, %s, %s::region_type, %s, %s)
        ON CONFLICT (metric_key) DO UPDATE SET
          name = EXCLUDED.name,
          units = EXCLUDED.units,
          direction = EXCLUDED.direction,
          source = EXCLUDED.source,
          grain = EXCLUDED.grain,
          native_resolution = EXCLUDED.native_resolution,
          notes = EXCLUDED.notes
        """,
        (
            manifest.metric_key,
            manifest.name,
            manifest.units,
            manifest.direction,
            f"{manifest.source} ({manifest.vintage})",
            grain,
            manifest.native_resolution,
            manifest.notes,
        ),
    )


def _promote_region_metrics(
    cur: psycopg.Cursor[Any], manifest: LayerManifest, region_slug: str
) -> None:
    cur.execute(
        """
        DELETE FROM region_metrics rm
        USING regions r
        WHERE rm.region_id = r.id
          AND r.region_group = %s
          AND rm.metric_key = %s
          AND rm.vintage = %s
        """,
        (region_slug, manifest.metric_key, manifest.vintage),
    )
    cur.execute(
        """
        INSERT INTO region_metrics (region_id, metric_key, value, vintage)
        SELECT r.id, s.metric_key, s.value, s.vintage
        FROM staging.layer_region_metrics s
        JOIN regions r ON r.slug = s.region_slug
        WHERE s.region_group = %s
          AND s.metric_key = %s
          AND s.vintage = %s
        ON CONFLICT (region_id, metric_key, vintage) DO UPDATE SET
          value = EXCLUDED.value,
          computed_at = now()
        """,
        (region_slug, manifest.metric_key, manifest.vintage),
    )


def _promote_listing_metrics(
    cur: psycopg.Cursor[Any], manifest: LayerManifest, region_slug: str
) -> None:
    cur.execute(
        """
        DELETE FROM listing_metrics lm
        USING listings l
        WHERE lm.listing_id = l.id
          AND l.region_slug = %s
          AND lm.metric_key = %s
          AND lm.vintage = %s
        """,
        (region_slug, manifest.metric_key, manifest.vintage),
    )
    cur.execute(
        """
        INSERT INTO listing_metrics (listing_id, metric_key, grain, value, vintage)
        SELECT listing_id, metric_key, grain, value, vintage
        FROM staging.layer_listing_metrics
        WHERE region_group = %s
          AND metric_key = %s
          AND vintage = %s
        ON CONFLICT (listing_id, metric_key, grain, vintage) DO UPDATE SET
          value = EXCLUDED.value,
          computed_at = now()
        """,
        (region_slug, manifest.metric_key, manifest.vintage),
    )
