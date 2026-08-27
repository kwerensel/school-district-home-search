# Codex Handoff

Generated: 2026-08-26, America/New_York.

## 1. Project Goal

Groundtruth is a geospatial home-search platform with two linked products on one deterministic data backbone:

- Listing Explorer (`/explore`): shows frozen PA and Hudson Valley listings with school-district assignment verified by PostGIS point-in-polygon joins against official NCES polygons.
- Discovery Engine (`/discover`): will help users decide where to search from budget and lifestyle constraints using regional metrics such as canopy, light pollution, risk, walkability, taxes, and home values.

Hard constraints from `AGENTS.md` remain active: no LLM/ZIP/deductive district assignment, no new RentCast calls or listing expansion, no GreatSchools data, financial math in code/tests only, EPSG:4326 stored geometry, and staging -> validate -> explicit promote for pipeline loads.

## 2. Current Phase Or Feature Area

Phases 0–7 are complete. The approved Phase 8 AQI, BTS transportation-noise,
and supplemental `noise_sources` slices are implemented, promoted, verified,
and wired into Discovery/Explorer. Satellite GVI remains explicitly deferred
and Mapillary GVI remains Phase 11. The next phase-ordered local build arc is
Phase 9 archetypes and guarded narratives; its dependency-free foundation is
implemented, but live model persistence is correctly blocked by the approved
HDBSCAN fallback gate described below. The unblocked Phase 10 URL-profile slice
is already complete.

Completed checkpoints:

- Phase 0-3 were already complete on `main` at commit `360bc45 Phase 3 live Neon Explorer API`.
- Phase 4 and promoted `canopy_height_m` were committed on `main` at commit `a59ed76 Phase 4 harness and canopy height layer`.
- `tree_canopy_pct` source onboarding was committed on `main` at commit `125a85d Draft tree canopy layer onboarding`.
- `tree_canopy_pct` implementation, staging run, validation, and QA map generation were committed and pushed on `main` at commit `133a59b Implement tree canopy layer staging`.
- `tree_canopy_pct` was promoted to Neon for both `pa-mainline` and `hudson-valley` after explicit human approval in the follow-up session.
- `risk_index` source onboarding was approved, implemented, staged for both regions, validated as promotable, QA maps were rendered, and it was promoted to Neon after explicit human approval.
- `light_pollution_radiance` source onboarding now uses the authenticated local
  EOG 2025 V2.2 median-masked raster, with exact filename and numeric sample
  stats verified; it has been implemented, staged, QA-rendered, promoted, and
  verified in Neon.
- `walkability_index` source onboarding was approved, implemented, staged for
  both regions, validated as promotable, QA maps were rendered, and it was
  promoted to Neon after explicit human approval.
- `flood_sfha` source onboarding was approved, implemented, staged for both
  regions, validated as promotable, QA maps were rendered, repaired for
  non-finite zero-overlap tract shares, and promoted to Neon.
- Explorer listing metrics panel work was implemented and pushed at
  `e44c204 Add Explorer listing metrics panel`: listing GeoJSON now carries
  compact canopy/flood filter fields, `getListingMetrics` returns promoted
  listing and tract context metrics, map clicks open a React detail panel, and
  the filter sidebar includes minimum canopy and FEMA SFHA flag filters.
- Follow-up lint/format repair was pushed at
  `6a99c54 Fix Explorer panel lint issues`.
- Phase 6 `effective_tax_rate` source onboarding was drafted and pushed at
  `617f0ab Draft effective tax rate onboarding`, then implemented with the
  official ACS table-based Summary File bulk workflow and promoted to Neon.
- Phase 6 pure finance engine was implemented and pushed at
  `816b127 Add purchasing power finance engine`: closed-form purchasing power,
  credit-band spreads, PMI, insurance, optional DTI ceiling, and unit tests.
- Phase 6 `effective_tax_rate` implementation and promotion was pushed at
  `7c0bfab Implement effective tax layer`.
- Phase 6 purchasing-power server data path is implemented in the current
  checkpoint: `getDistrictPurchasingPower` validates user budget inputs,
  reads promoted district `effective_tax_rate` rows, and maps them through the
  pure TypeScript finance engine without logging profile contents.
- First Phase 6 Discovery surface was implemented as an earlier checkpoint:
  `/discover` provides budget controls, district purchasing-power ranking, and
  a Leaflet district choropleth driven by the new server function. Promoted
  median home values were integrated in a later checkpoint below.
- Discovery/Explorer URL profile handoff is implemented in the current
  checkpoint: Discovery persists monthly budget, down payment, credit band, and
  region in search params, then links to Explorer with selected district and
  max-price ceiling; Explorer initializes filters from those URL params.
- Chrome QA follow-up is implemented in the current checkpoint: Discovery URL
  params now hydrate after mount to avoid SSR/client mismatch, and the
  choropleth uses Leaflet SVG rendering instead of canvas to avoid a runtime
  renderer error seen during local Chrome loading.
- Discovery feedback pass is implemented in the current checkpoint: map colors
  are explicitly labeled as district buying ceiling, down payment is now a
  dollar amount instead of a percentage, numeric fields can be edited without
  fighting controlled-input fallback behavior, and the generic Explorer header
  link is separate from the selected-district "Search listings" handoff.
- Explorer UX follow-up is implemented in the current checkpoint: filtering no
  longer refits/rezooms the map after initial load, and listing detail panels
  show compact filter values such as 100 m canopy height and FEMA SFHA point
  flag when those values explain why a listing remains in filtered results.
- Explorer listing detail follow-up is implemented in the current checkpoint:
  known compact listing values now always display alongside promoted metric
  groups, so users can see all currently known values for the selected listing.
- Discovery profile scoring follow-up is implemented in the current checkpoint:
  promoted environmental district metrics now feed deterministic match scoring
  alongside purchasing power, with URL-backed priority sliders for budget fit,
  green, walkability, lower risk, lower flood, and darker skies.
- Discovery selected-district polish is implemented in the current checkpoint:
  "buying ceiling" copy is clarified as max home price where appropriate, the
  selected district panel now appears earlier in the sidebar with all known
  promoted district values, and the map has a selected-district summary card,
  hover tooltips, and clearer legend labels.
- Explorer map legend polish is implemented in the current checkpoint: the map
  now explains listing/district colors, and Explorer uses Leaflet SVG rendering
  instead of the canvas renderer that produced a local Chrome `clearRect`
  runtime error.
- Phase 6 `median_home_value` is implemented, staged, QA-rendered, promoted,
  and verified in Neon using the approved Zillow ZHVI plus Census/ACS
  housing-unit-weighted ZCTA-to-school-district crosswalk.
- Phase 6 median-value Discovery integration is implemented in the current
  checkpoint: `getDistrictPurchasingPower` now fetches `median_home_value`,
  computes budget fit as max purchase price divided by district median value
  when available, and Discovery displays median value plus fit ratio in ranked
  cards, selected district panel, and map tooltips.
- Phase 7 `park_access` source onboarding is drafted in the current checkpoint
  using approved OpenStreetMap plus USGS PAD-US Public Access sources.
- Phase 7 `park_access` is implemented and promoted for both regions. The
  mixed-units design was resolved with tract `park_access` shares and listing
  `park_distance_m` meters as separate metric definitions. Discovery now uses
  park access in deterministic scoring and district maps, and Explorer listing
  details show straight-line park distance with an honesty explainer.
- Phase 6 mortgage-rate acceptance is closed: the purchasing-power server now
  fetches the official Freddie Mac PMMS 30-year series through FRED, caches a
  successful observation for 24 hours, and uses the documented constant only
  when the source is unavailable. The UI identifies live, supplied, and
  fallback rate assumptions.
- Release readiness now includes canonical `/explore` and
  `/discover/results` routes, Groundtruth metadata/branding, explicit query
  failure/retry states, redacted error logging, server-function CSRF
  protection, a forced Cloudflare Nitro production bundle, deploy instructions,
  CI, and Dependabot configuration.
- Phase 7 Transitland and ORS credentials are configured. The previously
  scaffolded `transit_access`, `transit_distance_m`, and fixed-anchor commute
  metrics are implemented, staged, QA-rendered, explicitly promoted, and
  exposed in the app with resolution-honest explanations.
- Discovery now has a typed canonical profile parser/serializer for budget,
  down payment, credit band, region, and all seven scoring weights. Invalid or
  absent URL values fall back per field, customized profiles round-trip, and
  Explorer filter changes remain shareable without dropping the originating
  Discovery profile or selected-district context.
- August 2026 UX feedback is implemented in the current worktree: consumer UI
  no longer exposes the normalized overall match percentage or percent-of-
  median as "fit"; it shows `#x of N districts`, the named comparison area,
  factor strengths/tradeoffs, purchasing-power assumptions, plain-language
  canopy/flood/light-pollution explanations, selectable district choropleths,
  a category-based Explorer tree-cover filter, and a Discovery -> Explorer
  district-focus handoff. Before/after screenshots are under
  `docs/screenshots/`.
- Phase 8 BTS transportation noise is implemented for both regions at tract,
  listing-point, and listing-100 m grains. `noise_mean_dba`,
  `noise_pct_over_45`, and `noise_pct_over_55` were staged, validated as
  promotable, QA-rendered, explicitly promoted, and live-verified. Discovery
  exposes the ≥55 dBA district share and modeled mean with honest limitations;
  Explorer exposes all three listing metrics with source/resolution context.
- Phase 8 supplemental noise-source context is implemented for both regions.
  OSM emergency-response facilities, nightlife venues, and industrial land
  plus FRA active freight-capable rail are served as labeled density,
  distance, count, and proximity signals only—never synthesized into dB or
  treated as measured noise. All 16 region/metric reports were promotable,
  visually QA-reviewed, explicitly promoted, and live-verified. A pinned
  listing regression test confirms the expected near-rail condition.

Standing approval model: source and application choices already documented in
the approved architecture/tasks/handoff count as approved. Do not stop for
routine yes/no source or promotion approval when validation is green; preserve
staging -> validate -> explicit promote and keep moving. Stop only for genuinely
missing information, surprising/red validation, a source-of-truth conflict, or a
new unapproved source/provider/paid integration. GVI must not start.

Do not start GVI yet. Complete `noise_sources` first; `gvi_ndvi_street` remains
deferred within Phase 8 and Mapillary/segmentation GVI is Phase 11.

## 3. Completed So Far

### Phase 4 Harness

- Added pydantic manifest models for region/layer manifests.
- Added seed region manifests:
  - `pipeline/manifests/regions/hudson-valley.yaml`
  - `pipeline/manifests/regions/pa-mainline.yaml`
- Implemented `gt region add` using official TIGER 2023 tracts/county subdivisions/places and NCES EDGE SY2223 school districts.
- Added staging-first region scaffold tables and promote path.
- Added validation reports under `data/reports/` and QA maps under `data/reports/qa/`.
- Changed `district_metrics` to a materialized view with promote refresh.
- Replayed Phase 4 against Neon using the existing `app/.env.local` `DATABASE_URL`.

Neon Phase 4 live validation:

- `hudson-valley`: 437 census tracts, 207 municipalities, 78 school-district regions, 1,874 overlap rows.
- `pa-mainline`: 495 census tracts, 347 municipalities, 62 school-district regions, 1,997 overlap rows.
- Tract -> district overlap weight min/max is approximately 1.0 for both region groups.

QA maps generated locally:

- `data/reports/qa/hudson-valley_tracts_districts.png`
- `data/reports/qa/pa-mainline_tracts_districts.png`

### Phase 5 `canopy_height_m`

- Drafted and approved source onboarding for WRI/Meta CHMv2 2026 canopy height.
- Added layer manifest:
  - `pipeline/manifests/layers/canopy_height_m.yaml`
- Added onboarding note:
  - `docs/layer-onboarding/canopy_height_m.md`
- Implemented `gt layer run canopy_height_m --region <slug> --grain tract|listing|both`.
- Implemented generic layer staging, QA map rendering, and promote support for the layer report type.
- Ran `canopy_height_m` for both regions at tract + listing grains.
- Promoted `canopy_height_m` into Neon `metric_definitions`, `region_metrics`, `listing_metrics`, and refreshed `district_metrics`.

Neon live `canopy_height_m` counts after promote:

- `region_metrics`: 932 tract rows.
- `listing_metrics`: 9,010 rows total:
  - 4,505 `point`
  - 4,505 `buffer_100m`
- `district_metrics`: 139 district rollups.

QA maps generated locally:

- `data/reports/qa/canopy_height_m_hudson-valley.png`
- `data/reports/qa/canopy_height_m_pa-mainline.png`
- `data/reports/qa/listing_canopy_variation_pa-mainline.png`
- `data/reports/qa/listing_canopy_variation_pa-mainline.json`

Listing-level canopy QA selected a close Wayne, PA pair from promoted Neon
`listing_metrics`: `1052 Eagle Rd, Wayne` and `Walnut Ave, Lot 2, Wayne` are
172 m apart and differ by 18.1 m in `buffer_100m` canopy height
(19.9 m vs. 1.8 m). This satisfies the Phase 5 house-to-house variation
acceptance detail for `canopy_height_m`.

### Phase 5 `tree_canopy_pct`

- Drafted and approved source onboarding for USDA Forest Service / MRLC NLCD Tree Canopy Cover Product Suite v2025.6.
- Added layer manifest:
  - `pipeline/manifests/layers/tree_canopy_pct.yaml`
- Added onboarding note:
  - `docs/layer-onboarding/tree_canopy_pct.md`
- Implemented layer runner:
  - `pipeline/gt/layers/tree_canopy.py`
- Wired the CLI so `gt layer run tree_canopy_pct --region <slug> --grain both` works.
- Staged `tree_canopy_pct` for both regions at:
  - `region_metrics`: census-tract zonal mean percent canopy.
  - `listing_metrics`: `buffer_100m` and `buffer_500m` means.
- Deliberately did not compute listing point samples, because the native 30 m product is block/context resolution rather than address-pixel truth.
- Rendered QA maps from staging.
- Promoted `tree_canopy_pct` into Neon `metric_definitions`, `region_metrics`, `listing_metrics`, and refreshed `district_metrics` after explicit human approval.

Staged validation:

- `pa-mainline`: 495/495 tracts; 251/251 listings at `buffer_100m`; 251/251 listings at `buffer_500m`; value range 0.0-81.03; `promotable: true`.
- `hudson-valley`: 437/437 tracts; 4,254/4,254 listings at `buffer_100m`; 4,254/4,254 listings at `buffer_500m`; value range 0.0-89.06; `promotable: true`.

Generated reports:

- `data/reports/layer_tree_canopy_pct_pa-mainline_latest.json`
- `data/reports/layer_tree_canopy_pct_hudson-valley_latest.json`

Generated QA maps:

- `data/reports/qa/tree_canopy_pct_pa-mainline.png`
- `data/reports/qa/tree_canopy_pct_hudson-valley.png`

Latest Neon-backed pipeline test run after staging:

```text
19 passed in 3.77s
```

Neon live `tree_canopy_pct` counts after promote:

- `region_metrics`: 932 tract rows:
  - `hudson-valley`: 437 census-tract rows, range 0.59-76.03.
  - `pa-mainline`: 495 census-tract rows, range 2.14-64.04.
- `listing_metrics`: 9,010 rows total:
  - `hudson-valley`: 4,254 `buffer_100m` and 4,254 `buffer_500m`.
  - `pa-mainline`: 251 `buffer_100m` and 251 `buffer_500m`.
- `district_metrics`: 139 district rollups:
  - `hudson-valley`: 78 rollups, range 11.28-74.53.
  - `pa-mainline`: 61 rollups, range 14.24-56.38.

### Phase 5 `risk_index`

- Drafted and approved source onboarding for FEMA National Risk Index via RAPT 2025.
- Added layer manifest:
  - `pipeline/manifests/layers/risk_index.yaml`
- Added onboarding note:
  - `docs/layer-onboarding/risk_index.md`
- Implemented layer runner:
  - `pipeline/gt/layers/risk_index.py`
- Wired the CLI so `gt layer run risk_index --region <slug> --grain tract` works.
- Staged `risk_index` for both regions at tract grain only:
  - `region_metrics`: direct census-tract join from NRI `RISK_SCORE`.
  - `listing_metrics`: none. NRI is tract-native and should only be attached to listings later as neighborhood/tract context.
- Rendered QA maps from staging.
- Promoted `risk_index` into Neon `metric_definitions` and `region_metrics`, and refreshed `district_metrics` after explicit human approval.

Staged validation:

- `pa-mainline`: 495/495 tracts; value range 0.1689-94.3004; `promotable: true`.
- `hudson-valley`: 437/437 tracts; value range 0.0214-99.0392; `promotable: true`.

Generated reports:

- `data/reports/layer_risk_index_pa-mainline_latest.json`
- `data/reports/layer_risk_index_hudson-valley_latest.json`

Generated QA maps:

- `data/reports/qa/risk_index_pa-mainline.png`
- `data/reports/qa/risk_index_hudson-valley.png`

Latest Neon-backed pipeline test run after staging:

```text
21 passed in 7.19s
```

Neon live `risk_index` counts after promote:

- `region_metrics`: 932 tract rows:
  - `hudson-valley`: 437 census-tract rows, range 0.0214-99.0392.
  - `pa-mainline`: 495 census-tract rows, range 0.1689-94.3004.
- `listing_metrics`: 0 rows by design. NRI is tract-native and should be shown at listing level only as tract/neighborhood context later.
- `district_metrics`: 139 district rollups:
  - `hudson-valley`: 78 rollups, range 14.33-71.57.
  - `pa-mainline`: 61 rollups, range 9.93-93.55.

### Phase 5 `light_pollution_radiance`

- Drafted source onboarding for EOG VIIRS Annual VNL V2.2 median-masked radiance.
- Added layer manifest:
  - `pipeline/manifests/layers/light_pollution_radiance.yaml`
- Added onboarding note:
  - `docs/layer-onboarding/light_pollution_radiance.md`
- Source access is resolved via the authenticated local 2025 EOG V2.2
  median-masked GeoTIFF under `data/raw/eog/`.
- Added the ingestion module:
  - `pipeline/gt/layers/light_pollution.py`
- Wired `light_pollution_radiance` into the layer runner dispatch and package
  export.
- Initial staging hit sandbox DNS resolution for the Neon host; rerunning with
  approved network access worked.
- Added a representative-point fallback for tiny tracts that receive no raster
  cells in the zonal pass, preserving the native ~500 m source resolution while
  meeting tract coverage.
- Staged both regions at tract grain and wrote promotable reports:
  - `data/reports/layer_light_pollution_radiance_pa-mainline_latest.json`
  - `data/reports/layer_light_pollution_radiance_hudson-valley_latest.json`
- Rendered QA maps:
  - `data/reports/qa/light_pollution_radiance_pa-mainline.png`
  - `data/reports/qa/light_pollution_radiance_hudson-valley.png`
- Promoted both reports to Neon and refreshed `district_metrics`.

Staged validation:

- `pa-mainline`: 495/495 tracts; range 0.680-77.168; source window p50 3.73,
  p90 28.105; `promotable: true`.
- `hudson-valley`: 437/437 tracts; range 0.259-100.720; source window p50
  1.82, p90 14.775; `promotable: true`.

Neon live `light_pollution_radiance` counts after promote:

- `region_metrics`: 932 tract rows:
  - `hudson-valley`: 437 census-tract rows, range 0.259-100.720.
  - `pa-mainline`: 495 census-tract rows, range 0.680-77.168.
- `listing_metrics`: 0 rows by design. VIIRS is neighborhood context only.
- `district_metrics`: 139 district rollups:
  - `hudson-valley`: 78 rollups, range 0.259-41.366.
  - `pa-mainline`: 61 rollups, range 1.384-39.908.

### Phase 5 `walkability_index`

- Drafted source onboarding for EPA National Walkability Index while EOG access
  is pending.
- Added layer manifest:
  - `pipeline/manifests/layers/walkability_index.yaml`
- Added onboarding note:
  - `docs/layer-onboarding/walkability_index.md`
- Added a manifest validation test in:
  - `pipeline/tests/test_cli.py`
- Proposed approach: use EPA block-group `NatWalkInd`, aggregate to census
  tracts by housing-unit-weighted area-overlap mean, roll up to districts
  through the existing `district_metrics` view after future promotion, and
  attach listing values only as containing-block-group neighborhood context.
- Sample stats were collected from the EPA ArcGIS REST layer on 2026-06-18.
  The 405 MB ZIP was verified reachable by `HEAD` but not downloaded.
- Direct tract-code joins missed 49 PA Main Line tracts and 109 Hudson Valley
  tracts because the NWI source vintage does not line up perfectly with the
  current local tract scaffold. Area-overlap weighting filled all local tracts:
  495/495 PA Main Line and 437/437 Hudson Valley.
- Listing point-in-polygon rehearsal matched 251/251 PA Main Line listings and
  4,245/4,254 Hudson Valley listings, clearing the 99% threshold. The future
  implementation should report unmatched listing IDs for review.
- Human approval was given on 2026-06-18 to implement EPA NWI using
  housing-unit-weighted area-overlap tract reduction and listing
  point-in-polygon neighborhood context.
- Added the ingestion module:
  - `pipeline/gt/layers/walkability.py`
- Wired `walkability_index` into the layer runner dispatch and package export.
- Initial staging attempt hit sandbox/network DNS resolution for the Neon host;
  rerunning with approved network access worked.
- During staging, two implementation issues were fixed:
  - local PostGIS geometry columns are named `geom`; the runner now aliases
    them to `geometry` for GeoPandas operations.
  - long source fetch/geometry work no longer holds an idle database
    transaction open, avoiding Neon idle-in-transaction timeout.
- Staged both regions at tract + listing neighborhood-context grains and wrote
  promotable reports:
  - `data/reports/layer_walkability_index_pa-mainline_latest.json`
  - `data/reports/layer_walkability_index_hudson-valley_latest.json`
- Rendered QA maps:
  - `data/reports/qa/walkability_index_pa-mainline.png`
  - `data/reports/qa/walkability_index_hudson-valley.png`
- Promoted both reports after explicit human approval on 2026-06-18:
  - `layer_walkability_index_pa-mainline_latest.json`
  - `layer_walkability_index_hudson-valley_latest.json`

Staged validation:

- `pa-mainline`: 495/495 tracts; 251/251 listings; direct tract diagnostic
  covered 446 tracts, area-overlap fallback filled 49; range 3.33-19.27;
  `promotable: true`.
- `hudson-valley`: 437/437 tracts; 4,244/4,254 listings; direct tract
  diagnostic covered 328 tracts, area-overlap fallback filled 109; range
  2.67-19.33; `promotable: true`. The 10 unmatched listing IDs are recorded
  in the validation report for review.

Neon live `walkability_index` counts after promote:

- `region_metrics`: 932 tract rows:
  - `hudson-valley`: 437 census-tract rows, range 3.72-18.33.
  - `pa-mainline`: 495 census-tract rows, range 3.33-19.27.
- `listing_metrics`: 4,495 rows total:
  - `hudson-valley`: 4,244 `point` rows, range 2.67-19.33.
  - `pa-mainline`: 251 `point` rows, range 4.33-18.67.
- `district_metrics`: 139 district rollups:
  - `hudson-valley`: 78 rollups, range 3.72-15.84.
  - `pa-mainline`: 61 rollups, range 5.22-15.88.

### Phase 5 `flood_sfha`

- Drafted source onboarding for FEMA National Flood Hazard Layer (NFHL), Flood
  Hazard Zones layer.
- Added layer manifest:
  - `pipeline/manifests/layers/flood_sfha.yaml`
- Added onboarding note:
  - `docs/layer-onboarding/flood_sfha.md`
- Added a manifest validation test in:
  - `pipeline/tests/test_cli.py`
- Proposed approach: use FEMA NFHL `Flood Hazard Zones` layer 28, filter
  `SFHA_TF = 'T'`, reduce to census tracts as area share inside SFHA polygons,
  and attach listing values as exact point-in-polygon flags.
- Source metadata was inspected from the FEMA ArcGIS REST layer on 2026-06-18:
  polygon geometry, NAD83/EPSG:4269, max record count 2,000, and fields
  `FLD_ZONE`, `ZONE_SUBTY`, `SFHA_TF`, `STATIC_BFE`, `DEPTH`, and `SOURCE_CIT`.
- Full-region bounded count queries worked when `inSR=4326` was included:
  - `pa-mainline`: 8,534 SFHA features in the local tract envelope
    (`A`: 944, `AE`: 7,509, `AO`: 7, `VE`: 74).
  - `hudson-valley`: 15,974 SFHA features in the local tract envelope
    (`A`: 816, `AE`: 14,914, `AO`: 19, `AH`: 15, `VE`: 210).
- Geometry-heavy REST fetches were brittle: one-shot envelope geometry queries
  returned FEMA service errors, and long object-ID chunk fetches eventually hit
  connection resets. The onboarding packet recommends a resumable object-ID
  chunk cache or official NFHL file geodatabase/state extract under
  `data/raw/flood_sfha/` for implementation.
- Human approval was given on 2026-06-18 to implement FEMA NFHL using
  `SFHA_TF='T'`, tract area-share reduction, and listing point-in-polygon
  flags.
- Added the ingestion module:
  - `pipeline/gt/layers/flood_sfha.py`
- Wired `flood_sfha` into the layer runner dispatch and package export.
- Implemented a resumable source cache under `data/raw/flood_sfha/<region>/`
  with bounded object IDs and small FEMA feature chunks, plus retry/backoff.
- Staged both regions at tract + listing point-flag grains and wrote promotable
  reports:
  - `data/reports/layer_flood_sfha_pa-mainline_latest.json`
  - `data/reports/layer_flood_sfha_hudson-valley_latest.json`
- Rendered QA maps:
  - `data/reports/qa/flood_sfha_pa-mainline.png`
  - `data/reports/qa/flood_sfha_hudson-valley.png`
- Promoted both reports to Neon. Initial live verification found non-finite
  tract/district values on zero-overlap rows; the reducer was repaired,
  staging was rerun for both regions, and both reports were promoted again.

Staged validation:

- `pa-mainline`: 495/495 tracts; 251/251 listings; 8 listing point flags
  inside SFHA; 8,534 source features fetched; range 0.0-1.0; max tract share
  0.70; `promotable: true`.
- `hudson-valley`: 437/437 tracts; 4,254/4,254 listings; 113 listing point
  flags inside SFHA; 15,974 source features fetched; range 0.0-1.0; max tract
  share 0.92; `promotable: true`.

## 4. Recently Changed Files And Why

Current transportation-noise checkpoint:

- `pipeline/gt/layers/noise.py`: cached BTS ArcGIS tile ingestion, legend-color
  decoding, tract/listing reductions, staging, validation, and report output.
- `pipeline/manifests/layers/noise_*.yaml` and
  `docs/layer-onboarding/transportation_noise.md`: approved source evidence,
  resolution limits, ranges, and midpoint-estimate disclosure.
- `pipeline/gt/cli.py`, `pipeline/gt/layers/__init__.py`, and pipeline tests:
  register and cover all three noise metrics.
- `app/src/lib/finance/server-data.ts` and tests: add promoted district noise
  values to the Discovery payload.
- `app/src/lib/metrics/presentation.ts`, `RegionChoroplethMap.tsx`, and
  `DiscoveryEngine.tsx`: add the selectable ≥55 dBA map, selected-district
  value, modeled mean, and limitations explainer.
- `app/src/components/housing/ListingDetailPanel.tsx`: label and explain BTS
  mean/threshold metrics at listing point, 100 m, and tract context.
- `docs/CODEX_HANDOFF.md`: records validation, promotion, UI QA, and the next
  approved Phase 8 slice.

Recently committed:

- `9da3a0c Add Discovery purchasing power view`: first `/discover` UI,
  district purchasing-power choropleth, Explorer link, route tree, and district
  GeoJSON metadata.
- `89df754 Add district purchasing power server function`: server-side district
  purchasing-power query/function, mocked app tests, and handoff update.
- `7c0bfab Implement effective tax layer`: implemented `effective_tax_rate`
  layer runner using ACS 2024 5-year table-based bulk files, staged/promoted
  both regions, and updated onboarding provenance.
- `816b127 Add purchasing power finance engine`: pure TypeScript purchasing
  power engine and unit tests for mortgage constant, credit spreads, PMI, DTI
  ceiling, and Hudson Valley/Lower Merion ordering under different tax rates.
- `e90d5a4 Update handoff after tax onboarding`: handoff update after
  `effective_tax_rate` source onboarding.
- `617f0ab Draft effective tax rate onboarding`: ACS 2024 5-year manifest,
  onboarding note, and manifest validation test for `effective_tax_rate`;
  records the Census API key/bulk-file blocker before ingestion.
- `6a99c54 Fix Explorer panel lint issues`: formats the Explorer panel/server
  function files, formats two pre-existing app files that lint was already
  flagging, and fixes the selected-marker hook warning.
- `79abdff Update handoff after Explorer metrics panel`: handoff update after
  the first Explorer metrics panel checkpoint.
- `e44c204 Add Explorer listing metrics panel`: `getListingMetrics` server
  function, selected-listing detail panel, map click selection, compact
  environmental fields on listing GeoJSON, and canopy/flood filters.
- `2cc6a57 Repair flood SFHA finite shares`: flood reducer/validation repair,
  clean restaging, promotion, live aggregate verification, and handoff update.
- `a05eb92 Relax autonomous approval gates`: standing-approval instructions for
  already-planned data/application work.
- `172a9a7 Implement flood SFHA layer staging`: FEMA NFHL `flood_sfha`
  implementation, staging/validation/QA status, CLI wiring/tests, and the first
  autonomy-instruction update.
- `08f9196 Draft flood SFHA source onboarding`: draft FEMA NFHL manifest,
  onboarding note, and manifest validation test.
- `20922c9 Implement walkability layer`: EPA NWI source onboarding,
  implementation, staging/QA/promotion handoff updates, and CLI wiring/tests.
- `58e7b1e Clarify blocked phase work-ahead rules`: updates `AGENTS.md` phase
  rule to allow reversible, non-promoting work-ahead when a phase is blocked by
  external access or human review.
- `3a8c290 Draft light pollution layer onboarding`: draft-only
  `light_pollution_radiance` manifest and onboarding packet.

Committed in `133a59b Implement tree canopy layer staging`:

- `pipeline/gt/layers/tree_canopy.py`: new NLCD TCC reducer. Reads the approved remote ZIP-backed GeoTIFF, reduces to tract means and listing 100 m / 500 m buffer means, stages results, and writes validation reports.
- `pipeline/gt/cli.py`: registers `tree_canopy_pct` in the layer runner dispatch.
- `pipeline/gt/layers/__init__.py`: exports `run_tree_canopy`.
- `pipeline/tests/test_cli.py`: validates the tree canopy manifest and confirms the CLI recognizes the layer key.

Gitignored/generated local files under `data/` include validation JSON reports and QA PNGs. These are reviewed locally but not committed under the current ignore policy.

`app/.env.local` contains the Neon `DATABASE_URL`; do not print it and do not commit secrets.

Committed in `42d9b30 Implement risk index layer staging`:

- `pipeline/gt/layers/risk_index.py`: new FEMA/RAPT NRI direct-join layer runner. Fetches tract rows by manifest counties from the official ArcGIS service, joins `TRACTFIPS` to local tract `regions.source_id`, stages `RISK_SCORE`, and writes validation reports.
- `pipeline/manifests/layers/risk_index.yaml`: approved layer manifest.
- `docs/layer-onboarding/risk_index.md`: approved onboarding packet and sample statistics.
- `pipeline/gt/cli.py`: registers `risk_index` in the layer runner dispatch.
- `pipeline/gt/layers/__init__.py`: exports `run_risk_index`.
- `pipeline/tests/test_cli.py`: validates the risk index manifest and confirms the CLI recognizes the layer key.

## 5. Current Branch / Worktree Status

- Branch: `main`
- Worktree: `/Users/katherine/Dropbox/school-district-home-search`
- Latest pushed checkpoint before the current commit: `f44e9b6 Implement Phase
  8 annual AQI layer`.
- Current checkpoint: Phase 8 BTS transportation-noise source packet, reducer,
  promotion, app integration, and QA described below.
- Expected handoff state after the checkpoint commit: clean and pushed.

## 6. Known Issues, Failing Checks, Or Unfinished Work

Known caveats:

- `uv` is not available in this shell; commands were run through the existing `pipeline/.venv` instead.
- `data/processed/listings.geojson` in this checkout is a 3-row sample, not the full frozen 4,505 listing dataset. The full frozen dataset is in Neon and is validated by the golden tests.
- The `canopy_height_m` source native resolution is about 1.2 m, but the current POC reducer uses a 4096 x 4096 overview grid per zoom-10 tile, roughly 9.6 m working resolution, for practical remote COG reads. This is recorded in the manifest and metric notes. It is appropriate for tract means and 100 m listing buffers, but not a final house-to-house pixel-level QA pass.
- The `tree_canopy_pct` reducer reads the public NLCD TCC ZIP-backed GeoTIFF remotely rather than caching the full 3.6 GB archive locally.
- GeoPandas emits warnings about direct psycopg connections not being SQLAlchemy connectables. These are warnings, not failures.
- README still begins with the original prototype overview, but now records the
  active Discovery ranking/map conventions plus the approved future hard-
  constraint and walking-access design so those decisions are not lost.
- Phase 5 clean enrichment layers are promoted: `canopy_height_m`,
  `tree_canopy_pct`, `risk_index`, `walkability_index`, `flood_sfha`, and
  `light_pollution_radiance`. Explorer listing metrics panel/environmental
  filters are implemented. Remaining work is app polish and later-phase data,
  not a blocked Phase 5 source.
- `light_pollution_radiance` uses the local authenticated EOG file
  `data/raw/eog/VNL_npp_2025_global_vcmslcfg_v2_c202604011200.median_masked.dat.tif.gz`.
  Raster verification passed: EPSG:4326, 86,401 x 33,601 pixels, one `float32`
  band. Sample stats were plausible: PA Main Line/Philadelphia-facing sample
  mean 23.137, lower Westchester/Yonkers mean 18.845, Putnam mean 2.446
  `nW/cm2/sr`.
- `effective_tax_rate` is promoted to public/live metric tables from official
  ACS 2024 5-year table-based Summary File bulk downloads. It uses
  county-subdivision rows only (`mun-cousub-*`) because including both county
  subdivisions and places would double-count many tract overlaps.
- `median_home_value` is promoted for both regions through the approved Zillow
  plus Census/ACS housing-unit-weighted path. The large local source files
  remain gitignored.
- `walkability_index` is promoted to public/live metric tables. Staging rows
  may still exist as the last staged source of truth for the promote reports.
- `flood_sfha` is promoted to public/live metric tables. The initial promote
  surfaced `NaN` tract/district aggregates for zero-overlap tracts; the reducer
  now fills non-finite shares with `0.0`, validation reports `tract_nonfinite`
  and `listing_point_nonfinite`, and promotion was rerun cleanly.
- GVI/perceived green is not part of Phase 5. Per spec, `gvi_ndvi_street` is Phase 8 and Mapillary/segmentation `gvi_streetlevel` is Phase 11.

Checks last run after repaired `flood_sfha` promotion:

- Manifest validation passed for `walkability_index` with `./.venv/bin/gt manifest validate layer manifests/layers/walkability_index.yaml`.
- Python compile check passed for `gt/layers/walkability.py`, `gt/cli.py`, and
  `gt/layers/__init__.py`.
- CLI test slice passed with `./.venv/bin/pytest tests/test_cli.py -q`:
  `12 passed in 0.63s`.
- Walkability reports validated with:
  - `./.venv/bin/gt validate --report layer_walkability_index_pa-mainline_latest.json`
  - `./.venv/bin/gt validate --report layer_walkability_index_hudson-valley_latest.json`
- Required golden Neon checks passed with `./.venv/bin/pytest -k golden -q`:
  `11 passed, 12 deselected in 8.83s`.
- Full Neon-backed pipeline suite passed with `./.venv/bin/pytest -q`:
  `23 passed in 13.96s` before promote and `23 passed in 10.45s` after promote.
- Golden Neon checks included:
  - 4,505 listings
  - 0 missing districts
  - pinned PA/NY address -> district facts
  - nearest fallback count/cap
  - SRID and geometry validity checks
- Public metric counts and `district_metrics` rollups were confirmed after
  `walkability_index` promote.
- Python compile check passed for `gt/layers/flood_sfha.py`.
- Re-ran `gt layer run flood_sfha --region pa-mainline --grain both` and
  `gt layer run flood_sfha --region hudson-valley --grain both`; both reports
  are `promotable: true`, with `tract_nonfinite: 0`,
  `listing_point_nonfinite: 0`, and range `0.0-1.0`.
- Re-promoted both flood reports after repair.
- Live `region_metrics` now has 495 PA tract rows, range 0.0-0.700938, and
  437 Hudson Valley tract rows, range 0.0-0.916032.
- Live `listing_metrics` now has 251 PA point rows with 8 SFHA flags and 4,254
  Hudson Valley point rows with 113 SFHA flags, all in range 0.0-1.0.
- Live `district_metrics` now has 61 PA rollups, range 0.006021-0.472059, and
  78 Hudson Valley rollups, range 0.013731-0.447256.
- Verified zero `NaN` rows in live `region_metrics`, `listing_metrics`,
  `district_metrics`, and staged flood tract metrics.
- CLI test slice passed with `./.venv/bin/pytest tests/test_cli.py -q`:
  `14 passed in 0.63s`.
- Required golden Neon checks passed with `./.venv/bin/pytest -k golden -q`:
  `11 passed, 14 deselected in 10.90s`.
- Full Neon-backed pipeline suite passed with `./.venv/bin/pytest -q`:
  `25 passed in 9.45s`.
- App lint passed with `npm run lint`: 0 errors, 6 pre-existing shadcn
  fast-refresh warnings.
- App tests passed with `npm test`: `6 passed`.
- App production build passed with `npm run build`.
- Vite dev server started on `http://localhost:8080/`; localhost `HEAD /`
  returned `HTTP/1.1 200`. In-app browser visual QA was attempted, but the
  browser connector failed before opening a session in this thread, so visual
  inspection is still a useful follow-up.
- `effective_tax_rate` manifest validation passed with
  `./.venv/bin/gt manifest validate layer manifests/layers/effective_tax_rate.yaml`.
- Pipeline CLI test slice passed with `./.venv/bin/pytest tests/test_cli.py -q`:
  `15 passed in 1.02s`.
- After implementation, `effective_tax_rate` staged cleanly for both regions:
  - `pa-mainline`: 184/184 source county subdivisions valid; 495/495 tracts;
    range 0.00631-0.03437; mean 0.01551; `promotable: true`.
  - `hudson-valley`: 60/60 source county subdivisions valid; 437/437 tracts;
    range 0.00483-0.02962; mean 0.01746; `promotable: true`.
- Generated QA maps:
  - `data/reports/qa/effective_tax_rate_pa-mainline.png`
  - `data/reports/qa/effective_tax_rate_hudson-valley.png`
- Promoted both reports and verified live counts/ranges:
  - `region_metrics`: 495 PA rows, 437 Hudson Valley rows.
  - `district_metrics`: 61 PA rollups, range 0.00631-0.02738; 78 Hudson
    Valley rollups, range 0.00550-0.02802.
  - Lower Merion district rollup is 0.01228; this is below the rough
    `docs/tasks.md` 1.5-2.5% anchor, but reflects ACS median tax divided by
    ACS median value rather than statutory millage or assessor-derived rate.
    Hudson Valley high-tax examples are in the expected 2-3% range.
- Effective tax post-promote checks passed:
  - `./.venv/bin/gt manifest validate layer manifests/layers/effective_tax_rate.yaml`
  - `./.venv/bin/pytest tests/test_cli.py -q`: `16 passed`
  - `./.venv/bin/pytest -k golden -q`: `11 passed, 16 deselected`
  - `./.venv/bin/pytest -q`: `27 passed`
- Finance/app tests passed after adding the finance engine with `npm test`:
  `2 passed`, `11 tests passed`.
- App lint passed after adding the finance engine with `npm run lint`: 0
  errors, 6 pre-existing shadcn fast-refresh warnings.
- App production build passed with `npm run build` after the finance engine
  change.
- App checks passed after adding `getDistrictPurchasingPower`:
  - `npm test`: 3 test files, 14 tests passed.
  - `npm run lint`: 0 errors, 6 pre-existing shadcn fast-refresh warnings.
  - `npm run build`: production client and SSR builds passed.
- App checks passed after adding the first `/discover` surface:
  - `npm test`: 3 test files, 14 tests passed.
  - `npm run lint`: 0 errors, 6 pre-existing shadcn fast-refresh warnings.
  - `npm run build`: production client and SSR builds passed; TanStack route
    tree regenerated for `/discover`.
  - Local dev server served `http://127.0.0.1:8081/discover` with `HTTP 200`.
  - In-app browser visual QA was attempted, but the browser connector failed
    before opening a session in this thread, so a screenshot/manual browser pass
    is still useful.
- App checks passed after adding URL-profile handoff:
  - `npm test`: 3 test files, 14 tests passed.
  - `npm run lint`: 0 errors, 6 pre-existing shadcn fast-refresh warnings.
  - `npm run build`: production client and SSR builds passed.
  - Local dev server served `/discover?monthlyBudget=6500&downPayment=15&creditBand=fair&regionGroup=hudson-valley`
    and `/?district=Lower%20Merion&maxPrice=800000&monthlyBudget=6500`
    with `HTTP 200`.
- Chrome/local QA follow-up:
  - Opening `/discover?monthlyBudget=6500&downPayment=15&creditBand=fair&regionGroup=hudson-valley`
    in Chrome initially exposed a hydration mismatch from client-only URL-param
    initialization and a Leaflet canvas renderer error in the choropleth.
  - Both issues were fixed; after reload, the prior hydration and Leaflet
    errors did not recur in the dev-server logs.
  - `npm test`, `npm run lint`, and `npm run build` passed again after the
    fixes.
  - Visual screen inspection via Computer Use is now working after macOS
    permissions were granted.
- Chrome visual QA after Discovery feedback pass:
  - Loaded `/discover?monthlyBudget=6500&downPayment=180000&creditBand=fair&regionGroup=hudson-valley`
    and confirmed the map paints, the legend reads "Buying ceiling", and the
    explanatory copy states cooler colors mean the same payment stretches
    farther.
  - Edited the down payment field to `250000`; URL, average buying ceiling,
    selected district buying ceiling, and ranking updated.
  - Verified the top Explorer header link is plain `/`, while the selected
    district "Search listings" link carries `monthlyBudget`, dollar
    `downPayment`, `creditBand`, `regionGroup`, `district`, and `maxPrice`.
  - `npm test`: 3 test files, 15 tests passed.
  - `npm run lint`: 0 errors, 6 pre-existing shadcn fast-refresh warnings.
  - `npm run build`: production client and SSR builds passed.
- Chrome visual QA after Explorer UX follow-up:
  - Raised the Explorer min-canopy filter in Chrome; the listing count changed
    while the map viewport stayed in place instead of refitting to the new
    result bounds.
  - Opened a filtered listing detail panel and confirmed canopy/flood context
    renders in the panel, including the filter-relevant 100 m canopy value.
  - Dev-server logs showed no new runtime errors beyond the existing TanStack
    Start CSRF warning.
  - `npm test`: 3 test files, 15 tests passed.
  - `npm run lint`: 0 errors, 6 pre-existing shadcn fast-refresh warnings.
  - `npm run build`: production client and SSR builds passed.
- `light_pollution_radiance` compile/manifest/CLI checks passed after adding
  the runner:
  - `./.venv/bin/python -m compileall gt/layers/light_pollution.py gt/cli.py gt/layers/__init__.py`
  - `./.venv/bin/gt manifest validate layer manifests/layers/light_pollution_radiance.yaml`
  - `./.venv/bin/pytest tests/test_cli.py -q`: `18 passed in 0.87s`.
- `light_pollution_radiance` staged and validated for both regions:
  - `pa-mainline`: 495/495 tracts, range 0.680-77.168, `promotable: true`.
  - `hudson-valley`: 437/437 tracts, range 0.259-100.720,
    `promotable: true`.
- Light-pollution QA maps rendered:
  - `data/reports/qa/light_pollution_radiance_pa-mainline.png`
  - `data/reports/qa/light_pollution_radiance_hudson-valley.png`
- Light-pollution promotion completed for both reports and live verification
  confirmed 932 tract rows, 139 district rollups, and zero listing rows by
  design.
- Required golden Neon checks passed after promotion with
  `./.venv/bin/pytest -k golden -q`: `11 passed, 18 deselected in 10.32s`.
- Full local pipeline suite passed with `./.venv/bin/pytest -q`:
  `18 passed, 11 skipped in 0.50s`.
- Discovery scoring app checks passed:
  - `npm test`: 3 test files, 16 tests passed.
  - `npm run lint`: 0 errors, 6 pre-existing shadcn fast-refresh warnings.
  - `npm run build`: production client and SSR builds passed.
  - Live Neon smoke query confirmed 78 Hudson Valley and 61 PA districts have
    the environmental metric inputs expected by Discovery scoring.
  - Chrome QA loaded weighted `/discover` URL, verified priority sliders,
    match percentages, buying ceilings, clean URL hydration, and no console
    errors.
- Discovery selected-district polish checks passed:
  - `npm test`: 3 test files, 16 tests passed.
  - `npm run lint`: 0 errors, 6 pre-existing shadcn fast-refresh warnings.
  - `npm run build`: production client and SSR builds passed.
  - Chrome QA loaded the weighted `/discover` URL after a clean dev-server
    restart, verified the selected sidebar panel, selected map card, legend,
    known district values, and no recent console errors. True mobile emulation
    was not available through the current Chrome connector.
- Explorer map legend checks passed:
  - `npm test`: 3 test files, 16 tests passed.
  - `npm run lint`: 0 errors, 6 pre-existing shadcn fast-refresh warnings.
  - `npm run build`: production client and SSR builds passed.
  - Chrome QA loaded `/`, verified 4,505 listings, the map legend text, and no
    post-fix Leaflet console errors.

### Median Home Value Implementation Checkpoint

- Local inputs are now present for the approved housing-unit-weighted
  ZCTA-to-school-district median-home-value path:
  - Zillow ZHVI ZIP file with latest local column `2026-05-31`.
  - Census 2020 ZCTA-to-tabulation-block relationship TXT.
  - PA and NY Census 2020 PL ZIPs.
  - ACS 2024 B25077 ZCTA fallback value file.
- Added `median_home_value` manifest and source-onboarding note.
- Added a pipeline layer that:
  - reads Zillow ZIP/ZCTA values and ACS fallback values;
  - reads PL 2020 block housing-unit counts and block school-district codes;
  - streams the Census ZCTA-to-block relationship file;
  - allocates block housing units to `(ZCTA, school district)` by block-part
    area share;
  - stages direct school-district `region_metrics` rows with validation checks
    for coverage, range, ZCTA count, Zillow/ACS/missing housing-unit shares,
    and output distribution.
- Added `004_direct_district_metrics.sql` so `district_metrics` includes both
  tract rollups and direct school-district metrics, preferring direct metrics
  where they exist for the same district/metric/vintage.
- Wired `median_home_value` into the layer CLI and promotion metadata as a
  `school_district`-grain metric.
- Local verification passed:
  - `./.venv/bin/python -m compileall gt/layers/median_home_value.py gt/layers/runner.py gt/layers/__init__.py gt/cli.py`
  - `./.venv/bin/gt manifest validate layer manifests/layers/median_home_value.yaml`
  - `./.venv/bin/pytest tests/test_median_home_value.py tests/test_cli.py -q`: 24 passed.
  - `env -u DATABASE_URL ./.venv/bin/pytest -q`: 24 passed, 11 skipped.
- User ran the database-backed stage/QA/promote commands locally because the
  Codex sandbox could not connect to Neon. Validation and promotion succeeded:
  - `pa-mainline`: 62/62 districts, range `$139,796-$1,034,863`, Zillow HU
    share `99.84%`, ACS fallback HU share `0.09%`, missing HU share `0.07%`.
  - `hudson-valley`: 78/78 districts, range `$323,783-$2,459,646`, Zillow HU
    share `94.05%`, ACS fallback HU share `5.65%`, missing HU share `0.30%`.
- QA maps generated locally:
  - `data/reports/qa/median_home_value_pa-mainline.png`
  - `data/reports/qa/median_home_value_hudson-valley.png`
- Live `district_metrics` verification after promote:
  - `hudson-valley`: 78 rows, range `323782.58814902324-2459645.916249137`.
  - `pa-mainline`: 62 rows, range `139795.92632345334-1034862.5737386206`.

### Discovery Copy/Input Polish Checkpoint

- Discovery dollar text fields now commit numeric changes on blur or Enter
  instead of updating the URL/query on every keystroke. This keeps the down
  payment field as a dollar amount while making it easier to edit.
- Down payment now accepts `$0` as a valid explicit fixed amount; monthly
  payment still requires a positive amount.
- Replaced user-facing "buying ceiling"/"ceiling" wording with "max home
  price"/"max price" in the Discovery map card, legend, tooltip, and map color
  explanation.
- App verification passed:
  - `npm test`: 3 test files, 16 tests passed.
  - `npm run lint`: 0 errors, 6 pre-existing shadcn fast-refresh warnings.
  - `npm run build`: production client and SSR builds passed.
- `curl -I http://localhost:8080/discover` returned HTTP 200 from the local dev
  server.
- Chrome connector QA was attempted but the connector hung on local navigation
  and again on browser-session cleanup. Do not treat this as an app failure;
  re-run visual QA when the browser connector is stable.

### Discovery Median Home Value Integration Checkpoint

- Discovery now uses the promoted `median_home_value` district metric in the
  purchasing-power server function.
- The budget-fit score now prefers `maxPurchasePrice / medianHomeValue` when a
  median value is present, falling back to raw `maxPurchasePrice` only when the
  median value is unavailable.
- Fixed a scoring bug where component scores of `0` were treated as missing
  and skipped from weighted averages.
- Discovery UI now shows:
  - selected district median value;
  - budget fit as percent of median value;
  - ranked card fit context;
  - map tooltip and selected map card fit context.
- App verification passed:
  - `npm test`: 3 test files, 17 tests passed.
  - `npm run lint`: 0 errors, 6 pre-existing shadcn fast-refresh warnings.
  - `npm run build`: production client and SSR builds passed.

### Phase 7 `park_access` Source Onboarding Checkpoint

- Added `pipeline/manifests/layers/park_access.yaml`.
- Added `docs/layer-onboarding/park_access.md`.
- Source packet uses:
  - OpenStreetMap via `osmnx` for local park/open-space polygons.
  - USGS PAD-US Public Access FeatureServer for nationally aggregated public
    access/protected open-space polygons.
- Evidence gathered from USGS/PAD-US:
  - PAD-US is the official national inventory of protected areas and public
    parks/open space.
  - PAD-US 4.x citation DOI is `10.5066/P96WBCHS`.
  - PAD-US web services expose a Public Access FeatureServer.
  - Public access categories include `OA` open access, `RA` restricted access,
    and `XA` closed access.
  - PAD-US documentation notes local park data gaps and categorical public
    access assignment, so OSM is included as a local-detail supplement.
- Inclusion rule for implementation:
  - Default metric includes PAD-US `OA` and public OSM park/open-space
    polygons.
  - Track PAD-US `RA` separately for QA; do not include restricted access in
    the default metric unless the UI/product copy explicitly labels it.
  - Exclude PAD-US `XA` and unknown/non-public access from the default metric.
- Verification passed:
  - `./.venv/bin/gt manifest validate layer manifests/layers/park_access.yaml`
  - `./.venv/bin/pytest tests/test_cli.py -q`: 21 passed.

### August 2026 UX Feedback Checkpoint

- Discovery ranks by the existing deterministic internal score but exposes only
  an explicit ordinal such as `#1 of 78 districts`, the named comparison area,
  and factor-level strengths/tradeoffs.
- Purchasing power now shows an estimated max home price separately from the
  district median value, with the rate, credit, tax, insurance, PMI, 30-year
  term, and exclusions available in the UI.
- Discovery and Explorer can shade one district-level context layer at a time:
  purchasing power (Discovery), tree coverage, FEMA flood-zone exposure, light
  pollution, EPA walkability, or natural-hazard risk. Legends and tooltips use
  plain language and state the geographic grain.
- Explorer now carries the listing `tree_canopy_pct` 100 m value in compact
  GeoJSON, filters with consumer tree-cover categories, and presents raw canopy
  height only as supporting detail.
- Discovery handoff adds the district slug; Explorer performs its initial fit
  against that district geometry before preserving the user-controlled map
  viewport. The Port Jervis QA profile landed on Port Jervis with 71 listings
  under the estimated max-price filter.
- Browser QA confirmed all 78 Hudson Valley ranked districts render, map layer
  switching works, listing markers remain selectable above district shading,
  the purchasing-power and EPA/flood/canopy/light explainers render, and the
  compact/mobile filter sheet uses the new tree-cover and FEMA language.
- Durable before/after images and capture notes are under:
  - `docs/screenshots/before-ui-feedback-2026-08-21/`
  - `docs/screenshots/after-ui-feedback-2026-08-22/`
- Final app verification passed:
  - `npm test`: 5 test files, 21 tests passed.
  - `npm run lint`: 0 errors and the same 6 pre-existing shadcn fast-refresh
    warnings.
  - `npm run build`: production client and SSR builds passed.

### Phase 7 Park Access Implementation Checkpoint

- Added a cached OpenStreetMap + USGS PAD-US reducer that includes PAD-US open
  access (`OA`) and public OSM park/open-space polygons while excluding
  explicit private-access OSM features.
- Split the approved task into honest companion metrics:
  - `park_access`: census-tract share within 800 m of mapped public open space.
  - `park_distance_m`: listing-point distance to the nearest mapped public
    park/open-space polygon edge.
- Both regions staged with promotable reports and visually plausible QA maps,
  then were explicitly promoted.
- Live verification:
  - `park_access`: 495 PA tracts and 437 Hudson Valley tracts; district rollups
    for 61 active PA and 78 Hudson Valley districts.
  - `park_distance_m`: all 251 PA and 4,254 Hudson Valley listings; PA median
    181 m and Hudson Valley median 270 m.
- App integration adds park-access scoring, URL-backed priority weight, map
  layer, selected-district context, and listing park-distance explanations.
- Post-promote checks: full Neon-backed pipeline suite `40 passed`; app tests
  `22 passed`; app lint has zero errors and six pre-existing shadcn warnings;
  production build passes.

### Live PMMS Mortgage Rate Checkpoint

- Added a server-only official FRED/PMMS CSV reader with strict latest-row
  parsing, a 3-second timeout, a 24-hour in-process cache, and the existing
  6.75% base-rate fallback.
- Purchasing-power responses now include rate source/date provenance, and the
  calculation explainer states whether the base came from PMMS, a caller, or
  fallback before applying the selected credit spread.
- The official feed returned the 2026-08-20 PMMS observation at 6.65% during
  implementation verification.
- App verification: `25 passed`, lint with zero errors/six existing warnings,
  and production client/SSR build passed.

### Release Readiness Checkpoint

- Added canonical `/explore` and `/discover/results` routes while keeping the
  original `/` and `/discover` routes for backward compatibility.
- Replaced generated/Lovable consumer metadata and labels with Groundtruth
  branding and added a secret-safe environment example.
- Forced the Nitro `cloudflare-module` production build, named the Worker
  `groundtruth-home-search`, added the generated-config deploy command, and
  documented required secrets plus the signed-out production smoke journey.
- Added app/pipeline GitHub Actions CI and weekly Dependabot checks.
- Added request-specific retry states for Explorer and Discovery, removed raw
  error logging from active server/client paths, added a financial-profile
  leakage regression test, and enabled TanStack server-function CSRF
  middleware.
- Browser QA verified both canonical routes, live PMMS provenance, promoted
  park access, the Discovery-to-Explorer URL handoff, all 139 ranked districts,
  and a compact 390 x 844 layout. It also caught and fixed missing URL down
  payment being coerced to zero; absent values now preserve the $150,000
  default while explicit zero remains valid.
- App verification: `29 passed`, lint with zero errors/six existing warnings,
  canonical-route HTTP 200 checks, and a successful Cloudflare Nitro bundle.

### Phase 7 Transit And Commute Checkpoint

- Added cached Transitland pagination with active-feed filtering, stable stop
  deduplication, feed-version evidence, tract stop density, and listing
  straight-line nearest-stop distance.
- Added ORS matrix routing through the current HeiGIT API host with cached
  requests, population-weighted tract origins from official 2024 ACS block
  groups, routing/snap provenance, and explicit missing-route accounting.
- All six region/metric reports were promotable, QA-rendered, and explicitly
  promoted. Live public counts are 495 PA + 437 Hudson Valley tract rows for
  transit access, 251 PA + 4,254 Hudson Valley listing distances, 493 PA
  Center City commute rows, and 437 Hudson Valley Grand Central commute rows.
  The two missing PA values are explicitly unroutable ORS cells; 99.596%
  coverage remains above the approved 99% threshold.
- Discovery exposes district transit-stop density and region-appropriate drive
  time as map layers and selected-district context. Explorer listing details
  expose transit proximity as straight-line street context, not service
  frequency or routed walking distance.
- Post-promote verification: full Neon-backed pipeline suite `49 passed`,
  spatial golden suite `11 passed`, app suite `33 passed`, lint has zero errors
  and six existing shadcn warnings, and the Cloudflare production build passes.

### Phase 8 Transportation Noise Checkpoint

- Added the official BTS National Transportation Noise Map source packet and a
  cached ArcGIS tile reducer for the current combined model (2022 aviation and
  rail, 2023 road). The source is a national 24-hour LAeq screening model, not
  a live or address-specific measurement.
- The reducer maps published RGBA legend colors instead of tile palette indexes
  because the ArcGIS service may reorder palette entries per tile. Transparent
  cells are treated as below the published 45 dBA floor. Threshold metrics
  preserve exact classes; `noise_mean_dba` is explicitly labeled as a
  class-midpoint estimate.
- `noise_mean_dba`, `noise_pct_over_45`, and `noise_pct_over_55` staged with
  complete tract and listing point/100 m coverage for both regions. All six
  reports were promotable, all six QA maps were visually plausible, and all
  six reports were explicitly promoted.
- Live counts: 495 PA and 437 Hudson Valley tract rows per metric; all 251 PA
  and 4,254 Hudson Valley listings at both point and 100 m grains; 61 active PA
  and 78 Hudson Valley district rollups per metric.
- Discovery shows the district share at or above 55 dBA, the modeled mean, a
  selectable map, and BTS limitations. Explorer shows all three metrics with
  point/buffer/tract labels and the same limitations.
- Post-promote verification: pipeline suite `58 passed`; live golden suite
  `11 passed`; app suite `33 passed`; lint has zero errors and six existing
  shadcn warnings; Cloudflare production build passes. Local browser QA
  confirmed live values and the interactive transportation-noise map layer.

### Phase 8 AQI Checkpoint

- Added an approved EPA AQS/AirData source packet and manifest for
  `aqi_annual_mean`. The reducer uses official account-free 2025 daily-summary
  ZIPs after the configured AQS API pair returned invalid, so the credential is
  no longer a build gate.
- The reducer takes the maximum EPA-calculated AQI per monitor site/day across
  supported criteria pollutants and duplicate standards, keeps sites with at
  least 30 valid days, computes annual monitor means, applies inverse-distance-
  squared weighting within 30 km, and uses a day-weighted county monitor mean
  only when no monitor is within range.
- Both regions staged at 100% tract coverage with no non-finite or missing
  tracts and plausible QA maps, then were explicitly promoted. Live counts are
  495 PA tracts / 61 active district rollups and 437 Hudson Valley tracts / 78
  active district rollups. Ranges are 36.48–46.49 PA and 29.57–45.19 Hudson
  Valley.
- Discovery exposes annual mean daily AQI as a selectable district map and
  selected-district card. Explorer inherits it only as census-tract
  Neighborhood Context with an interpolation/fallback honesty explainer.
- Post-promote verification: full Neon-backed pipeline suite `53 passed`,
  spatial golden suite `11 passed`, app suite `33 passed`, lint has zero errors
  and six existing shadcn warnings, Cloudflare production build passes, and
  local browser map interaction has no console errors.

### Phase 8 Supplemental Noise Sources Checkpoint

- Added cached OpenStreetMap source extraction for fire stations, police
  stations, hospitals, bars, pubs, nightclubs, and industrial land, plus the
  official FRA North American Rail Network line service filtered to active
  freight-capable main, industrial, siding, and yard classifications.
- Added four complete tract layers: `noise_siren_density`,
  `noise_nightlife_density`, `noise_industrial_land_pct`, and
  `noise_freight_rail_density`; each has 495 PA and 437 Hudson Valley rows.
- Added four complete listing layers: `noise_siren_distance_m`,
  `noise_nightlife_count_300m`, `noise_industrial_distance_m`, and
  `noise_freight_rail_distance_m`; each has all 4,505 frozen listings.
- A follow-up provenance audit added `buffer_300m` to the allowed listing
  grains and re-promoted `noise_nightlife_count_300m` under that exact grain;
  live verification shows 4,505 `buffer_300m` rows and no generic point rows.
- All 16 reports passed validation and visual spatial QA before explicit
  promotion. Explorer derives clear nearby/within-500 m labels and provides
  OSM/FRA limitations; Discovery exposes all four district context maps but
  does not use them in ranking.
- The golden check pins `PA-209` at 26.3 m from an active freight-capable rail
  line. Post-promote verification: full Neon-backed pipeline suite `64 passed`;
  app suite `34 passed`; lint has zero errors and six existing shadcn warnings;
  Cloudflare production build passes. Local browser QA confirmed live district
  values and a clean Discovery layout.

### Typed Shareable Profile Checkpoint

- Centralized Discovery URL defaults, types, parsing, and serialization in a
  pure module shared by the UI and tests.
- Invalid URL values now fall back independently instead of corrupting the
  whole profile; zero down payment remains an intentional supported value.
- Explorer filter edits update the current URL while preserving budget,
  credit, scoring weights, region, and district-focus context from Discovery.
- App verification: `32 passed`; lint has zero errors and the same six
  pre-existing shadcn fast-refresh warnings; the Cloudflare Nitro production
  bundle passes.

### Phase 9 Archetype And Narrative Foundation

- Added forward-only, versioned `archetype_models`, `archetypes`, and
  `region_archetypes` schema plus a narrative cache keyed by region pair,
  profile bucket, and structured-payload hash.
- Added a dependency-free fixed-seed k-means implementation, percentile
  normalization with median imputation for sparse cells, k=4..9 silhouette
  selection, atomic model persistence, top-five distinguishing features, and
  CLI commands for build, pending Claude labels, and explicit human approval.
- The live 139-district build intentionally refused persistence: the best
  k-means silhouette is `0.192`, below the architecture's `0.25` threshold.
  The specified HDBSCAN fallback requires a new Python dependency and therefore
  remains an explicit dependency approval gate. No weak model or label was
  written.
- Added the Anthropic Messages API path without an SDK dependency, strict
  pending-versus-approved label visibility, structured tradeoff payloads, a
  deterministic narrative fallback, and a numeral post-check. Tests inject an
  unsupported `17`/`99` and prove the Claude result is rejected in favor of the
  template.
- Discovery queries approved labels only and remains unchanged while no model
  is ready. Verification: pipeline suite `71 passed`; app suite `37 passed`;
  lint has zero errors and six existing shadcn warnings; Cloudflare build
  passes; signed-out browser QA still returns all 139 districts.

### Production Deployment Preflight

- Wrangler is authenticated with the configured account-scoped API token for
  the intended personal Cloudflare account.
- A read-only secret check confirms that `groundtruth-home-search` does not yet
  exist, so the next deploy is a first release rather than an update. No stale
  Worker or secret set needs reconciliation.
- `docs/deployment.md` now distinguishes server secrets from public production
  configuration, records the Phase 12 secret names, and documents first-release
  plus signed-out and optional-account smoke checks. No secret values are
  checked in.
- A custom domain is not required for the initial `workers.dev` smoke release,
  but production deployment remains gated on the app checkpoint and Worker
  secret configuration.

## 7. Recommended Next Steps

Recommended next chat boundary: optional. Continue in the current task while
the Phase 8 build path remains stable.

Next actions, in order:

1. Approve adding the `hdbscan` Python dependency, run the required fallback,
   inspect the versioned assignments, generate pending labels, and explicitly
   approve product copy only after review. The k-means result must not be used.
2. Configure the intended Cloudflare account, production secrets, and domain,
   then run the documented production smoke journey. This is an external-state
   release action, not a local implementation gap.
3. Continue Phase 12 using the configured Better Auth, Resend, and Turnstile
   environment values; accounts must remain an optional save layer and never
   gate the signed-out journey.
4. Keep satellite GVI deferred; Mapillary remains the Phase 11 research track.

Phase 8 AQS access note: on 2026-08-25, the configured email/key pair was
present but EPA returned `Email and/or key are invalid.` This no longer gates
the layer because EPA's equivalent official daily-summary AirData ZIPs are
account-free; the reducer uses those deterministic bulk archives instead.

## 8. Standing Chat-Continuity Instruction

Prefer continuing in the current chat. Do not recommend a fresh chat after
every commit, data gate, or mode change. Recommend a fresh chat only when:

- context is likely unreliable or too compressed to continue safely;
- the next work is a substantially different arc and the user wants a clean
  restart;
- the user explicitly asks for a new chat/thread.

At meaningful checkpoints, update `docs/CODEX_HANDOFF.md` with:

- Current branch, latest commit, and worktree status.
- What changed and why.
- Validation/test results.
- Data staging/promotion status.
- Remaining blockers, missing information, and explicit "do not do" constraints.

Default continuation prompt:

```text
Read AGENTS.md and docs/CODEX_HANDOFF.md. Continue the next Groundtruth arc
from the latest committed state.

Work autonomously for as long as the build path remains stable. Do not stop
after one checkpoint. Continue through multiple data, pipeline, and UI
checkpoints when they are unblocked. Commit and push each green checkpoint when
working an autonomous arc. Treat source and application choices already
documented in the approved architecture/tasks/handoff as standing approval.
Stop only for a real blocker, genuinely missing information from the user, a
conflict with the source-of-truth docs, or a point where the next meaningful
work requires new product/design direction that cannot be inferred responsibly.
```

## 9. Assumptions And Uncertainty

- Assumed `app/.env.local` points to the intended Neon database; this was confirmed by listing counts and passing golden tests.
- Region scaffolding handles tract -> district and tract -> municipality
  overlaps. `median_home_value` now implements its own streamed
  ZCTA/block/housing-unit crosswalk, stages direct school-district metrics, and
  is promoted/verified in Neon. Codex sandbox database connectivity remains
  unreliable; user Terminal can reach Neon.
- Data/report artifacts under `data/` are gitignored. They exist locally and were used for QA, but they will not be part of a normal commit unless the ignore policy changes.
- `tree_canopy_pct` is promoted to public/live metric tables. Staging rows may still exist as the last staged source of truth for the promote reports.
- `risk_index` is promoted to public/live metric tables. Staging rows may still exist as the last staged source of truth for the promote reports.
- `walkability_index` is promoted to public/live metric tables. Staging rows may still exist as the last staged source of truth for the promote reports.
- `light_pollution_radiance` manifest uses verified vintage `2025`.
- `walkability_index` manifest uses citation vintage `2021` based on Data.gov
  metadata and EPA's 2021 Smart Location Database lineage. ArcGIS REST sampling
  verified the needed fields and score range; the ZIP members are still
  uninspected because the 405 MB ZIP was not downloaded.
- `flood_sfha` manifest uses `live-nfhl` vintage because the FEMA map service
  is live/current. Implementation should record retrieval date in validation
  reports.

## 10. Suggested Prompt For Next Codex Chat

```text
Read AGENTS.md and docs/CODEX_HANDOFF.md. Continue the next Groundtruth arc
from the latest committed state.

Work autonomously for as long as the build path remains stable. Do not stop
after one checkpoint. Continue through multiple data, pipeline, and UI
checkpoints when they are unblocked. Commit and push each green checkpoint when
working an autonomous arc. Treat source and application choices already
documented in the approved architecture/tasks/handoff as standing approval.
Stop only for a real blocker, genuinely missing information from the user, a
conflict with the source-of-truth docs, or a point where the next meaningful
work requires new product/design direction that cannot be inferred responsibly.
```
