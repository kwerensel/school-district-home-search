"""Read-only diagnostics; experiments never authorize model release."""
from __future__ import annotations
import math
from pathlib import Path
import numpy as np
import psycopg
from gt.archetypes import METRIC_KEYS, percentile_normalize, select_kmeans
from gt.db.migrate import database_url
from gt.reports import ValidationReport, write_report

# Proposed diagnostic grouping, not a production weighting change.
THEMES = {
    "green": ("tree_canopy_pct", "canopy_height_m", "gvi_ndvi_street"),
    "access": ("walkability_index", "park_access", "transit_access", "commute_minutes"),
    "environmental_risk": ("risk_index", "flood_sfha", "aqi_annual_mean"),
    "noise": ("noise_pct_over_55", "noise_siren_density", "noise_nightlife_density", "noise_industrial_land_pct", "noise_freight_rail_density"),
    "night_sky": ("light_pollution_radiance",),
}


def adjusted_rand(left: np.ndarray, right: np.ndarray) -> float:
    """Chance-adjusted pair agreement, invariant to cluster IDs."""
    if left.ndim != 1 or right.shape != left.shape or len(left) < 2:
        raise ValueError("Two equally sized partitions with at least two rows required")
    _, a = np.unique(left, return_inverse=True)
    _, b = np.unique(right, return_inverse=True)
    table = np.zeros((int(a.max()) + 1, int(b.max()) + 1), dtype=int)
    np.add.at(table, (a, b), 1)
    def pairs(values): return float(np.sum(values * (values - 1) / 2))
    matched = pairs(table)
    a_pairs, b_pairs = pairs(table.sum(axis=1)), pairs(table.sum(axis=0))
    expected = a_pairs * b_pairs / math.comb(len(left), 2)
    maximum = (a_pairs + b_pairs) / 2
    return (matched - expected) / (maximum - expected) if maximum != expected else 1.0


def matrix_diagnostics(raw: np.ndarray) -> dict:
    if raw.ndim != 2 or raw.shape[1] != len(METRIC_KEYS) or len(raw) < 6:
        raise ValueError("At least six districts and the complete planned feature set required")
    matrix = percentile_normalize(raw)
    variance = np.var(matrix, axis=0)
    total = float(variance.sum())
    correlations = []
    for i, first in enumerate(METRIC_KEYS):
        for j in range(i + 1, len(METRIC_KEYS)):
            if variance[i] > 0 and variance[j] > 0:
                value = float(np.corrcoef(matrix[:, i], matrix[:, j])[0, 1])
                correlations.append({"first": first, "second": METRIC_KEYS[j], "correlation": value})
    correlations.sort(key=lambda row: (-abs(row["correlation"]), row["first"], row["second"]))
    weights = np.ones(len(METRIC_KEYS))
    themes = []
    for name, keys in THEMES.items():
        indexes = [METRIC_KEYS.index(key) for key in keys]
        weights[indexes] = 1 / math.sqrt(len(keys))
        themes.append({"theme": name, "metric_keys": list(keys), "metric_count": len(keys),
                       "current_squared_distance_share": float(variance[indexes].sum() / total) if total else 0.0})
    experiments = []
    for name, values in (("current_equal_metric_weights", matrix), ("proposed_equal_theme_weights", matrix * weights)):
        labels, _, _, k, score = select_kmeans(values)
        agreements, cluster_counts = [], []
        rng = np.random.default_rng(20261019)
        for _ in range(24):
            # Fixed full-cohort percentiles isolate fit sensitivity, not independent validation.
            subset = np.sort(rng.choice(len(values), max(5, int(len(values) * .9)), replace=False))
            _, centers, _, count, _ = select_kmeans(values[subset])
            predicted = ((values[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
            agreements.append(adjusted_rand(labels, predicted))
            cluster_counts.append(count)
        experiments.append({"name": name, "k": k, "silhouette_in_experiment_space": score,
            "cluster_sizes": [int((labels == c).sum()) for c in range(k)],
            "subsample_stability": {"runs": 24, "retained_fraction": .9, "percentiles": "fixed_full_cohort",
                "adjusted_rand_min": min(agreements), "adjusted_rand_median": float(np.median(agreements)),
                "adjusted_rand_max": max(agreements), "selected_cluster_counts": cluster_counts}})
    return {"district_count": len(raw), "metric_keys": list(METRIC_KEYS),
            "missing_by_metric": {key: int((~np.isfinite(raw[:, i])).sum()) for i, key in enumerate(METRIC_KEYS)},
            "themes": themes, "strong_correlations_abs_ge_0_8": [row for row in correlations if abs(row["correlation"]) >= .8],
            "experiments": experiments, "model_persisted": False,
            "limitations": ["Theme grouping is proposed; production weights and release gate are unchanged.",
                "Scores in different weighted spaces are not directly comparable evidence of improvement.",
                "Subsample agreement measures sensitivity, not truth or independent predictive accuracy.",
                "Current single-start KMeans is used; this does not supersede the broader multistart audit."]}


def audit_archetypes() -> Path:
    from gt.archetypes import _load_district_matrix
    with psycopg.connect(database_url(), autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout = '30s'")
        _, matrix, _ = _load_district_matrix(conn)
    report = ValidationReport(report_type="archetype_audit", target="post-gvi-design-review",
                              status="diagnostic_only", promotable=False, checks=matrix_diagnostics(matrix))
    return write_report(report, "archetypes_design_audit_latest.json")
