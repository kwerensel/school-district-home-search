from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import os
from typing import Any
from urllib.request import Request, urlopen

import numpy as np
import psycopg
from psycopg.types.json import Jsonb

from gt.db.migrate import database_url
from gt.reports import ValidationReport, write_report


METRIC_KEYS = (
    "tree_canopy_pct",
    "canopy_height_m",
    "walkability_index",
    "risk_index",
    "flood_sfha",
    "light_pollution_radiance",
    "park_access",
    "transit_access",
    "commute_minutes",
    "aqi_annual_mean",
    "noise_pct_over_55",
    "noise_siren_density",
    "noise_nightlife_density",
    "noise_industrial_land_pct",
    "noise_freight_rail_density",
)
COMMUTE_KEYS = (
    "commute_minutes_center_city_philadelphia",
    "commute_minutes_grand_central",
)
MIN_K = 4
MAX_K = 9
MIN_ACCEPTABLE_SILHOUETTE = 0.25
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-20250514"


@dataclass(frozen=True)
class ArchetypeBuildResult:
    model_version: str
    district_count: int
    cluster_count: int
    silhouette: float
    missing_by_metric: dict[str, int]
    cluster_sizes: dict[int, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "district_count": self.district_count,
            "cluster_count": self.cluster_count,
            "silhouette": self.silhouette,
            "missing_by_metric": self.missing_by_metric,
            "cluster_sizes": self.cluster_sizes,
        }


@dataclass(frozen=True)
class PendingArchetypeLabel:
    archetype_id: int
    cluster_index: int
    label: str
    one_line_description: str


def label_archetypes(
    model_version: str = "latest",
    *,
    model: str | None = None,
    requester: Any | None = None,
) -> list[PendingArchetypeLabel]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if requester is None and not api_key:
        raise RuntimeError("Set ANTHROPIC_API_KEY before labeling archetypes")
    resolved_model = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL
    request_label = requester or (
        lambda distinguishing: _request_anthropic_label(
            distinguishing, api_key=str(api_key), model=resolved_model
        )
    )
    with psycopg.connect(database_url(), autocommit=False) as conn:
        resolved_version = _resolve_model_version(conn, model_version)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, cluster_index, distinguishing_metrics
                FROM archetypes
                WHERE model_version = %s
                ORDER BY cluster_index
                """,
                (resolved_version,),
            )
            rows = cur.fetchall()
        if not rows:
            raise RuntimeError(f"No archetypes found for {resolved_version}")
        pending: list[PendingArchetypeLabel] = []
        for archetype_id, cluster_index, distinguishing in rows:
            label, description = request_label(distinguishing)
            parsed = _validate_label(label, description)
            pending.append(
                PendingArchetypeLabel(
                    archetype_id=int(archetype_id),
                    cluster_index=int(cluster_index),
                    label=parsed[0],
                    one_line_description=parsed[1],
                )
            )
        with conn.cursor() as cur:
            cur.executemany(
                """
                UPDATE archetypes
                SET label = %s,
                    one_line_description = %s,
                    label_status = 'pending'
                WHERE id = %s
                """,
                [
                    (item.label, item.one_line_description, item.archetype_id)
                    for item in pending
                ],
            )
        conn.commit()
    return pending


def approve_archetype_labels(model_version: str) -> int:
    with psycopg.connect(database_url(), autocommit=False) as conn:
        resolved_version = _resolve_model_version(conn, model_version)
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE archetypes
                SET label_status = 'approved'
                WHERE model_version = %s
                  AND label_status = 'pending'
                  AND label IS NOT NULL
                  AND one_line_description IS NOT NULL
                """,
                (resolved_version,),
            )
            count = int(cur.rowcount)
        conn.commit()
    return count


def build_archetypes() -> tuple[ArchetypeBuildResult, str]:
    with psycopg.connect(database_url(), autocommit=False) as conn:
        district_ids, raw_matrix, missing_by_metric = _load_district_matrix(conn)
        matrix = percentile_normalize(raw_matrix)
        labels, centroids, distances, best_k, silhouette = select_kmeans(matrix)
        if silhouette < MIN_ACCEPTABLE_SILHOUETTE:
            raise RuntimeError(
                "Best k-means silhouette "
                f"{silhouette:.3f} is below {MIN_ACCEPTABLE_SILHOUETTE:.2f}; "
                "the approved HDBSCAN fallback is required before persistence."
            )
        model_version = _model_version(district_ids, matrix)
        distinguishing = distinguishing_metrics(centroids)
        _persist_model(
            conn,
            model_version,
            district_ids,
            labels,
            centroids,
            distances,
            silhouette,
            distinguishing,
        )
        conn.commit()

    cluster_sizes = {
        cluster: int(np.sum(labels == cluster)) for cluster in range(best_k)
    }
    result = ArchetypeBuildResult(
        model_version=model_version,
        district_count=len(district_ids),
        cluster_count=best_k,
        silhouette=silhouette,
        missing_by_metric=missing_by_metric,
        cluster_sizes=cluster_sizes,
    )
    report = ValidationReport(
        report_type="archetypes",
        target=model_version,
        status="ready",
        promotable=True,
        checks=result.as_dict(),
    )
    path = write_report(report, f"archetypes_{model_version}.json")
    return result, str(path)


def percentile_normalize(values: np.ndarray) -> np.ndarray:
    if values.ndim != 2:
        raise ValueError("Expected a two-dimensional district metric matrix")
    normalized = np.full(values.shape, 0.5, dtype=float)
    for column_index in range(values.shape[1]):
        column = values[:, column_index]
        finite_mask = np.isfinite(column)
        finite = column[finite_mask]
        if finite.size <= 1:
            continue
        order = np.argsort(finite, kind="mergesort")
        sorted_values = finite[order]
        ranks = np.empty(finite.size, dtype=float)
        start = 0
        while start < finite.size:
            end = start + 1
            while end < finite.size and sorted_values[end] == sorted_values[start]:
                end += 1
            average_rank = (start + end - 1) / 2
            ranks[order[start:end]] = average_rank / (finite.size - 1)
            start = end
        normalized[finite_mask, column_index] = ranks
    return normalized


def kmeans(
    matrix: np.ndarray, k: int, *, max_iterations: int = 200
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if matrix.ndim != 2 or not np.isfinite(matrix).all():
        raise ValueError("K-means requires a finite two-dimensional matrix")
    if k < 2 or k >= matrix.shape[0]:
        raise ValueError("k must be at least 2 and smaller than the row count")
    centroids = _deterministic_initial_centroids(matrix, k)
    labels = np.full(matrix.shape[0], -1, dtype=int)
    for _ in range(max_iterations):
        squared = ((matrix[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
        next_labels = squared.argmin(axis=1)
        if np.array_equal(labels, next_labels):
            break
        labels = next_labels
        for cluster in range(k):
            members = matrix[labels == cluster]
            if members.size:
                centroids[cluster] = members.mean(axis=0)
            else:
                nearest = squared.min(axis=1)
                centroids[cluster] = matrix[int(nearest.argmax())]
    distances = np.linalg.norm(matrix - centroids[labels], axis=1)
    return labels, centroids, distances


def silhouette_score(matrix: np.ndarray, labels: np.ndarray) -> float:
    unique = np.unique(labels)
    if unique.size < 2 or unique.size >= matrix.shape[0]:
        return -1.0
    pairwise = np.linalg.norm(matrix[:, None, :] - matrix[None, :, :], axis=2)
    scores: list[float] = []
    for index, label in enumerate(labels):
        same = np.flatnonzero(labels == label)
        same = same[same != index]
        if same.size == 0:
            scores.append(0.0)
            continue
        a = float(pairwise[index, same].mean())
        b = min(
            float(pairwise[index, labels == other].mean())
            for other in unique
            if other != label
        )
        denominator = max(a, b)
        scores.append((b - a) / denominator if denominator else 0.0)
    return float(np.mean(scores))


def select_kmeans(
    matrix: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, float]:
    candidates: list[tuple[float, int, np.ndarray, np.ndarray, np.ndarray]] = []
    for k in range(MIN_K, min(MAX_K, matrix.shape[0] - 1) + 1):
        labels, centroids, distances = kmeans(matrix, k)
        candidates.append((silhouette_score(matrix, labels), k, labels, centroids, distances))
    if not candidates:
        raise ValueError("At least five districts are required to build archetypes")
    score, k, labels, centroids, distances = max(candidates, key=lambda item: (item[0], -item[1]))
    return labels, centroids, distances, k, score


def distinguishing_metrics(centroids: np.ndarray) -> list[list[dict[str, Any]]]:
    global_median = 0.5
    output: list[list[dict[str, Any]]] = []
    for centroid in centroids:
        indexes = sorted(
            range(len(METRIC_KEYS)),
            key=lambda index: (-abs(float(centroid[index]) - global_median), METRIC_KEYS[index]),
        )[:5]
        output.append(
            [
                {
                    "metric_key": METRIC_KEYS[index],
                    "percentile": round(float(centroid[index]), 6),
                    "delta_from_median": round(float(centroid[index]) - global_median, 6),
                    "level": "high" if centroid[index] >= global_median else "low",
                }
                for index in indexes
            ]
        )
    return output


def _request_anthropic_label(
    distinguishing: list[dict[str, Any]], *, api_key: str, model: str
) -> tuple[str, str]:
    prompt = (
        "Name one home-search district archetype from the verified percentile features below. "
        "Return JSON only with string fields label and one_line_description. The label must be "
        "2-5 neutral consumer-friendly words. The description must be one sentence, avoid claims "
        "about individual homes, and mention no numbers not supplied here. Features:\n"
        + json.dumps(distinguishing, sort_keys=True)
    )
    payload = json.dumps(
        {
            "model": model,
            "max_tokens": 180,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()
    request = Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        body = json.loads(response.read().decode())
    blocks = body.get("content", [])
    text = "".join(str(block.get("text", "")) for block in blocks if block.get("type") == "text")
    return _parse_label_response(text)


def _parse_label_response(text: str) -> tuple[str, str]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```")
        cleaned = cleaned.removesuffix("```").strip()
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("Archetype label response must be a JSON object")
    return _validate_label(payload.get("label"), payload.get("one_line_description"))


def _validate_label(label: Any, description: Any) -> tuple[str, str]:
    if not isinstance(label, str) or not 2 <= len(label.split()) <= 5 or len(label) > 60:
        raise ValueError("Archetype label must contain 2-5 words and at most 60 characters")
    if not isinstance(description, str) or not 20 <= len(description) <= 240:
        raise ValueError("Archetype description must contain 20-240 characters")
    return label.strip(), description.strip()


def _resolve_model_version(conn: psycopg.Connection[Any], model_version: str) -> str:
    if model_version != "latest":
        return model_version
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT model_version
            FROM archetype_models
            WHERE status = 'ready'
            ORDER BY created_at DESC, model_version DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError("No ready archetype model is available")
    return str(row[0])


def _deterministic_initial_centroids(matrix: np.ndarray, k: int) -> np.ndarray:
    center = matrix.mean(axis=0)
    first = int(np.linalg.norm(matrix - center, axis=1).argmax())
    indexes = [first]
    while len(indexes) < k:
        distances = np.min(
            np.stack([np.linalg.norm(matrix - matrix[index], axis=1) for index in indexes]),
            axis=0,
        )
        distances[indexes] = -1
        indexes.append(int(distances.argmax()))
    return matrix[indexes].copy()


def _load_district_matrix(
    conn: psycopg.Connection[Any],
) -> tuple[list[int], np.ndarray, dict[str, int]]:
    source_keys = tuple(key for key in METRIC_KEYS if key != "commute_minutes") + COMMUTE_KEYS
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH latest AS (
              SELECT
                dm.district_region_id,
                dm.metric_key,
                dm.value,
                row_number() OVER (
                  PARTITION BY dm.district_region_id, dm.metric_key
                  ORDER BY dm.computed_at DESC, dm.vintage DESC
                ) AS recency
              FROM district_metrics dm
              JOIN regions r ON r.id = dm.district_region_id
              WHERE r.region_type = 'school_district'
                AND dm.metric_key = ANY(%s)
            )
            SELECT district_region_id, metric_key, value
            FROM latest
            WHERE recency = 1
            ORDER BY district_region_id, metric_key
            """,
            (list(source_keys),),
        )
        rows = cur.fetchall()
        cur.execute(
            """
            SELECT id
            FROM regions
            WHERE region_type = 'school_district'
              AND region_group IN ('pa-mainline', 'hudson-valley')
            ORDER BY id
            """
        )
        district_ids = [int(row[0]) for row in cur.fetchall()]
    if not district_ids:
        raise RuntimeError("No active school-district regions are available")
    values_by_district: dict[int, dict[str, float]] = {district_id: {} for district_id in district_ids}
    for district_id, metric_key, value in rows:
        if int(district_id) not in values_by_district:
            continue
        canonical_key = "commute_minutes" if metric_key in COMMUTE_KEYS else str(metric_key)
        values_by_district[int(district_id)][canonical_key] = float(value)
    matrix = np.array(
        [
            [values_by_district[district_id].get(metric_key, math.nan) for metric_key in METRIC_KEYS]
            for district_id in district_ids
        ],
        dtype=float,
    )
    missing = {
        metric_key: int(np.sum(~np.isfinite(matrix[:, index])))
        for index, metric_key in enumerate(METRIC_KEYS)
    }
    return district_ids, matrix, missing


def _model_version(district_ids: list[int], matrix: np.ndarray) -> str:
    payload = {
        "algorithm": "deterministic-kmeans-silhouette-v1",
        "district_ids": district_ids,
        "metric_keys": METRIC_KEYS,
        "matrix": np.round(matrix, 8).tolist(),
    }
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return f"archetypes-v1-{digest[:12]}"


def _persist_model(
    conn: psycopg.Connection[Any],
    model_version: str,
    district_ids: list[int],
    labels: np.ndarray,
    centroids: np.ndarray,
    distances: np.ndarray,
    silhouette: float,
    distinguishing: list[list[dict[str, Any]]],
) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM archetype_models WHERE model_version = %s", (model_version,))
        cur.execute(
            """
            INSERT INTO archetype_models
              (model_version, metric_keys, district_count, cluster_count, silhouette, status)
            VALUES (%s, %s, %s, %s, %s, 'ready')
            """,
            (
                model_version,
                Jsonb(list(METRIC_KEYS)),
                len(district_ids),
                len(centroids),
                silhouette,
            ),
        )
        archetype_ids: dict[int, int] = {}
        for cluster_index, centroid in enumerate(centroids):
            cur.execute(
                """
                INSERT INTO archetypes
                  (model_version, cluster_index, centroid, distinguishing_metrics, silhouette)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    model_version,
                    cluster_index,
                    Jsonb(
                        {
                            metric_key: round(float(centroid[index]), 8)
                            for index, metric_key in enumerate(METRIC_KEYS)
                        }
                    ),
                    Jsonb(distinguishing[cluster_index]),
                    silhouette,
                ),
            )
            archetype_ids[cluster_index] = int(cur.fetchone()[0])
        cur.executemany(
            """
            INSERT INTO region_archetypes
              (region_id, archetype_id, model_version, distance)
            VALUES (%s, %s, %s, %s)
            """,
            [
                (
                    district_id,
                    archetype_ids[int(labels[index])],
                    model_version,
                    float(distances[index]),
                )
                for index, district_id in enumerate(district_ids)
            ],
        )
