# walkability_index onboarding note

Status: drafted for human approval before full ingestion module. No data has
been staged or promoted.

## Candidate source

Selected source: EPA National Walkability Index.

- Smart Location Mapping page: https://www.epa.gov/smartgrowth/smart-location-mapping
- User guide and methodology page: https://www.epa.gov/smartgrowth/national-walkability-index-user-guide-and-methodology
- Data.gov metadata: https://catalog.data.gov/dataset/walkability-index
- Download ZIP: https://edg.epa.gov/EPADataCommons/public/OA/WalkabilityIndex.zip
- ArcGIS REST layer: https://geodata.epa.gov/arcgis/rest/services/OA/WalkabilityIndex/MapServer/0
- Source publisher: U.S. Environmental Protection Agency, Office of Sustainable
  Communities / Office of Community Revitalization.
- Citation vintage for this draft manifest: 2021 publication, using Census
  2019 block-group definitions and Smart Location Database inputs from the
  2021 release lineage.
- License note: Data.gov metadata lists the dataset license as CC0/public
  domain.

Reason for choosing this source: the architecture spec explicitly chooses EPA
National Walkability Index over the commercial Walk Score API. EPA documents
the index as a nationwide block-group data product that ranks every block group
by relative walkability and exposes both the final `NatWalkInd` score and the
ranked input variables.

## Candidate comparison

Selected: EPA National Walkability Index `NatWalkInd`.

- Pros: official federal source, free, national, block-group native, documented
  methodology, includes a ready-to-use score and underlying Smart Location
  Database attributes, and is available through both a downloadable ZIP and an
  ArcGIS REST service.
- Processing meaning: aggregate block-group `NatWalkInd` values to local
  census tracts with housing-unit weights, then rely on the existing
  tract-to-district rollup for Discovery.
- Grain honesty: block-group context. This supports Discovery tract/district
  rollups and can be attached to listings by containing block group, but the
  Explorer must label it as neighborhood context rather than an address-level
  measurement.

Rejected for this layer: Walk Score API.

- Reason: the API is commercial/restricted and returns proprietary address
  scores. It is useful as a consumer-facing benchmark but does not fit the
  free, auditable, reproducible data-backbone requirement for this POC.

Rejected as the primary metric: raw EPA Smart Location Database variables.

- Reason: the Smart Location Database is valuable and is the input source for
  NWI, but Phase 5 calls for a single `walkability_index` metric. Pulling raw
  density, diversity, design, and transit variables directly would create
  multiple new modeling choices before the approved composite exists.

Rejected for this layer: OSM-derived custom walkability score.

- Reason: OSM network and POI data can support later access layers, but a
  custom composite would require subjective weighting and ongoing QA. EPA NWI
  gives a documented national baseline first.

Rejected for this layer: EPA Smart Location Calculator score.

- Reason: the calculator is workplace-location oriented and its scores are
  relative to a region. The Discovery Engine needs a nationally comparable
  residential neighborhood walkability baseline.

## Source shape

Source metadata inspected from EPA pages, Data.gov, and the public ArcGIS REST
endpoint:

| Field | Value |
|---|---|
| Dataset | EPA National Walkability Index |
| Download | `WalkabilityIndex.zip` |
| Service layer | `OA/WalkabilityIndex/MapServer/0` |
| Layer name | `NationalWalkabilityIndex` |
| Geometry type | polygon |
| Service spatial reference | Web Mercator, EPSG:3857 / 102100 |
| Dataset geography | Census 2019 block groups |
| Local compute grain | census tract |
| Primary metric field | `NatWalkInd` |
| Housing-weight fields | `CountHU`, `HH`, and related household fields |
| Block-group keys | `GEOID10`, `GEOID20`, `STATEFP`, `COUNTYFP`, `TRACTCE`, `BLKGRPCE` |
| Ranked input fields | `D2A_Ranked`, `D2B_Ranked`, `D3B_Ranked`, `D4A_Ranked` |
| Allowed score range | 1-20 |
| Units | index score |

The ingestion module should not use EPA geometry as local region truth. It
should use source geometry only to assign source block groups to local tracts
when needed, then store numeric metric rows against the existing EPSG:4326
local `regions` and frozen `listings`.

## Sample stats plan

Sample stats were collected from the public ArcGIS REST service on
2026-06-18. The full ZIP was not downloaded because the source package is
405 MB and the service exposes the same layer with county filters. No source
data was staged or promoted.

Source-access checks:

1. ZIP reachability: `HEAD` returned `HTTP 200`; `content-length` is
   425,281,342 bytes; `last-modified` is Tue, 08 Jun 2021 19:11:31 GMT.
2. ZIP contents: not inspected in this sampling pass because the REST service
   was sufficient for county-filtered evidence. The implementation may still
   choose the ZIP if it is faster or more reproducible than the service.
3. Field names confirmed from the REST layer: `NatWalkInd`, `CountHU`, `HH`,
   `GEOID20`, `STATEFP`, `COUNTYFP`, `TRACTCE`, `BLKGRPCE`, `D2A_Ranked`,
   `D2B_Ranked`, `D3B_Ranked`, and `D4A_Ranked`.
4. Source service CRS is Web Mercator (`EPSG:3857` / `102100`). Sampling
   requested polygon output as `EPSG:4326`; overlap rehearsals used a projected
   working CRS (`EPSG:5070`) for area weights.
5. `NatWalkInd` values in both local county samples stayed within the manifest
   range of 1-20.

Measured county samples:

| Region sample | Counties | Expected pattern | Rows | Non-null score | Min | Mean | P50 | P90 | Max |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| PA Main Line | Chester, Delaware, Montgomery | Main Line boroughs and inner suburbs above exurban Chester County | 1,262 | 1,262 | 2.33 | 11.74 | 12.50 | 16.67 | 20.00 |
| Hudson Valley | Westchester, Rockland, Putnam, Orange | Yonkers/White Plains/Nyack higher than rural Putnam and outer Orange | 1,252 | 1,252 | 1.00 | 10.93 | 11.33 | 16.32 | 19.67 |

Direct tract-code weighting rehearsal:

| Region sample | Source block groups | Local tracts | Tracts with value | Min tract value | Mean tract value | Max tract value | Null tracts |
|---|---:|---:|---:|---:|---:|---:|---:|
| PA Main Line | 1,262 | 495 | 446 | 3.33 | 11.41 | 18.83 | 49 |
| Hudson Valley | 1,252 | 437 | 328 | 3.72 | 11.11 | 18.34 | 109 |

The direct `STATEFP` + `COUNTYFP` + `TRACTCE` join is not sufficient by
itself. It misses current local tracts because the NWI source uses older
block-group/tract vintages than the local tract scaffold. The implementation
should therefore include the proposed geometry-overlap fallback and report how
many local tracts required it.

Geometry-overlap weighting rehearsal:

| Region sample | Source block groups | Local tracts | Tracts with value | Min tract value | Mean tract value | Max tract value | Null tracts after overlap |
|---|---:|---:|---:|---:|---:|---:|---:|
| PA Main Line | 1,262 | 495 | 495 | 3.33 | 11.34 | 19.27 | 0 |
| Hudson Valley | 1,252 | 437 | 437 | 3.72 | 11.07 | 18.33 | 0 |

Measured listing-context rehearsal:

| Region sample | Listings | Listings matched to block group | Min listing context | Mean listing context | Max listing context |
|---|---:|---:|---:|---:|---:|
| PA Main Line | 251 | 251 | 4.33 | 11.08 | 18.67 |
| Hudson Valley | 4,254 | 4,245 | 2.67 | 9.82 | 19.33 |

The Hudson Valley listing match rate is 99.79%, above the 99% threshold. The
implementation should include the unmatched listing count and IDs in the
validation report so any waterfront or boundary-edge misses can be reviewed.

Approval question: approve EPA NWI as the Phase 5 `walkability_index` source
and proceed to the ingestion module, using geometry-overlap weighting for
tract coverage and point-in-polygon listing context labeled as neighborhood
context?

## Proposed reductions

- `region_metrics`: census-tract walkability score computed as a
  housing-unit-weighted mean of block-group `NatWalkInd` values.
- Weighting preference: use `CountHU` as the first-choice housing-unit weight;
  fall back to `HH` if `CountHU` is missing; fail validation rather than using
  unweighted means unless explicitly approved.
- Boundary-vintage handling: source `STATEFP` + `COUNTYFP` + `TRACTCE` joins
  are useful as a diagnostic, but the sampled source misses 49 PA Main Line
  tracts and 109 Hudson Valley tracts with direct codes alone. The ingestion
  module should distribute each block group's housing-unit weight to local
  tracts by area overlap, then flag tract coverage, source block-group counts,
  and any zero-overlap rows in the validation report.
- `district_metrics`: existing materialized-view rollup by tract/district
  overlap after promote.
- `listing_metrics`: containing block-group `NatWalkInd` via point-in-polygon,
  stored with `grain = 'point'` only if the UI labels it as block-group
  neighborhood context. Do not calculate 100 m or 500 m buffers from this
  source.
- Register `metric_definitions.direction = higher_better`.
- Validation threshold: at least 99% tract coverage and 99% listing
  point-in-polygon coverage if listing grain is implemented with the first
  module.

## Implementation notes

- Query or read only the manifest counties for the current regions; no need to
  persist a national copy after deriving local metric rows.
- Keep raw source artifacts under `data/raw/walkability_index/` if cached.
- Transform source geometries for processing as needed, but public region and
  listing geometries remain EPSG:4326.
- Include validation report fields for source row count, non-null score count,
  score range, number of boundary-vintage fallback overlaps, tract coverage,
  and listing match coverage.
- Preserve staging -> validate -> explicit promote.
- Do not call RentCast, do not infer districts, do not stage or promote
  `light_pollution_radiance`, and do not start GVI.
