# Transportation-noise source onboarding

## Decision

Use the USDOT Bureau of Transportation Statistics (BTS) 2022/2023 National
Transportation Noise Map combined CONUS aviation, rail, and road layer for:

- `noise_mean_dba`
- `noise_pct_over_45`
- `noise_pct_over_55`

This source is already approved by `docs/architecture-spec.md` section 6 and
`docs/tasks.md` Phase 8. It is a U.S. government data product available for
unrestricted public use.

## Exact published source

- BTS landing/download page:
  https://www.bts.gov/geospatial/national-transportation-noise-map
- Data.gov record:
  https://catalog.data.gov/dataset/noise-data-2022
- Official tiled service:
  https://tiles.arcgis.com/tiles/xOi1kZaI0eWDREZv/arcgis/rest/services/NTAD_Noise_2022_CONUS_aviation_rail_road/MapServer
- Official tiled-service legend:
  https://tiles.arcgis.com/tiles/xOi1kZaI0eWDREZv/arcgis/rest/services/NTAD_Noise_2022_CONUS_aviation_rail_road/MapServer/legend

The combined vintage is labeled 2022/2023 because aviation and rail inputs are
from 2022 while the road input is from 2023. BTS released this dataset in May
2026 and updated its public catalog in June 2026.

## Verified service structure

The current BTS service is a public, single-band, zoom-12 PNG8 tile cache in
EPSG:3857. Zoom 12 is the highest published level and has a nominal ground
resolution of 38.2185 m per cell. Its legend publishes these classes:

| Tile class | Published label | Mean reducer value |
| --- | --- | --- |
| 0 / transparent | below 45.0 dBA modeling floor | 45.0 dBA floor |
| 1 | 45.0–49.9 | 47.45 |
| 2 | 50.0–54.9 | 52.45 |
| 3 | 55.0–59.9 | 57.45 |
| 4 | 60.0–69.9 | 64.95 |
| 5 | 70.0–79.9 | 74.95 |
| 6 | 80.0–89.9 | 84.95 |
| 7 | at least 90.0 | 92.5 |

The threshold metrics preserve these classes exactly. `noise_mean_dba` is an
explicit class-midpoint estimate: it does not pretend the public class tiles
contain continuous sound measurements. Pixels below the published modeling
floor use 45 dBA rather than an invented sub-floor midpoint.

The reducer caches only the tiles intersecting the two project regions under
`data/raw/bts/2022/`, records the exact service, tile range, class labels, and
resolution in request evidence, and keeps all rasters out of Postgres.

## Grain and reductions

- Census tract: estimated class-midpoint mean and exact source-cell threshold
  shares.
- Listing point: modeled class estimate or threshold flag at the grid cell.
- Listing `buffer_100m`: mean/share across intersecting source cells.

The nominal grid supports the Phase 8 listing reductions, but the UI must call
these values modeled transportation-noise context rather than address-level
measurements.

## Limitations and honesty language

BTS states that this is simplified national-level modeling for tracking trends
and that it should not be used to evaluate an individual location or a
specific time. The model covers aviation, road, and rail transportation noise,
does not include many intermittent or non-transportation sources, and does not
model shielding by terrain or barriers. Shielded locations can therefore be
overestimated. Values are 24-hour equivalent A-weighted levels (`LAeq`), not a
nighttime peak or a live reading.

The supplemental `noise_sources` layer remains separate. It will expose
distances and flags for sirens, nightlife, industrial land, and freight rail;
those signals must never be synthesized into decibels.

## Acceptance evidence required before promotion

- Manifest validation for all three metric keys.
- 99% or better tract coverage and 100% listing point/100 m-buffer coverage in
  both project regions.
- No non-finite values and all outputs inside their manifest ranges.
- Source evidence includes at least one non-transparent/45+ pixel in each
  region.
- One QA PNG per metric and region, visually showing higher modeled exposure
  along major transport corridors.
- Spatial golden tests pass after staging and again after explicit promotion.
