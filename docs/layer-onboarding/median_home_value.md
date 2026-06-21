# median_home_value source onboarding

## Source choice

Approved Phase 6 source: Zillow ZHVI single-family ZIP values reduced to school
districts with a housing-unit-weighted ZCTA crosswalk. ZCTAs without Zillow
values fall back to ACS B25077 median owner-occupied value.

Local files now available:

- `data/raw/Zip_zhvi_uc_sfr_tier_0.33_0.67_sm_sa_month.csv`
- `data/raw/census/tab20_zcta520_tabblock20_natl.txt`
- `data/raw/census/pl2020/pa2020.pl.zip`
- `data/raw/census/pl2020/ny2020.pl.zip`
- `data/raw/acs/2024/table-based-SF/acsdt5y2024-b25077.dat`

## Reduction

The layer does not use raw ZCTA land-area overlap. It streams the Census 2020
ZCTA-to-block relationship file, attaches each block to its PL 94-171 total
housing-unit count and Census school-district code, then sums housing units for
each `(ZCTA, school district)` pair. District value is the housing-unit-weighted
mean of available ZCTA values.

The PL 2020 geo file supplies block school-district codes; the segment 2 PL file
supplies H1 total housing units. Zillow ZHVI is preferred for each ZCTA, and ACS
B25077 ZCTA value is the fallback when Zillow has no row/value.

## Display grain

Output is staged directly on school-district regions. This is intentional:
median home values arrive at ZIP/ZCTA grain and are translated to districts,
not tracts. It is a Discovery affordability context metric, not an address-level
or tract-level fact.

## Current sample facts

- Zillow local latest observed column: `2026-05-31`.
- Census ZCTA-to-block relationship file is pipe-delimited and approximately
  1.0 GB.
- PA and NY PL 2020 ZIP files are local and contain state geo, segment 1,
  segment 2, and segment 3 files.

Validation reports record district coverage, ZCTA counts, Zillow versus ACS
fallback housing-unit shares, missing-value housing-unit share, and output range.
