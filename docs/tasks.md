# Groundtruth — Implementation Tasks

Ordered phases for Claude Code. Each task has acceptance criteria (AC). Don't start a phase until the previous phase's gate passes. References: `docs/architecture-spec.md` (§ numbers below) and `CLAUDE.md` hard rules.

---

## Phase 0 — Repo hygiene

**0.1 Restructure.** Create `pipeline/` as a uv-managed Python package with a Typer CLI stub (`gt --help` works). Move existing `scripts/*.py` into `pipeline/gt/legacy/` (keep runnable; they document the original pipeline). Add `pyproject.toml` with: geopandas, rasterio, rasterstats, osmnx, shapely, typer, pydantic, psycopg, matplotlib, contextily, pytest.
**0.2 Data hygiene.** Gitignore `data/` (keep `data/processed/*.geojson` until Phase 3 gate). Remove the 120 MB ZHVI CSV from git history is *optional*; at minimum stop tracking it and add `gt fetch zhvi` to re-download. Move `docs/chat-history-*.txt` out of the repo.
**0.3 App cleanup.** Remove `mapbox-gl` and `@types/mapbox-gl` deps (Leaflet is the map). Add `app/src/server/db.ts` placeholder. Add vitest.
**AC:** `uv run gt --help` and `npm run build` both succeed; `git status` clean; repo < 10 MB without data.

## Phase 1 — Schema unification (local PostGIS)

**1.1 Migration `001_unify_schema.sql`** per spec §3.2: `school_districts` (merge `pa_school_districts` + `ny_school_districts`, transform 3857→4326, `ST_MakeValid`, normalize display names with the existing suffix rules, preserve `name_raw`), `listings` (union PA `listings_map_ready` — casting the varchar price/beds/baths — and HV `hv_listings_map_ready` + raw-table columns; `region_slug` = `pa-mainline` / `hudson-valley`), re-run the assignment join, port `good_school_districts` into a `district_quality` placeholder metric.
**1.2 Golden tests.** `pipeline/tests/test_golden.py`: total listings = 4,505 ± documented delta; ≥ 3 pinned address→district facts per region (pick from current data); all `assignment_method='nearest'` rows have `assignment_dist_m ≤ 500` and count = 4; every geometry SRID = 4326 and valid.
**1.3 Migration runner.** `gt db migrate` applies `sql/migrations/` in order, idempotently, against `$DATABASE_URL`.
**AC:** `uv run pytest -k golden` passes; old tables intact (migration is additive); a diff report shows every old-table listing represented exactly once in `listings`.

## Phase 2 — Neon

**2.1** Create Neon project, enable PostGIS, run migrations, load `school_districts` + `listings` (+`district_quality`) via `gt promote --target neon`.
**2.2** Golden tests runnable against Neon (`DATABASE_URL` switch).
**AC:** golden suite green against Neon; query `SELECT count(*) FROM listings WHERE district_id IS NULL` = 0.

## Phase 3 — Live API + frontend swap

**3.1** `getListings` + `getDistricts` server functions per spec §2 (zod inputs, SQL-built GeoJSON, zoom-mapped `ST_SimplifyPreserveTopology`, cache headers). Use `@neondatabase/serverless`.
**3.2** Swap `HousingSearch` to TanStack Query + server functions; keep `filters.ts` client filtering. District polygons rendered with `good_district` styling parity.
**3.3 Parity gate:** screenshot/behavior comparison vs. static version — same markers, popups, filters, district overlay, for both PA and HV viewports. Then delete `app/public/data/*.geojson` and the static fetch path.
**AC:** app runs with zero static GeoJSON; cold load < 3 s on dev; vitest covers both server functions (mocked sql).

## Phase 4 — Pipeline harness + region scaffolding

**4.1** Manifests: pydantic models for `manifests/regions/*.yaml` and `manifests/layers/*.yaml` (source URLs, vintage, allowed value range, reduction method, coverage threshold). Write `hudson-valley.yaml` and `pa-mainline.yaml`.
**4.2** `gt region add`: TIGER tracts + county subdivisions + places for manifest counties → `regions` rows (tract/municipality types); NCES districts → district-type `regions` linked to `school_districts`; compute `region_overlaps` (tract↔district, tract↔municipality by area; ZCTA↔district by ACS housing units). Staging-first.
**4.3** Harness: `gt validate` (re-runs report checks), `gt promote` (refuses on failed report), `gt qa map` (PNG choropleth of any metric or geometry set via matplotlib+contextily), JSON report writer per spec format. Layer runner supports `--grain tract|listing|both` (default `both` for environmental layers); listing-grain reductions: point sample, 100 m / 500 m buffer zonal stats, point-in-polygon flag, distance-to-nearest.
**4.4** `district_metrics` materialized view with the §3.3 rollup rule + refresh in `gt promote`.
**AC:** both regions scaffolded; `SELECT region_type, count(*) FROM regions GROUP BY 1` matches TIGER counts; overlap weights per tract sum to 1.0 ± 0.01 against districts; QA PNG of tract boundaries over district boundaries reviewed and committed to `data/reports/qa/` (path gitignored — reviewed locally).

## Phase 5 — First six layers (clean sources)

For each of `canopy_height_m` (Meta/WRI 1 m canopy height — **the street-level green headline; do this one first**), `tree_canopy_pct` (NLCD TCC), `light_pollution_radiance` (VIIRS VNL V2), `risk_index` (FEMA NRI, tract-native join), `walkability_index` (EPA NWI, block-group → housing-unit-weighted tract), `flood_sfha` (FEMA NFHL): layer module + manifest + run for both regions **at both grains where the source's native resolution permits (per spec §3.3 honesty rule)** + QA PNG + promote. Register all in `metric_definitions` with source/vintage/direction/native_resolution.
**Process rule (CLAUDE.md):** draft manifest + sample stats → human approval → full module.
**5.x Listing detail panel.** `getListingMetrics` server function + Explorer detail panel replacing the bare popup: environmental metrics grouped by grain, neighborhood-context metrics (VIIRS, AQI) visually distinguished from street-level ones; environmental dimensions added to `filters.ts` (min canopy height, flood flag).
**AC per layer:** report `promotable: true`; tract coverage ≥ 99%; listing coverage = 4,505/4,505 for listing-grain layers; values inside manifest range; QA PNG approved — for `canopy_height_m`, the QA PNG must show visible house-to-house variation on a known leafy-vs-bare street pair. **Phase gate:** `district_metrics` shows all metrics for every district in both regions; clicking any Explorer listing shows its environmental panel; spot-check three known places (e.g., Manhattan-adjacent Yonkers tracts high radiance; Putnam tracts high canopy).

## Phase 6 — Money: taxes, prices, purchasing power

**6.1** `effective_tax_rate` layer from ACS B25103/B25077 at county-subdivision/place grain → mapped to tracts → district rollup. Sanity anchors: Lower Merion ~1.5–2.5%, typical Westchester ~2–3%+.
**6.2** `median_home_value` from the ZHVI ZCTA file via housing-unit-weighted crosswalk to districts; ZCTAs missing from ZHVI (thin-market/rural gaps) fall back to ACS B25077 median value, recorded as a distinct vintage so provenance stays visible per district.
**6.3** `app/src/lib/finance/`: closed-form P_max per spec §7 (PMMS rate fetch + 24 h cache + fallback constant; credit-band spreads; PMI under 20% down; optional DTI second ceiling with binding-bound label). Exhaustive unit tests incl. the brief's worked example (B=$5,500 ⇒ ordering Hudson Valley > Lower Merion must hold with real tax data).
**6.4** `computePurchasingPower` server function + `RegionChoropleth` Leaflet component shading districts by P_max.
**AC:** finance tests green; choropleth renders for a budget slider with <100 ms recompute; tax metric QA PNG approved.

## Phase 7 — Access layers

`commute_minutes_<anchor>` (ORS matrix from population-weighted tract centroids to manifest anchors; runtime user anchors handled in Phase 10), `transit_access` (Transitland GTFS: tract stop density + per-listing distance-to-nearest-stop), `park_access` (OSM + PAD-US: tract 800 m share + per-listing distance-to-park-edge). Same per-layer AC as Phase 5 including listing coverage.

## Phase 8 — Hard layers

`noise_mean_dba` + `noise_pct_over_45/55` (BTS National Transportation Noise Map per spec §6; ~30 m grid → both grains, listing point + buffer_100m), `noise_sources` (per spec §6: per-listing distances to siren sources / nightlife clusters / industrial land use via OSM + freight rail via FRA; tract source-densities for Discovery; served as labeled distances and flags, never synthesized dB), `aqi_annual_mean` (EPA AQS, IDW ≤ 30 km, county fallback; neighborhood-context grain), `gvi_ndvi_street` (Sentinel-2 summer composite → NDVI → 50 m OSM road buffer mask → tract zonal mean + listing buffer_100m/500m, per spec §5 Phase 1). Add derived metric `green_divergence` = canopy percentile − street-NDVI percentile (SQL view, both grains).
**AC:** standard per-layer AC; for `noise_sources`, a golden check that a known listing near a fire station or freight line carries the expected flag; for GVI additionally a QA PNG pair (canopy vs street-NDVI) demonstrating divergence somewhere visible, and a listing-level spot check: two listings on the same block with visibly different street greenery must show different `buffer_100m` values.

## Phase 9 — Archetypes + narratives

**9.1** `gt archetypes build`: percentile-normalize district × metric matrix, k-means k=4..9 by silhouette, persist versioned assignments per spec §8.
**9.2** `gt archetypes label`: Claude API labels from top-5 distinguishing percentiles; written to a pending state; human approves → live.
**9.3** `discover` server function: filter districts by profile (P_max vs ZHVI, commute caps), score by user weights over metric percentiles, return ranked regions + archetype + structured deltas. Tradeoff narrative endpoint with the numeral post-check guard + template fallback + (regionA, regionB, profile-bucket) cache table.
**AC:** clustering deterministic across runs (fixed seed); guard demonstrably catches an injected hallucinated number in tests; `discover` returns in < 500 ms warm.

## Phase 10 — Discovery UI + handoff

Wizard at `/discover` (budget, optional Level 1–2 fields, ≤ 2 anchors via geocode + ORS at request time, weight sliders), results at `/discover/results` (ranked cards, choropleth, compare drawer with narratives), profile as typed search params per spec §3.4, "See listings" → `/explore?profile=...` applying shortlist polygons + per-region P_max price caps.
**AC:** full journey clickable: budget in → shortlist → Explorer pre-filtered; every wizard state is a shareable URL; works on mobile sheet layout (existing pattern).

## Phase 11 — GVI v2 (research track, non-blocking)

Mapillary-sampled segmentation GVI per spec §5 Phase 2, **anchored to the frozen listing set**: nearest 3–5 road points within 150 m of each listing, image fetch, Cityscapes-class vegetation fraction (SegFormer), per-listing aggregation with `gvi_streetlevel_n_images` companion metric, tract values aggregated from samples, NDVI-proxy fallback labeling where coverage is thin, correlation report vs `gvi_ndvi_street`.
**AC:** methodology writeup in `docs/` with the correlation result — this is portfolio material regardless of the number.

## Phase 12 — Auth & saved profiles (can run any time after Phase 3; favorites need only Phase 3, saved searches need Phase 10)

**12.1** better-auth setup on TanStack Start: email+password, sessions in Neon, its CLI migration plus `sql/migrations/00N_saved_profiles.sql` (tables per spec §3.5 with `ON DELETE CASCADE`). Password reset requires a transactional email sender — use Resend (free tier) via better-auth's email hooks; email *verification* may be disabled for the POC. Enable Dependabot for the repo and add login rate limiting (better-auth built-in) + Cloudflare Turnstile on the signup form.
**12.2** Authenticated server functions: `saveProfile`/`listProfiles`/`deleteProfile`, `toggleFavorite`/`listFavorites` — session checked server-side, user id never accepted from the client, profile jsonb zod-validated on write.
**12.3** UI: `/login`, `/signup`, `/saved`; "Save this search" on Discovery results and favorite-hearts on Explorer listings, both prompting sign-in when signed out and persisting the current URL state after; account menu with delete-account.
**12.4** Sensitive-data guards: no profile contents in logs/error reporters (grep-able test: serialize a profile through the error path and assert budget/credit fields absent); delete-account integration test proves cascade.
**AC:** entire app remains fully usable signed out (URL state canonical — regression-check the Phase 10 journey with no session); save → sign out → sign in → `/saved` → re-open lands on the identical URL; cascade test green.

---

## Standing definition of done (every task)

Code formatted/linted; new behavior covered by a test or a validation check; golden suite green; no new geometry outside EPSG:4326; staging→promote respected for any data change; QA PNG generated for any spatial output.
