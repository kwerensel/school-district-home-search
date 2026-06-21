from gt.layers.median_home_value import (
    SourceValue,
    _block_part_allocation,
    _compute_district_metrics,
    _normalize_zcta,
)


def test_block_part_allocation_uses_land_share() -> None:
    assert (
        _block_part_allocation(
            {
                "AREALAND_TABBLOCK_20": "1000",
                "AREALAND_PART": "250",
                "AREAWATER_TABBLOCK_20": "5000",
                "AREAWATER_PART": "5000",
            }
        )
        == 0.25
    )


def test_block_part_allocation_falls_back_to_total_area() -> None:
    assert (
        _block_part_allocation(
            {
                "AREALAND_TABBLOCK_20": "0",
                "AREALAND_PART": "0",
                "AREAWATER_TABBLOCK_20": "400",
                "AREAWATER_PART": "100",
            }
        )
        == 0.25
    )


def test_compute_district_metrics_prefers_zillow_then_acs_fallback() -> None:
    metrics = _compute_district_metrics(
        {
            ("01234", "district-a"): 10,
            ("56789", "district-a"): 30,
            ("00001", "district-b"): 5,
            ("99999", "district-b"): 5,
        },
        {
            "01234": SourceValue(value=100_000, source="zillow_zhvi"),
            "00001": SourceValue(value=900_000, source="zillow_zhvi"),
        },
        {
            "56789": SourceValue(value=300_000, source="acs_b25077"),
            "00001": SourceValue(value=1, source="acs_b25077"),
        },
    )

    by_slug = {metric.region_slug: metric.value for metric in metrics}
    assert by_slug == {
        "district-a": 250_000,
        "district-b": 900_000,
    }


def test_normalize_zcta_requires_digits_and_zero_pads() -> None:
    assert _normalize_zcta("123") == "00123"
    assert _normalize_zcta(" 90210 ") == "90210"
    assert _normalize_zcta("ZIP 90210") == ""
