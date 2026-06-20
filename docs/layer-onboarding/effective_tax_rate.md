# effective_tax_rate Source Onboarding

Status: implemented, staged, QA-rendered, and promoted.

## Source

- Publisher: U.S. Census Bureau
- Product: ACS 2024 5-year detailed tables
- Tables:
  - `B25103_001E`: median real estate taxes paid, total
  - `B25077_001E`: median owner-occupied home value
- Proposed metric: `effective_tax_rate = B25103_001E / B25077_001E`
- Units: share
- Native geography: county subdivision, then mapped to local census tracts
  with existing tract -> county-subdivision overlap weights.

The table metadata endpoints were reachable on 2026-06-20:

- `https://api.census.gov/data/2024/acs/acs5/groups/B25103.json`
- `https://api.census.gov/data/2024/acs/acs5/groups/B25077.json`

Verified labels:

- `B25103_001E`: `Estimate!!Median real estate taxes paid --!!Total:`
- `B25077_001E`: `Estimate!!Median value (dollars)`

The row-level Census API request returned `Missing Key` in this environment, so
the implementation uses official ACS table-based Summary File bulk downloads
instead:

- `https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-b25103.dat`
- `https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-b25077.dat`

Both files are pipe-delimited with `GEO_ID` and estimate fields. County
subdivision rows use `GEO_ID` values such as `0600000US3607107003`, where the
suffix after `US` matches local county-subdivision `regions.source_id`.

## Intended Reduction

1. Download/cache the two ACS table-based Summary File `.dat` files under
   `data/raw/acs/2024/table-based-SF/`.
2. Read `B25103_E001` and `B25077_E001` for local county-subdivision GEOIDs.
2. Drop rows where either estimate is negative, missing, or where median value
   is zero.
3. Compute source-unit rate as annual median real estate taxes divided by
   median owner-occupied home value.
4. Join source county subdivisions to local `mun-cousub-*` municipality
   regions by `source_id` and reduce to tract metrics through existing
   tract -> county-subdivision overlap weights. Places are intentionally not
   included in the reducer because the Phase 4 overlap graph includes both
   county subdivisions and places; using both would double-count many tracts.
5. Promote as tract-grain `region_metrics`; do not write `listing_metrics`
   from this source. Explorer may show the containing-tract value later as
   neighborhood tax context.

## Sample Stats

Staged report summaries on 2026-06-20:

- `pa-mainline`: 184/184 county subdivisions had both source values; 495/495
  tracts staged; range 0.00631-0.03437; mean 0.01551; p50 0.01436; p90
  0.02285; `promotable: true`.
- `hudson-valley`: 60/60 county subdivisions had both source values; 437/437
  tracts staged; range 0.00483-0.02962; mean 0.01746; p50 0.01726; p90
  0.02253; `promotable: true`.

Live district rollups after promote:

- `pa-mainline`: 61 district rollups, range 0.00631-0.02738, average 0.01535.
- `hudson-valley`: 78 district rollups, range 0.00550-0.02802, average
  0.01662.

Sanity anchors from `docs/tasks.md`:

- Lower Merion district rollup is 0.01228. This is below the rough 1.5-2.5%
  task anchor, but it reflects the ACS median-tax / ACS median-value formula
  and may differ from statutory millage or assessor-derived effective tax.
- Hudson Valley high-tax examples are in the expected range: Highland Falls
  0.02802, Carmel 0.02384, Wappingers 0.02358, Pawling 0.02345, and
  Washingtonville 0.02323.
