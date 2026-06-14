# Codex Handoff

Generated: 2026-06-14, America/New_York.

## 1. Project Goal

Groundtruth is a geospatial home-search platform with two linked products on one deterministic data backbone:

- Listing Explorer (`/explore`): shows frozen PA and Hudson Valley listings with school-district assignment verified by PostGIS point-in-polygon joins against official NCES polygons.
- Discovery Engine (`/discover`): will help users decide where to search from budget and lifestyle constraints using regional metrics such as canopy, light pollution, risk, walkability, taxes, and home values.

Hard constraints from `AGENTS.md` remain active: no LLM/ZIP/deductive district assignment, no new RentCast calls or listing expansion, no GreatSchools data, financial math in code/tests only, EPSG:4326 stored geometry, and staging -> validate -> explicit promote for pipeline loads.

## 2. Current Phase Or Feature Area

Current work spans:

- Phase 4: Pipeline harness + region scaffolding.
- Phase 5: First enrichment layer, `canopy_height_m`, only.

Phase 0-3 were already complete on `main` at commit `360bc45 Phase 3 live Neon Explorer API`.

Phase 4 is effectively implemented and replayed against Neon. Phase 5 has started and the first approved layer, `canopy_height_m`, has been staged, QA-rendered, promoted, and validated against Neon. Do not start additional Phase 5 layers without following the manifest + sample-stats + human approval rule.

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

Latest full Neon-backed pipeline test run passed:

```text
17 passed in 3.68s
```

## 4. Recently Changed Files And Why

Tracked modified files:

- `pipeline/gt/cli.py`: added region/layer manifest validation commands, real `gt region add`, layer runner wiring, QA map routing, and report-gated promote logic.
- `pipeline/gt/recovery/load_frozen.py`: repointed stale recovery read path from deleted `app/public/data/listings.geojson` to `data/processed/listings.geojson`.
- `pipeline/tests/test_cli.py`: added CLI tests for manifest validation, layer manifest validation, DB-required region add behavior, and layer grain validation.
- `pipeline/tests/test_golden.py`: repointed stale GeoJSON path and made the frozen-GeoJSON representation test tolerate the current checkout's 3-row local sample while still asserting the DB has 4,505 distinct `source_id`s.
- `sql/migrations/001_unify_schema.sql`: made the `district_metrics` view recreation tolerant of an existing materialized view so migrations can be replayed idempotently after Phase 4.

New untracked files/directories:

- `sql/migrations/002_phase4_region_harness.sql`: staging tables for region scaffolding and materialized `district_metrics`.
- `sql/migrations/003_layer_staging.sql`: generic staging tables for layer region/listing metrics.
- `pipeline/gt/manifests/`: pydantic manifest models/loaders.
- `pipeline/gt/reports.py`: JSON validation report helper.
- `pipeline/gt/region.py`: region staging/promote/validation/QA implementation.
- `pipeline/gt/layers/`: canopy layer implementation and generic layer promote/QA helpers.
- `pipeline/manifests/regions/`: seed region manifests.
- `pipeline/manifests/layers/canopy_height_m.yaml`: approved canopy manifest.
- `docs/layer-onboarding/canopy_height_m.md`: source approval/sample-stats note.
- `docs/CODEX_HANDOFF.md`: this handoff.

Gitignored/generated local files also changed or were created under `data/`, including raw TIGER downloads, validation JSON reports, and QA PNGs. `app/.env.local` already contained the Neon `DATABASE_URL`; do not commit it.

## 5. Current Branch / Worktree Status

- Branch: `main`
- Worktree: `/Users/katherine/Dropbox/school-district-home-search`
- `git worktree list` shows this single worktree at commit `360bc45`.
- Status before this handoff file: `main...origin/main` with uncommitted Phase 4 + `canopy_height_m` changes.
- No commit has been made for this work yet.

Important status note: `git diff --stat` only shows tracked-file modifications and does not include the many new untracked files listed above. Use `git status --short` before committing.

## 6. Known Issues, Failing Checks, Or Unfinished Work

Known caveats:

- `uv` is not available in this shell; commands were run through the existing `pipeline/.venv` instead.
- `data/processed/listings.geojson` in this checkout is a 3-row sample, not the full frozen 4,505 listing dataset. The full frozen dataset is in Neon and is validated by the golden tests.
- The `canopy_height_m` source native resolution is about 1.2 m, but the current POC reducer uses a 4096 x 4096 overview grid per zoom-10 tile, roughly 9.6 m working resolution, for practical remote COG reads. This is recorded in the manifest and metric notes. It is appropriate for tract means and 100 m listing buffers, but not a final house-to-house pixel-level QA pass.
- Phase 5 acceptance asks for QA showing visible house-to-house variation for `canopy_height_m`. The current promoted data includes listing point and 100 m buffer values, but only tract-level QA PNGs have been rendered. A listing-level/known-street QA artifact is still recommended before calling the entire `canopy_height_m` layer fully polished.
- GeoPandas emits warnings about direct psycopg connections not being SQLAlchemy connectables. These are warnings, not failures.
- README is stale relative to the current architecture; it still describes the older static GeoJSON prototype.
- Phase 5 is not complete. Only `canopy_height_m` is implemented/promoted. Remaining Phase 5 layers are `tree_canopy_pct`, `light_pollution_radiance`, `risk_index`, `walkability_index`, and `flood_sfha`, plus the Explorer listing detail panel/environmental filters.
- GVI/perceived green is not part of Phase 5. Per spec, `gvi_ndvi_street` is Phase 8 and Mapillary/segmentation `gvi_streetlevel` is Phase 11.

Checks last run:

- Neon-backed pipeline suite: `17 passed`.
- Neon listing truth validated during the run:
  - 4,505 listings
  - 0 missing districts
  - 4,254 NY
  - 251 PA
- No app frontend build/test was run after the pipeline work because no frontend files were changed.

## 7. Recommended Next Steps

1. Review the uncommitted changes and generated QA PNGs.
2. Optionally run a focused listing-level canopy QA:
   - Pick one leafy vs. bare street/listing pair.
   - Query `listing_metrics` for `canopy_height_m` `point` and `buffer_100m`.
   - Render a small map or report to satisfy the Phase 5 house-to-house variation acceptance detail.
3. If satisfied, make a checkpoint commit for Phase 4 + first Phase 5 canopy layer.
4. Continue Phase 5 one layer at a time. Next likely layer: `tree_canopy_pct` (NLCD TCC) or another clean tract/listing source, but follow the process rule:
   - draft manifest + sample stats,
   - stop for human approval,
   - then write/run/promote ingestion module.
5. Defer Discovery UI until enough metrics and Phase 6 finance/tax layers exist.
6. Consider updating `README.md` in a separate cleanup commit so public project docs match the new Neon/PostGIS pipeline architecture.

## 8. Assumptions And Uncertainty

- Assumed `app/.env.local` points to the intended Neon database; this was confirmed by listing counts and passing golden tests.
- Assumed CHMv2 2026 is the right successor to the Meta/WRI canopy source named in the original spec. The source was approved by the user before implementation.
- Region scaffolding currently handles tract -> district and tract -> municipality overlaps. ZCTA -> district housing-unit overlaps are mentioned in Phase 4 but not implemented yet; this will matter for `median_home_value` in Phase 6.
- The canopy implementation reads public WRI/Meta COGs remotely rather than caching full tiles locally. It works, but future layers may need explicit local caching for speed or reproducibility.
- Data/report artifacts under `data/` are gitignored. They exist locally and were used for QA, but they will not be part of a normal commit unless the ignore policy changes.

## 9. Suggested Prompt For Next Codex Chat

```text
Continue Groundtruth Home Search App work in /Users/katherine/Dropbox/school-district-home-search.

First read AGENTS.md, docs/tasks.md, docs/architecture-spec.md, docs/agentic-pipeline-plan.md, and docs/CODEX_HANDOFF.md.

Do not redo Phase 3. Current uncommitted work contains Phase 4 pipeline harness/region scaffolding and the first Phase 5 layer, canopy_height_m. Preserve the hard rules: deterministic district truth via PostGIS only, RentCast frozen, no GreatSchools, all geometry EPSG:4326, staging -> validate -> explicit promote.

Start by inspecting git status, the uncommitted files, and the latest Neon-backed validation/test state. app/.env.local contains the Neon DATABASE_URL; do not print or commit secrets.

Before new feature work, decide whether the current state is ready for a checkpoint commit. If continuing Phase 5, first complete/review a listing-level canopy QA artifact for house-to-house variation, then proceed one layer at a time using the manifest + sample-stats + human approval rule. Do not start GVI yet; gvi_ndvi_street is Phase 8 and Mapillary GVI is Phase 11.
```
