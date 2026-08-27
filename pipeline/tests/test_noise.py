import numpy as np

from gt.layers.noise import CLASS_COLORS, CLASS_MIDPOINT_DBA, _metric_values


def test_noise_class_colors_match_official_legend_order() -> None:
    assert CLASS_COLORS[1] == (255, 193, 7, 255)
    assert CLASS_COLORS[3] == (255, 0, 0, 255)
    assert CLASS_COLORS[7] == (0, 0, 255, 255)


def test_noise_mean_uses_published_class_midpoints_and_floor() -> None:
    categories = np.arange(8, dtype="uint8").reshape(2, 4)

    values = _metric_values(categories, "noise_mean_dba")

    np.testing.assert_allclose(values.ravel(), CLASS_MIDPOINT_DBA)
    assert values[0, 0] == 45.0


def test_noise_threshold_shares_preserve_bts_class_boundaries() -> None:
    categories = np.arange(8, dtype="uint8").reshape(2, 4)

    over_45 = _metric_values(categories, "noise_pct_over_45")
    over_55 = _metric_values(categories, "noise_pct_over_55")

    np.testing.assert_array_equal(over_45.ravel(), [0, 100, 100, 100, 100, 100, 100, 100])
    np.testing.assert_array_equal(over_55.ravel(), [0, 0, 0, 100, 100, 100, 100, 100])
