# flood_sfha onboarding note

Status: drafted for human approval before full ingestion module. No data has
been staged or promoted.

## Candidate source

Selected source: FEMA National Flood Hazard Layer (NFHL), Flood Hazard Zones.

- FEMA NFHL overview: https://www.fema.gov/flood-maps/national-flood-hazard-layer
- NFHL REST service: https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer
- Flood Hazard Zones layer: https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28
- Source publisher: Federal Emergency Management Agency (FEMA), National Flood
  Insurance Program.
- Citation vintage for this draft manifest: `live-nfhl`, because the public
  map service represents FEMA's current NFHL service rather than a fixed annual
  release file. The implementation should record retrieval date in validation
  reports.
- License note: FEMA flood map products are federal public data; derived metric
  rows should preserve FEMA provenance and retrieval date.

Reason for choosing this source: the architecture spec explicitly calls for
FEMA NFHL for `flood_sfha`. It is the authoritative national source for FEMA
Flood Insurance Rate Map hazard polygons, and it carries an explicit `SFHA_TF`
field for Special Flood Hazard Area membership.

## Candidate comparison

Selected: FEMA NFHL `Flood Hazard Zones` polygons.

- Pros: official federal source, national, parcel-scale regulatory polygons,
  exposes both flood zone class (`FLD_ZONE`) and Special Flood Hazard Area flag
  (`SFHA_TF`), and supports exact point-in-polygon listing flags.
- Processing meaning: filter source polygons to `SFHA_TF = 'T'`, reduce to
  census tracts by area share, then rely on the existing tract-to-district
  rollup for Discovery.
- Grain honesty: exact polygon context. This supports Discovery tract/district
  rollups and listing point-in-polygon flags. It should not be interpolated,
  buffered, or presented as probabilistic flood depth.

Rejected for this layer: First Street / Flood Factor.

- Reason: paid/proprietary and not part of the approved free, auditable POC
  data backbone. It may be a future premium comparison source, but not the
  deterministic Phase 5 layer.

Rejected for this layer: FEMA National Risk Index flooding scores.

- Reason: NRI is already onboarded as `risk_index` and is tract-level relative
  risk. `flood_sfha` needs exact regulatory flood-hazard polygons for listing
  flags and tract area shares.

Rejected for this layer: local county floodplain datasets.

- Reason: local layers can be useful QA cross-checks, but NFHL is the national
  canonical source and covers both current project regions with one schema.

## Source shape

Source metadata inspected from FEMA's public ArcGIS REST service on
2026-06-18:

| Field | Value |
|---|---|
| Service | `public/NFHL/MapServer` |
| Layer id | `28` |
| Layer name | `Flood Hazard Zones` |
| Geometry type | polygon |
| Service spatial reference | NAD83, EPSG:4269 |
| Primary filter | `SFHA_TF = 'T'` |
| Flood-zone field | `FLD_ZONE` |
| Other useful fields | `ZONE_SUBTY`, `STATIC_BFE`, `DEPTH`, `SOURCE_CIT` |
| Max record count | 2,000 |
| Allowed metric range | 0-1 |
| Units | share / binary flag |

The ingestion module should not use FEMA geometry as local region truth. It
should use source geometry only to compute metric rows against the existing
EPSG:4326 local `regions` and frozen `listings`.

## Sample stats

Sample stats were collected from the public NFHL ArcGIS REST service on
2026-06-18. No source data was staged or promoted.

Source-access checks:

1. Current REST service endpoint responded at
   `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer`.
   The older `/gis/nfhl/rest/...` path returned `HTTP 404` from this
   environment.
2. Layer metadata confirmed `Flood Hazard Zones` as layer `28`, polygon
   geometry, EPSG:4269, max record count 2,000, and fields `FLD_ZONE` and
   `SFHA_TF`.
3. National service counts returned 5,564,845 flood hazard zone records and
   1,364,420 `SFHA_TF = 'T'` records.
4. Region-bounded count queries require an explicit `inSR=4326` parameter.
   Without it, the service returned a generic `Error performing query
   operation`.
5. Geometry-heavy live REST pulls were brittle in this environment. Envelope
   queries with geometry returned service errors; object-ID chunk fetches worked
   for small chunks but repeated long runs hit connection resets. The full
   implementation should therefore use resumable object-ID chunk caching or a
   downloaded NFHL file geodatabase/state extract under `data/raw/flood_sfha/`,
   not a one-shot REST geometry query.

Measured bounded service counts:

| Region sample | Query geometry | SFHA features | Zone A | Zone AE | Zone AO | Zone AH | Zone VE |
|---|---|---:|---:|---:|---:|---:|---:|
| PA Main Line | local census-tract total bounds | 8,534 | 944 | 7,509 | 7 | 0 | 74 |
| Hudson Valley | local census-tract total bounds | 15,974 | 816 | 14,914 | 19 | 15 | 210 |

Expected patterns:

- PA Main Line should show SFHA ribbons along the Schuylkill River, Darby
  Creek, Ridley Creek, Brandywine Creek, and smaller tributaries.
- Hudson Valley should show SFHA concentration along the Hudson River, coastal
  Westchester / Long Island Sound edges, the Wallkill, Moodna, and other Orange
  County river corridors.
- Listing point flags should be sparse. Any positive listing flag should be
  treated as exact FEMA polygon context, but still not as insurance advice.

Approval question: approve FEMA NFHL `Flood Hazard Zones` layer 28 as the Phase
5 `flood_sfha` source, using `SFHA_TF = 'T'`, tract area-share reduction, and
listing point-in-polygon flags?

## Proposed reductions

- `region_metrics`: census-tract share of area inside SFHA polygons, computed
  as `area(intersection(tract, union/source polygons where SFHA_TF='T')) /
  tract_area`.
- `district_metrics`: existing materialized-view rollup by tract/district
  overlap after promote. This metric is threshold/share-like and should remain
  area-weighted.
- `listing_metrics`: exact point-in-polygon flag, stored with `grain = 'point'`
  and value `1` if the listing point is inside an SFHA polygon, else `0`.
- Register `metric_definitions.direction = lower_better`.
- Validation threshold: 100% tract rows and 100% listing rows, because zero is
  a meaningful value for this layer. Validate value range 0-1.

## Implementation notes

- Prefer a resumable source cache:
  - first request bounded `objectIds` for `SFHA_TF='T'`;
  - fetch small geometry chunks with retry/backoff; or
  - use official NFHL file geodatabase/state extract if it proves more stable.
- Keep raw source artifacts under `data/raw/flood_sfha/`.
- Transform FEMA EPSG:4269/4326 geometries into EPSG:4326 before staging and
  use EPSG:5070 or local equal-area projection for area-share calculations.
- Include validation report fields for source object-id count, fetched feature
  count, flood-zone counts, tract coverage, listing coverage, value range, and
  any source geometry fetch retries/failures.
- Preserve staging -> validate -> explicit promote.
- Do not call RentCast, do not infer districts, do not stage or promote
  `light_pollution_radiance`, and do not start GVI.
