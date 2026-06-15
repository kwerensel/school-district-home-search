# Codex Handoff

Generated: 2026-06-15, America/New_York.

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

Important current gate: `risk_index` is now promoted. The next Phase 5 action is to onboard the next clean source; do not start GVI.

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

## 4. Recently Changed Files And Why

Recently committed:

- `6f7dc2b Update handoff after tree canopy promote`: documentation-only handoff update after `tree_canopy_pct` promotion and verification.

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
- Current local commit before this handoff update: `42d9b30 Implement risk index layer staging`
- `main` is ahead of `origin/main` by at least 1 local commit unless pushed.
- Worktree has this handoff edit until committed.

## 6. Known Issues, Failing Checks, Or Unfinished Work

Known caveats:

- `uv` is not available in this shell; commands were run through the existing `pipeline/.venv` instead.
- `data/processed/listings.geojson` in this checkout is a 3-row sample, not the full frozen 4,505 listing dataset. The full frozen dataset is in Neon and is validated by the golden tests.
- The `canopy_height_m` source native resolution is about 1.2 m, but the current POC reducer uses a 4096 x 4096 overview grid per zoom-10 tile, roughly 9.6 m working resolution, for practical remote COG reads. This is recorded in the manifest and metric notes. It is appropriate for tract means and 100 m listing buffers, but not a final house-to-house pixel-level QA pass.
- The `tree_canopy_pct` reducer reads the public NLCD TCC ZIP-backed GeoTIFF remotely rather than caching the full 3.6 GB archive locally.
- GeoPandas emits warnings about direct psycopg connections not being SQLAlchemy connectables. These are warnings, not failures.
- README is stale relative to the current architecture; it still describes the older static GeoJSON prototype.
- Phase 5 is not complete. Completed/promoted: `canopy_height_m`, `tree_canopy_pct`, and `risk_index`. Remaining Phase 5 layers are `light_pollution_radiance`, `walkability_index`, and `flood_sfha`, plus the Explorer listing detail panel/environmental filters.
- GVI/perceived green is not part of Phase 5. Per spec, `gvi_ndvi_street` is Phase 8 and Mapillary/segmentation `gvi_streetlevel` is Phase 11.

Checks last run after `risk_index` promote:

- Manifest validation passed for `risk_index`.
- Report validation rechecked both `risk_index` reports; both remain `promotable: true`.
- Full Neon-backed pipeline suite: `21 passed` on 2026-06-15.
- Golden Neon checks passed:
  - 4,505 listings
  - 0 missing districts
  - pinned PA/NY address -> district facts
  - nearest fallback count/cap
  - SRID and geometry validity checks
- Public metric counts and `district_metrics` rollups confirmed after promote.
- No app frontend build/test was run after the pipeline work because no frontend files were changed.

## 7. Recommended Next Steps

Recommended next chat boundary: start a fresh chat now. This is a clean checkpoint: `risk_index` is promoted and verified; the next action changes mode to onboarding the next Phase 5 source.

Next actions, in order:

1. Choose the next Phase 5 layer onboarding target. Recommended next target: `light_pollution_radiance`, because it is a core Discovery context metric and exercises the raster/neighborhood-context pattern.
2. Draft the `light_pollution_radiance` layer manifest plus sample-stats summary, then stop for human approval before implementing ingestion.
3. Keep `walkability_index` and `flood_sfha` queued after `light_pollution_radiance`.
4. Do not start GVI.

## 8. Standing Chat-Continuity Instruction

At the end of each substantial chat, Codex should recommend whether to start a new chat. Recommend a new chat when any of these checkpoints is reached:

- A commit has been pushed.
- A data layer reaches a gate: onboarding approval packet, staged/validated/QA-rendered, promoted, or rejected.
- A phase gate in `docs/tasks.md` passes.
- The conversation has accumulated enough tool output that a fresh context would reduce risk.
- The next step changes mode, for example from implementation to human QA, from QA to promotion, or from one data source to another.

When recommending a new chat, Codex should update `docs/CODEX_HANDOFF.md` before closing the session with:

- Current branch, latest commit, and worktree status.
- What changed and why.
- Validation/test results.
- Data staging/promotion status.
- Remaining gates and explicit "do not do" constraints.
- A copy-paste opening prompt for the next chat.

## 9. Assumptions And Uncertainty

- Assumed `app/.env.local` points to the intended Neon database; this was confirmed by listing counts and passing golden tests.
- Region scaffolding currently handles tract -> district and tract -> municipality overlaps. ZCTA -> district housing-unit overlaps are mentioned in Phase 4 but not implemented yet; this will matter for `median_home_value` in Phase 6.
- Data/report artifacts under `data/` are gitignored. They exist locally and were used for QA, but they will not be part of a normal commit unless the ignore policy changes.
- `tree_canopy_pct` is promoted to public/live metric tables. Staging rows may still exist as the last staged source of truth for the promote reports.
- `risk_index` is promoted to public/live metric tables. Staging rows may still exist as the last staged source of truth for the promote reports.

## 10. Suggested Prompt For Next Codex Chat

```text
Continue Groundtruth Home Search App work in /Users/katherine/Dropbox/school-district-home-search.

First read AGENTS.md, docs/tasks.md, docs/architecture-spec.md,
docs/agentic-pipeline-plan.md, and docs/CODEX_HANDOFF.md.

Do not redo Phase 3. Phase 4 and canopy_height_m are complete. Do not start
GVI. Preserve hard rules: deterministic district truth via PostGIS only,
RentCast frozen, no GreatSchools, all geometry EPSG:4326, staging -> validate
-> explicit promote.

Current checkpoint: risk_index was implemented from the approved FEMA/RAPT NRI
onboarding packet, staged for both pa-mainline and hudson-valley at tract grain,
validated as promotable, QA maps were rendered, then it was explicitly approved
and promoted to Neon public metric tables.
app/.env.local contains the Neon DATABASE_URL; do not print or commit secrets.

First inspect git status and latest validation state. Then start the next Phase
5 source onboarding packet. Recommended target: light_pollution_radiance because
it is a core Discovery context metric and exercises the next raster/neighborhood
context pattern. Draft the layer manifest plus sample-stats summary and stop
for human approval before writing the full ingestion module. Do not start GVI.
```
