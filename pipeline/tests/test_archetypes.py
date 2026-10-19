import numpy as np

from gt.archetypes import (
    METRIC_KEYS,
    distinguishing_metrics,
    kmeans,
    percentile_normalize,
    _parse_label_response,
    select_kmeans,
    select_hdbscan,
    silhouette_score,
)


def test_percentile_normalize_averages_ties_and_imputes_missing_to_median() -> None:
    values = np.array([[10.0, np.nan], [20.0, 4.0], [20.0, 8.0], [40.0, 12.0]])
    normalized = percentile_normalize(values)

    assert normalized[:, 0].tolist() == [0.0, 0.5, 0.5, 1.0]
    assert normalized[0, 1] == 0.5
    assert normalized[1:, 1].tolist() == [0.0, 0.5, 1.0]


def test_kmeans_is_deterministic_and_separates_obvious_groups() -> None:
    matrix = np.array(
        [
            [0.0, 0.0],
            [0.05, 0.05],
            [0.1, 0.0],
            [0.9, 1.0],
            [0.95, 0.95],
            [1.0, 0.9],
        ]
    )
    first = kmeans(matrix, 2)
    second = kmeans(matrix, 2)

    assert np.array_equal(first[0], second[0])
    assert np.allclose(first[1], second[1])
    assert silhouette_score(matrix, first[0]) > 0.8


def test_select_kmeans_uses_stable_smallest_k_tie_break() -> None:
    groups = []
    for center in (0.0, 0.33, 0.66, 1.0):
        groups.extend([[center, center], [center + 0.01, center], [center, center + 0.01]])
    labels, centroids, distances, k, score = select_kmeans(np.array(groups))

    assert k == 4
    assert len(labels) == 12
    assert centroids.shape == (4, 2)
    assert np.isfinite(distances).all()
    assert score > 0.8


def test_hdbscan_fallback_is_deterministic_and_assigns_noise() -> None:
    rng = np.random.default_rng(11)
    matrix = np.vstack(
        [rng.normal(center, 0.015, size=(12, 2)) for center in (0.1, 0.35, 0.65, 0.9)]
        + [np.array([[0.5, 0.05], [0.5, 0.95]])]
    )
    first = select_hdbscan(matrix)
    second = select_hdbscan(matrix)

    assert np.array_equal(first[0], second[0])
    assert np.all(first[0] >= 0)
    assert 4 <= first[3] <= 9
    assert first[6] >= 0


def test_distinguishing_metrics_emits_five_structured_features() -> None:
    centroid = np.full((1, len(METRIC_KEYS)), 0.5)
    centroid[0, 0] = 0.95
    centroid[0, 1] = 0.1
    output = distinguishing_metrics(centroid)

    assert len(output[0]) == 5
    assert output[0][0]["metric_key"] == "tree_canopy_pct"
    assert output[0][0]["level"] == "high"


def test_label_response_parser_accepts_json_fence_and_rejects_bad_shape() -> None:
    label, description = _parse_label_response(
        '```json\n{"label":"Quiet Green Suburb","one_line_description":"Leafier districts with calmer access patterns."}\n```'
    )
    assert label == "Quiet Green Suburb"
    assert description.startswith("Leafier districts")


def test_noise_assignment_preserves_core_members_even_when_centroids_are_closer():
    from gt.archetypes import assign_hdbscan_noise
    # A density-connected member at 9 remains in cluster 2 despite proximity
    # to cluster 7's centroid. Only -1 is eligible for extension.
    matrix = np.array([[0.0], [9.0], [10.0], [11.0], [10.5]])
    labels = assign_hdbscan_noise(matrix, np.array([2, 2, 7, 7, -1]))
    assert labels.tolist() == [0, 0, 1, 1, 1]


def test_unchanged_rebuild_preserves_reviewed_labels():
    from unittest.mock import MagicMock
    from gt.archetypes import _persist_model
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = (1,)
    _persist_model(conn,'existing-version',[1],np.array([0]),np.array([[0.5]]),
                   np.array([0.0]),0.4,[])
    statements = [call.args[0] for call in cur.execute.call_args_list]
    assert statements and all('SELECT' in statement for statement in statements)
    cur.executemany.assert_not_called()


def test_label_resolution_guards_even_an_explicit_pre_gvi_version():
    from unittest.mock import MagicMock
    import pytest
    from gt.archetypes import _resolve_model_version
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = None
    with pytest.raises(RuntimeError,match='post-GVI'):
        _resolve_model_version(conn,'pre-gvi-version')
    query,params = cur.execute.call_args.args
    assert "metric_keys ? 'gvi_ndvi_street'" in query
    assert 'silhouette >= %s' in query
    assert params == (0.25,'pre-gvi-version','pre-gvi-version')
