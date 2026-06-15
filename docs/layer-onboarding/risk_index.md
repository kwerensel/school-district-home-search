# risk_index onboarding note

Status: drafted for human approval before full ingestion module.

## Candidate source

Selected source: FEMA National Risk Index (NRI), served through FEMA's
Resilience Analysis and Planning Tool (RAPT) 2025 ArcGIS services.

- FEMA transition page: https://hazards.fema.gov/nri/transition
- RAPT application: https://experience.arcgis.com/experience/0a317e8998534c30a9b2d3861c814d42/
- RAPT web map item: `e68601a5d6814c03a4db8d93e2beaa1b`
- Selected service: https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/National_Risk_Index_Census_Tracts/FeatureServer/0
- Source publisher: FEMA, with RAPT/NRI content hosted under FEMA's ArcGIS organization.
- Citation vintage for this metric: 2025, matching the RAPT 2025 production app and service.

Reason for choosing this source: the architecture spec names FEMA NRI as the
Phase 5 `risk_index` source, and FEMA's old NRI data-resource page now states
that NRI data has moved into RAPT. The RAPT web map exposes a tract-level
`National_Risk_Index_Census_Tracts` feature service with the composite
`RISK_SCORE` field required for this metric.

## Candidate comparison

Selected: `National_Risk_Index_Census_Tracts/FeatureServer/0`.

- Pros: official FEMA/RAPT source, tract-native, directly includes composite
  `RISK_SCORE`, `RISK_RATNG`, expected annual loss, social vulnerability, and
  resilience companion fields.
- Processing meaning: direct attribute join to existing census-tract regions;
  no raster processing, interpolation, or polygon overlay needed.
- Grain honesty: tract-native. This supports Discovery rollups cleanly. Any
  later listing display should attach the listing's containing tract value as
  neighborhood/tract context, not as an address-level fact.

Rejected for this metric: county-level NRI services.

- Reason: useful for broad context, but coarser than the repo's census-tract
  compute grain and would blur district rollups.

Rejected for this metric: hazard-specific NRI layers such as wildfire,
earthquake, hurricane, and inland flooding risk ratings.

- Reason: those are useful future explanatory slices, but Phase 5 calls for the
  composite `risk_index`. Hazard-specific fields can be considered later after
  the composite metric is live.

## Source shape

Service metadata inspected from the public ArcGIS REST endpoint:

| Field | Value |
|---|---|
| Service layer | `National_Risk_Index_Census_Tracts/FeatureServer/0` |
| Layer name | `NRI_CensusTracts_Prod` |
| Geometry type | polygon |
| Service spatial reference | Web Mercator, EPSG:3857 / 102100 |
| Local join grain | census tract |
| Join key | source `TRACTFIPS` to local tract `regions.source_id` |
| Main metric field | `RISK_SCORE` |
| Rating field | `RISK_RATNG` |
| Companion fields | `RISK_SPCTL`, `EAL_SCORE`, `EAL_SPCTL`, `SOVI_SCORE`, `RESL_SCORE` |
| Allowed range | 0-100 |

The ingestion module should not store or promote service geometry. It should
fetch attributes for the manifest counties, join to local tract regions, and
keep all stored geometries in EPSG:4326.

## Sample value checks

ArcGIS REST queries sampled the exact counties in the current region manifests:

| Region sample | Counties | Rows | Non-null risk | Min | Mean | P50 | Max | Ratings seen |
|---|---|---:|---:|---:|---:|---:|---:|---|
| PA Main Line | Chester, Delaware, Montgomery | 495 | 495 | 0.169 | 33.953 | 32.790 | 94.300 | Very Low, Relatively Low, Relatively Moderate, Relatively High |
| Hudson Valley | Westchester, Rockland, Putnam, Orange | 437 | 437 | 0.021 | 24.394 | 19.398 | 99.039 | Very Low, Relatively Low, Relatively Moderate, Relatively High, Very High |

Companion-field spot checks also stayed inside expected 0-100-like score
ranges:

| Region sample | EAL score min/mean/max | SOVI score min/mean/max | RESL score min/mean/max |
|---|---|---|---|
| PA Main Line | 0.206 / 39.829 / 95.189 | 0.393 / 37.045 / 98.885 | 76.542 / 82.051 / 88.441 |
| Hudson Valley | 0.022 / 26.022 / 99.240 | 0.393 / 46.901 / 99.989 | 51.014 / 63.819 / 84.825 |

Rows exactly match the currently scaffolded tract counts for both regions
(495 PA Main Line, 437 Hudson Valley), which makes this a good low-risk next
Phase 5 layer.

## Proposed reductions

- `region_metrics`: direct join from NRI tract `RISK_SCORE` to local
  census-tract regions.
- `district_metrics`: existing materialized-view rollup by tract/district
  overlap after promote.
- `listing_metrics`: none in the initial layer manifest. If the Explorer later
  needs this metric, attach each listing's containing tract value as a
  neighborhood-context metric and label it accordingly.
- Register `metric_definitions.direction = lower_better`.
- Keep `RISK_RATNG` out of `region_metrics` for now because the metrics table
  stores numeric values. The runner can use it for validation summaries or a
  later explanatory lookup table.
- Validation threshold: at least 99% tract coverage; expected current coverage
  is 932/932 tracts across both regions based on the sample queries.

## Implementation notes

- Query the ArcGIS service by `STCOFIPS` for the manifest counties and request
  only needed fields; no need to download national geometry.
- Assert every local tract has exactly one matching NRI `TRACTFIPS` row.
- Values must be within `[0, 100]` and non-null.
- Preserve staging -> validate -> explicit promote.
- Do not call RentCast, do not infer districts, and do not start GVI.
