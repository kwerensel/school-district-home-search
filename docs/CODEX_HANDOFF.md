# Codex Handoff

Generated: 2026-06-20, America/New_York.

## 1. Project Goal

Groundtruth is a geospatial home-search platform with two linked products on one deterministic data backbone:

- Listing Explorer (`/explore`): shows frozen PA and Hudson Valley listings with school-district assignment verified by PostGIS point-in-polygon joins against official NCES polygons.
- Discovery Engine (`/discover`): will help users decide where to search from budget and lifestyle constraints using regional metrics such as canopy, light pollution, risk, walkability, taxes, and home values.

Hard constraints from `AGENTS.md` remain active: no LLM/ZIP/deductive district assignment, no new RentCast calls or listing expansion, no GreatSchools data, financial math in code/tests only, EPSG:4326 stored geometry, and staging -> validate -> explicit promote for pipeline loads.

## 2. Current Phase Or Feature Area

Current work is in Phase 5, first clean enrichment layers.

Completed checkpoints:

- Phase 0-3 were already complete on `main` at commit `360bc45 Phase 3 live Neon Explorer API`.
- Phase 4 and promoted `canopy_height_m` were committed on `main` at commit `a59ed76 Phase 4 harness and canopy height layer`.
- `tree_canopy_pct` source onboarding was committed on `main` at commit `125a85d Draft tree canopy layer onboarding`.
- `tree_canopy_pct` implementation, staging run, validation, and QA map generation were committed and pushed on `main` at commit `133a59b Implement tree canopy layer staging`.
- `tree_canopy_pct` was promoted to Neon for both `pa-mainline` and `hudson-valley` after explicit human approval in the follow-up session.
- `risk_index` source onboarding was approved, implemented, staged for both regions, validated as promotable, QA maps were rendered, and it was promoted to Neon after explicit human approval.
- `light_pollution_radiance` source onboarding was drafted and committed, but ingestion is blocked pending EOG-authenticated exact file verification and numeric sample stats.
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
  `617f0ab Draft effective tax rate onboarding`. Table metadata is verified
  against official ACS 2024 5-year endpoints, but row-level sample stats are
  blocked because the Census API returned `Missing Key` for county-subdivision
  data requests in this environment.
- Phase 6 pure finance engine was implemented and pushed at
  `816b127 Add purchasing power finance engine`: closed-form purchasing power,
  credit-band spreads, PMI, insurance, optional DTI ceiling, and unit tests.

Standing approval model: source and application choices already documented in
the approved architecture/tasks/handoff count as approved. Do not stop for
routine yes/no source or promotion approval when validation is green; preserve
staging -> validate -> explicit promote and keep moving. Stop only for genuinely
missing information, surprising/red validation, a source-of-truth conflict, or a
new unapproved source/provider/paid integration. `light_pollution_radiance`
remains blocked and GVI must not start.

Do not start GVI. `gvi_ndvi_street` is Phase 8 and Mapillary/segmentation GVI is Phase 11.

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
- This layer is intentionally stopped before ingestion. The official EOG V2.2
  directory redirects to EOG sign-in from this environment, so exact latest-year
  filename verification and numeric raster sample stats require authenticated
  access or an approved local source file.
- Do not stage or promote this layer until the source blocker is resolved and
  approved.

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

Uncommitted in the current worktree:

- `pipeline/gt/layers/flood_sfha.py`: fixes `NaN` tract shares by coercing
  zero-overlap/degenerate tract reductions to finite `0.0`, clamps shares to
  the manifest range, and makes the validation report fail promotion if staged
  tract or listing values are non-finite.
- `docs/CODEX_HANDOFF.md`: records the repaired flood promotion checkpoint and
  latest verification results.

Recently committed:

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
- Current local commit: `816b127 Add purchasing power finance engine`
- `main` is even with `origin/main` at that commit before this handoff edit.
- Worktree has this uncommitted `docs/CODEX_HANDOFF.md` update.

## 6. Known Issues, Failing Checks, Or Unfinished Work

Known caveats:

- `uv` is not available in this shell; commands were run through the existing `pipeline/.venv` instead.
- `data/processed/listings.geojson` in this checkout is a 3-row sample, not the full frozen 4,505 listing dataset. The full frozen dataset is in Neon and is validated by the golden tests.
- The `canopy_height_m` source native resolution is about 1.2 m, but the current POC reducer uses a 4096 x 4096 overview grid per zoom-10 tile, roughly 9.6 m working resolution, for practical remote COG reads. This is recorded in the manifest and metric notes. It is appropriate for tract means and 100 m listing buffers, but not a final house-to-house pixel-level QA pass.
- The `tree_canopy_pct` reducer reads the public NLCD TCC ZIP-backed GeoTIFF remotely rather than caching the full 3.6 GB archive locally.
- GeoPandas emits warnings about direct psycopg connections not being SQLAlchemy connectables. These are warnings, not failures.
- README is stale relative to the current architecture; it still describes the older static GeoJSON prototype.
- Phase 5 is not complete. Completed/promoted: `canopy_height_m`, `tree_canopy_pct`, `risk_index`, `walkability_index`, and `flood_sfha`. Explorer listing metrics panel/environmental filters are implemented. Blocked on source access: `light_pollution_radiance`. Remaining Phase 5 app work is follow-up polish/QA on the Explorer metrics surface and any missing environmental dimensions after blocked light pollution is resolved.
- `light_pollution_radiance` source onboarding is intentionally stopped before ingestion. The official EOG V2.2 download directory redirects to EOG sign-in from this environment, so exact filename/latest-year verification and numeric raster sample stats are pending authenticated source access or an approved local source file.
- `effective_tax_rate` source onboarding is intentionally stopped before
  ingestion. ACS table metadata endpoints are reachable, but the row-level
  county-subdivision Census API request returned `Missing Key`; implementation
  needs either a Census API key in the local environment or an approved
  official ACS bulk-file workflow.
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
- Finance/app tests passed after adding the finance engine with `npm test`:
  `2 passed`, `11 tests passed`.
- App lint passed after adding the finance engine with `npm run lint`: 0
  errors, 6 pre-existing shadcn fast-refresh warnings.
- App production build passed with `npm run build` after the finance engine
  change.
- `light_pollution_radiance` manifest validation passed with `./.venv/bin/gt manifest validate layer manifests/layers/light_pollution_radiance.yaml`.
- A one-off `curl -I` probe against a likely EOG V2.2 2024 median-masked file returned an authentication redirect, not downloadable file metadata.
- No app frontend build/test was run after the pipeline work because no frontend files were changed.

## 7. Recommended Next Steps

Recommended next chat boundary: optional. This is a clean checkpoint:
`flood_sfha` is promoted and verified after repair. A fresh chat is not
required if continuing immediately.

Next actions, in order:

1. Commit and push this handoff update.
2. Continue Phase 5 app polish/QA when browser access is available: visually inspect the Explorer metrics panel
   in a browser, verify marker selection and mobile panel behavior, and tune
   any copy/layout issues found.
3. Resolve blocked source/data access:
   - `light_pollution_radiance`: EOG-authenticated exact file verification and
     numeric sample stats.
   - `effective_tax_rate`: Census API key or official ACS bulk-file workflow
     for county-subdivision row data and sample stats.
   - `median_home_value`: restore/fetch the ZHVI ZCTA CSV and implement the
     missing ZCTA -> district housing-unit crosswalk before layer ingestion.
4. Next unblocked code path after source access is resolved: implement
   `effective_tax_rate`, then wire `computePurchasingPower` to live tax/home
   value data.
5. Do not start GVI.

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
- Region scaffolding currently handles tract -> district and tract -> municipality overlaps. ZCTA -> district housing-unit overlaps are mentioned in Phase 4 but not implemented yet; this will matter for `median_home_value` in Phase 6.
- Data/report artifacts under `data/` are gitignored. They exist locally and were used for QA, but they will not be part of a normal commit unless the ignore policy changes.
- `tree_canopy_pct` is promoted to public/live metric tables. Staging rows may still exist as the last staged source of truth for the promote reports.
- `risk_index` is promoted to public/live metric tables. Staging rows may still exist as the last staged source of truth for the promote reports.
- `walkability_index` is promoted to public/live metric tables. Staging rows may still exist as the last staged source of truth for the promote reports.
- `light_pollution_radiance` manifest uses draft vintage `2024`. This should be updated before implementation if EOG-authenticated listing shows a newer complete annual V2.2 median-masked product.
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
