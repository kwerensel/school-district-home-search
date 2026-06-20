# effective_tax_rate Source Onboarding

Status: blocked before ingestion by row-level Census API access.

## Source

- Publisher: U.S. Census Bureau
- Product: ACS 2024 5-year detailed tables
- Tables:
  - `B25103_001E`: median real estate taxes paid, total
  - `B25077_001E`: median owner-occupied home value
- Proposed metric: `effective_tax_rate = B25103_001E / B25077_001E`
- Units: share
- Native geography: county subdivision / place, then mapped to local census
  tracts with area or overlap weights.

The table metadata endpoints were reachable on 2026-06-20:

- `https://api.census.gov/data/2024/acs/acs5/groups/B25103.json`
- `https://api.census.gov/data/2024/acs/acs5/groups/B25077.json`

Verified labels:

- `B25103_001E`: `Estimate!!Median real estate taxes paid --!!Total:`
- `B25077_001E`: `Estimate!!Median value (dollars)`

## Intended Reduction

1. Fetch `B25103_001E`, `B25077_001E`, and `NAME` for county subdivisions
   in the project counties.
2. Drop rows where either estimate is negative, missing, or where median value
   is zero.
3. Compute source-unit rate as annual median real estate taxes divided by
   median owner-occupied home value.
4. Join source county subdivisions/places to local tract geometries and reduce
   to tract metrics through area/overlap weights.
5. Promote as tract-grain `region_metrics`; do not write `listing_metrics`
   from this source. Explorer may show the containing-tract value later as
   neighborhood tax context.

## Sample Stats

Sample stats are not complete. The row-data request against the official API,
for example:

```text
https://api.census.gov/data/2024/acs/acs5?get=NAME,B25103_001E,B25077_001E&for=county%20subdivision:*&in=state:42%20county:029
```

returned the Census API `Missing Key` HTML response in this environment on
2026-06-20. The table metadata endpoints do not require a key, but row-level
county-subdivision data appears to require a valid Census API key or an
alternate official bulk-file path.

## Blocker

Do not implement, stage, or promote this layer until one of these is available:

- a Census API key in the local environment, or
- an approved official ACS bulk-file workflow that can fetch the same variables
  for the target geographies without an API key.

Once access is resolved, collect sample stats for all project counties before
writing the ingestion module. Expected sanity anchors from `docs/tasks.md`:

- Lower Merion / nearby Main Line values should be roughly 1.5-2.5%.
- Typical Westchester values should be roughly 2-3%+.
