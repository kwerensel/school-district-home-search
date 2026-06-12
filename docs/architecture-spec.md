# Groundtruth — Architecture Specification

Status: approved for implementation. Written against the actual repo state (commit on `main`, 2026-06): TanStack Start app on Cloudflare, Leaflet map, local PostGIS with PA (251 listings, SRID-3857 districts) and Hudson Valley (4,254 listings, SRID-3857 districts, corrected numeric types) datasets, static GeoJSON frontend feed.

---

## 1. Backend hosting: Neon

**Decision: Neon serverless Postgres** (free tier initially; Launch plan if limits are hit — within the ~$25/mo budget).

Rationale, in order of weight:

1. **Cloudflare compatibility.** The app deploys to Cloudflare via `@cloudflare/vite-plugin`. Cloudflare Workers can't open raw TCP Postgres connections; Neon's `@neondatabase/serverless` driver speaks HTTP/WebSockets and is designed for exactly this runtime. With Supabase you'd either route through `supabase-js` (a different query model than SQL) or add Cloudflare Hyperdrive. Neon removes the problem.
2. **PostGIS supported** via `CREATE EXTENSION postgis;`. `postgis_raster` is also available on Neon, but per §4 we don't use in-database rasters — all raster layers are reduced to per-tract scalars offline.
3. **The database stays tiny.** ~4.5k listing points, ~1.2k district polygons, a few thousand tract polygons, and long-format metric rows — comfortably inside free-tier storage. Scale-to-zero compute fits a low-traffic POC.
4. **Branching** gives free staging databases: `gt promote` can be tested on a branch before touching main.

Why not Supabase: its headline feature (auto-generated PostgREST API) is redundant — TanStack server functions are already the API layer (one exists today: `getMapboxToken`). You'd be carrying auth/storage/edge-function machinery this project doesn't need. Supabase remains a valid fallback if you later want hosted auth; nothing in this spec precludes switching (it's all plain Postgres + SQL).

Why not self-hosted (Fly/Railway): more ops surface for a solo builder, no meaningful capability gain at this scale.

**Migration path:** `pg_dump` local → `psql $NEON_URL` restore, after the schema-unification migration (§3) runs locally first. Keep local PostGIS as the pipeline's working database; Neon is the serving database. The pipeline promotes to Neon (`gt promote --target neon`). This split means heavy geoprocessing never competes with serving, and the RentCast dataset is preserved in two places.

## 2. Live PostGIS connection: TanStack server functions as the API layer

Replace static `/data/*.geojson` fetches with typed server functions in `app/src/server/`:

```ts
// app/src/server/db.ts
import { neon } from "@neondatabase/serverless";
export const sql = neon(process.env.DATABASE_URL!);
```

Endpoints (all `createServerFn`, all zod-validated inputs):

| Function | Input | Output |
|---|---|---|
| `getListings` | bbox, filters (maxPrice, minBeds, minBaths, goodOnly, districtSlug?) | GeoJSON FeatureCollection (built in SQL via `ST_AsGeoJSON`) |
| `getDistricts` | bbox or state, simplifyTolerance | GeoJSON FC, geometry simplified server-side |
| `getRegions` | regionType, state? | region list with slugs + bbox (no geometry) |
| `getRegionMetrics` | regionSlugs[], metricKeys[]? | long-format rows + metric definitions |
| `getListingMetrics` | listingIds[] | listing-grain environmental metrics (§3.3) for the Explorer detail panel |
| `computePurchasingPower` | profile (see §7) | per-region purchasing power |
| `discover` | full discovery profile | ranked regions + archetype + tradeoff data |
| `saveProfile` / `listProfiles` / `deleteProfile`, `toggleFavorite` / `listFavorites` | session-authenticated (better-auth, §3.5) | CRUD on saved searches and favorited listings |

Implementation notes:

- Build GeoJSON in Postgres: `SELECT json_build_object('type','FeatureCollection','features', json_agg(ST_AsGeoJSON(t.*)::json)) FROM (...) t;`. Never round-trip geometry through JS.
- **Polygon weight control:** districts are served with `ST_SimplifyPreserveTopology(geom, tolerance)` where tolerance maps from zoom (e.g., 0.01° at z≤8, 0.001° at z≤11, 0.0001° above). Tract geometries are never sent to the client at all — only their rolled-up metrics.
- **Caching:** listings are frozen and metrics change only on pipeline runs, so wrap responses with TanStack Query (`staleTime: Infinity` for listings, hours for metrics) and set `Cache-Control: public, max-age=3600` headers. This makes Neon cold starts irrelevant in practice.
- Vector tiles (`ST_AsMVT` / PMTiles) are explicitly **deferred**: at 4.5k points and ~75 visible polygons, simplified GeoJSON is simpler and sufficient. Revisit only if a region exceeds ~50k features.
- Keep the static GeoJSON files in place until `getListings` reaches feature parity (tasks.md Phase 3 gate), then delete them.

## 3. Data model

### 3.1 SRID policy

Everything stored in **EPSG:4326**. The current 3857 district tables were an unnecessary choice (point-in-polygon containment is projection-invariant; ST_Contains works fine in 4326). Migration transforms `pa_school_districts` / `ny_school_districts` into the unified table below. Metric distances use `geom::geography`.

### 3.2 Core tables (migration `001_unify_schema.sql`)

```sql
-- Districts: one national-pattern table replaces pa_/ny_ pair
CREATE TABLE school_districts (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nces_geoid    text UNIQUE NOT NULL,          -- NCES EDGE GEOID
  name_raw      text NOT NULL,                 -- full NCES name
  name_display  text NOT NULL,                 -- suffix-stripped (existing normalization rules)
  state         text NOT NULL,                 -- 'PA', 'NY', ...
  school_year   text NOT NULL,                 -- 'SY2223'
  geom          geometry(MultiPolygon, 4326) NOT NULL
                CHECK (ST_IsValid(geom))       -- ST_MakeValid applied at import
);
CREATE INDEX ON school_districts USING gist (geom);

-- Listings: unified PA + HV, frozen dataset, correct types
CREATE TABLE listings (
  id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_id          text,                     -- RentCast id (null for PA CSV rows)
  source             text NOT NULL DEFAULT 'rentcast',
  region_slug        text NOT NULL,            -- 'pa-mainline', 'hudson-valley'
  address            text, city text, state text, zip text, county text,
  price              integer,
  beds               integer,
  baths              double precision,
  property_type      text, square_footage integer, year_built integer,
  url                text,                     -- null for all rows (RentCast plan limitation)
  listed_date        date, days_on_market integer, status text,
  district_id        bigint REFERENCES school_districts(id),
  assignment_method  text NOT NULL CHECK (assignment_method IN ('within','nearest')),
  assignment_dist_m  double precision,         -- 0 for 'within'; ≤300 observed for 'nearest'
  geom               geometry(Point, 4326) NOT NULL,
  UNIQUE (source, source_id)
);
CREATE INDEX ON listings USING gist (geom);
CREATE INDEX ON listings (district_id);
```

The assignment join (deterministic layer — this exact pattern, already validated in the HV run):

```sql
UPDATE listings l SET district_id = d.id, assignment_method = 'within', assignment_dist_m = 0
FROM school_districts d WHERE ST_Contains(d.geom, l.geom);
-- fallback for waterfront points only, capped at 500 m:
-- nearest district via ORDER BY d.geom <-> l.geom LIMIT 1, method = 'nearest'
```

### 3.3 Regions and metrics (the Discovery Engine spine)

Compute grain = **census tract**; presentation grain = **school district** (primary) and **municipality** (label/secondary). Rationale: nearly every enrichment source ships at or crosswalks to tract level; districts are the product's spine but are sometimes too large/heterogeneous to be one "place".

```sql
CREATE TYPE region_type AS ENUM ('school_district','municipality','census_tract','county','zcta');

CREATE TABLE regions (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  region_type region_type NOT NULL,
  slug        text UNIQUE NOT NULL,            -- 'sd-lower-merion-pa', 'tract-42045401501'
  name        text NOT NULL,
  state       text NOT NULL,
  source_id   text,                            -- GEOID / nces_geoid / place FIPS
  district_id bigint REFERENCES school_districts(id),  -- set when region_type='school_district'
  geom        geometry(MultiPolygon, 4326) NOT NULL CHECK (ST_IsValid(geom)),
  region_group text                             -- 'hudson-valley', 'pa-mainline' (manifest slug)
);
CREATE INDEX ON regions USING gist (geom);
CREATE INDEX ON regions (region_type, state);

-- Area-weighted relationships: tract → district, tract → municipality
CREATE TABLE region_overlaps (
  child_region_id  bigint REFERENCES regions(id),   -- tract
  parent_region_id bigint REFERENCES regions(id),   -- district or municipality
  area_weight      double precision NOT NULL,       -- fraction of child area inside parent
  PRIMARY KEY (child_region_id, parent_region_id)
);

CREATE TABLE metric_definitions (
  metric_key  text PRIMARY KEY,                -- 'light_pollution_radiance', 'gvi_ndvi_street'
  name        text NOT NULL,
  units       text,
  direction   text CHECK (direction IN ('higher_better','lower_better','neutral')),
  source      text NOT NULL,                   -- dataset + vintage description
  grain       region_type NOT NULL,            -- native grain it's computed at
  notes       text
);

CREATE TABLE region_metrics (
  region_id   bigint REFERENCES regions(id),
  metric_key  text REFERENCES metric_definitions(metric_key),
  value       double precision NOT NULL,
  vintage     text NOT NULL,                   -- '2023', '2024-annual'
  computed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (region_id, metric_key, vintage)
);
```

**Rollup rule** (materialized view `district_metrics`): district value = Σ(tract value × area_weight × tract_area) / Σ(area_weight × tract_area), per metric, except metrics flagged in `metric_definitions.notes` as count-like (summed) or threshold-like (area-weighted share). Median home prices arrive at ZCTA grain (Zillow ZHVI — already in `data/raw/`) and crosswalk to districts via ZCTA↔district `region_overlaps` weighted by ZCTA housing-unit counts (ACS), not raw area.

**Dual-grain principle.** Environmental and sensory layers are computed at *two* grains from the same source data: **listing grain** for the Explorer ("what is it like to live at this address / on this street") and **tract grain** for the Discovery Engine (regional averages and tradeoffs). The listing set is frozen at ~4,505 points, so listing-grain computation is cheap — a point sample plus small-buffer zonal stats per listing. Buffer semantics: `point` = value at the address; `buffer_100m` ≈ the immediate street; `buffer_500m` ≈ the walkable surroundings.

```sql
CREATE TABLE listing_metrics (
  listing_id  bigint REFERENCES listings(id),
  metric_key  text REFERENCES metric_definitions(metric_key),
  grain       text NOT NULL CHECK (grain IN ('point','buffer_100m','buffer_500m')),
  value       double precision NOT NULL,
  vintage     text NOT NULL,
  computed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (listing_id, metric_key, grain, vintage)
);
```

`metric_definitions` gains a `native_resolution` column (e.g., `'10m'`, `'30m'`, `'~500m'`, `'monitor-network'`). **Honesty rule:** a metric is only served at listing grain if its native resolution supports it (≤ ~30 m, or exact polygons like FEMA NFHL). Coarser sources (VIIRS light pollution, air quality) are attached to listings as *neighborhood context* — same value for nearby listings — and the UI labels them as such rather than implying address-level precision.

Staging schema: every pipeline load writes to `staging.<table>`; `gt promote` swaps/upserts into `public` after validation passes.

### 3.4 The Discovery → Explorer handoff

Stateless for the POC: the discovery profile is a zod-validated, URL-serializable object carried in TanStack Router typed search params.

```ts
const DiscoveryProfile = z.object({
  monthlyBudget: z.number(),                       // Level 0
  downPayment: z.number().optional(),              // Level 1 ($ amount, replaces 20% default)
  creditBand: z.enum(["excellent","good","fair"]).optional(),  // Level 2
  monthlyDebts: z.number().optional(),             // Level 2
  anchors: z.array(z.object({ label: z.string(), lat: z.number(), lng: z.number(),
                              maxMinutes: z.number() })).max(2),
  weights: z.record(z.string(), z.number()),       // metric_key → importance 0–1
  shortlist: z.array(z.string()).optional(),       // region slugs chosen on results page
});
```

`/explore?profile=<encoded>` pre-filters the map to shortlisted regions, draws their district polygons, and re-applies the budget as a price filter (purchasing-power-derived max price per region). The URL *is* the working state — Discovery and Explorer are fully usable with no account.

### 3.5 Auth & saved profiles (accounts as a save layer, never a gate)

**Stack: better-auth** on TanStack Start, sessions and users stored in Neon — chosen specifically so user data lives in our own Postgres (it's part of the product's moat), not a per-MAU hosted vendor. Email+password at launch; OAuth providers are config additions later. better-auth generates its own tables (`user`, `session`, `account`, `verification`) via its CLI migration.

App tables on top:

```sql
CREATE TABLE saved_profiles (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id    text NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  name       text NOT NULL,                  -- "Spring 2027 search"
  profile    jsonb NOT NULL,                 -- the DiscoveryProfile object, zod-validated on write
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE favorites (
  user_id    text NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  listing_id bigint NOT NULL REFERENCES listings(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, listing_id)
);
```

Rules: signed-out users lose nothing (URL state is canonical; "Save this search" prompts sign-in and then persists the current URL profile); every authenticated server function checks the session server-side, never trusts a client-supplied user id; **profile contents are sensitive financial data** (budget, down payment, credit band) — never write them to logs or error reports, and `ON DELETE CASCADE` makes account deletion real deletion. This section is additive: nothing elsewhere in the spec depends on a user existing.

## 4. Enrichment ingestion architecture

One pattern for all layers: **fetch → process → reduce-to-tract → validate → load(staging) → promote.** Each layer is a Python module in `pipeline/gt/layers/` exposing the same interface; a manifest (`manifests/layers/<key>.yaml`) declares source URLs, vintage, expected value ranges, and the reduction method. The CLI runs them: `gt layer run <key> --region <slug>`.

Reduction by data shape:

- **Raster → scalar** (light pollution, canopy, noise, NDVI): `rasterstats.zonal_stats` over tract polygons → mean / percent-above-threshold; **and**, for listing grain, `rasterio` point sampling + zonal stats over 100 m / 500 m listing buffers. Rasters never enter Postgres; raw files live in `data/raw/<layer>/` (gitignored), re-downloadable from the manifest URL.
- **Polygon overlay → share** (FEMA flood, parks, conservation land): `ST_Intersection` area share per tract; at listing grain, exact point-in-polygon (flood zone yes/no) or distance-to-nearest-edge (parks).
- **Point/monitor → interpolation** (EPA air quality): assign tracts the inverse-distance-weighted mean of monitors within 30 km; fall back to county mean. Neighborhood-context grain only.
- **Network-derived** (commute, transit, walk/park access): computed against OSM / GTFS / routing APIs from tract centroids (population-weighted) — and from listing points directly where cheap (distance to nearest transit stop, nearest park entrance).
- **Computed scores** (GVI, any composite): own module, but output is still rows in `region_metrics` / `listing_metrics` — composites are SQL views over base metrics, never opaque stored numbers.

Each layer manifest declares `grains: [tract, listing]` (or tract-only) and the listing reduction (`point`, `buffer_100m`, `buffer_500m`, `distance`). `gt layer run <key> --grain both` is the default for environmental layers.

Source table (POC set — chosen for free access, with native resolution governing which grains are honest):

| metric_key | Source | Native res. | Tract reduction | Listing grain |
|---|---|---|---|---|
| `canopy_height_m` | **Meta/WRI Global Canopy Height (1 m, free, on AWS)** | **1 m** | zonal mean | point + buffer_100m — the house-to-house green signal |
| `gvi_ndvi_street` | Sentinel-2 NDVI, road-buffer-masked (§5) | 10 m | masked zonal mean | buffer_100m / buffer_500m |
| `tree_canopy_pct` | NLCD Tree Canopy Cover (MRLC) | 30 m | zonal mean % | buffer_100m / buffer_500m |
| `noise_mean_dba`, `noise_pct_over_55` | BTS National Transportation Noise Map (§6) | ~30 m | zonal mean + % ≥ threshold | point + buffer_100m |
| `noise_sources` | OSM POIs (sirens, nightlife, industrial) + FRA freight rail (§6) | exact points/lines | source density per km² | distance/flag per source class — no synthesized dB |
| `flood_sfha` | FEMA NFHL | parcel-exact polygons | % tract area in A/AE/V | exact point-in-polygon flag |
| `park_access` | OSM (osmnx) leisure=park + PAD-US | exact polygons | % residents within 800 m | distance to nearest park edge |
| `transit_access` | GTFS via Transitland | exact points | stops per km² | distance to nearest stop |
| `light_pollution_radiance` | VIIRS VNL V2 annual median (EOG) | ~500 m | zonal mean (nW/cm²/sr) | neighborhood context only |
| `aqi_annual_mean` | EPA AQS annual summary API (+ PurpleAir later for hyperlocal) | monitor network | IDW to tract | neighborhood context only |
| `walkability_index` | EPA National Walkability Index | block group | housing-unit-weighted mean | block-group value attached |
| `risk_index` | FEMA National Risk Index | tract-native | direct GEOID join | tract value attached |
| `effective_tax_rate` | ACS 5-yr B25103/B25077 (§7) | place/county-subdiv. | direct, mapped to tracts | n/a (regional by nature) |
| `median_home_value` | Zillow ZHVI (ZCTA) — file already in repo | ZCTA | crosswalk to district (§3.3) | n/a |
| `commute_minutes_<anchor>` | OpenRouteService (§9/§10) | computed | tract-centroid → anchor | per-listing on demand (Explorer detail view) |

The **canopy height map is the headline addition for street-level green**: at 1 m it distinguishes a street of mature oaks from a clear-cut cul-de-sac two blocks away — exactly the house-to-house variation the product cares about — and it complements `gvi_ndvi_street` (which captures lawns/shrubs/visual green, not just tall canopy). Where state/county LiDAR canopy exists (PA has statewide lidar-derived products), the manifest can swap it in as a higher-fidelity vintage without schema changes.

Two substitutions vs. the brief, both deliberate: **EPA Walkability Index over Walk Score API** (Walk Score's API is restricted/commercial; EPA's is free, national, block-group-native) and **FEMA NRI over First Street** (First Street's API is paid; NRI is free and tract-native — First Street can be a paid upgrade later).

## 5. Perceived green view (GVI): phased recommendation

The honest answer: true GVI requires street-level imagery, and the canonical pipeline (MIT Treepedia) is: sample points along the road network → pull street imagery at each point (multiple headings) → semantic segmentation → vegetation-pixel fraction → aggregate. The constraint is imagery access: **Google Street View static API is priced per image and its ToS prohibits deriving stored data products from imagery** — do not build on scraped GSV. That reshapes the plan:

**Phase 1 (build now) — street-adjacent NDVI proxy, `gvi_ndvi_street`.** Sentinel-2 (10 m, free) summer cloud-free composite → NDVI → mask to a 50 m buffer around the OSM road network → zonal mean per tract **and per listing buffer (100 m / 500 m)**. This is *not* canopy-from-above repackaged: masking to the road corridor captures street trees, lawns, and roadside vegetation while excluding interior forest blocks and rooftops, which is most of the divergence between canopy% and perceived greenness in dense suburbs. Paired with the 1 m canopy height map (§4), the Explorer can show per-listing: canopy height on this block, street-level greenness within 100 m, and the walkable-green within 500 m. Cheap, national, reproducible. Surface the canopy-vs-street-NDVI *difference* as its own signal (high canopy + low street NDVI = "green from a plane, gray from the sidewalk").

**Phase 2 (research track) — sampled segmentation GVI, `gvi_streetlevel`.** Use **Mapillary** (free API, ToS-compatible, crowd-sourced coverage is decent in the Northeast). With listing-level granularity as the goal, anchor sampling to the frozen listing set rather than tract-stratified points: for each listing, sample the nearest 3–5 road points within 150 m, fetch nearest images, run an off-the-shelf segmentation model (SegFormer/Mask2Former fine-tuned on Cityscapes; `vegetation` class fraction per image), average per listing; tract values aggregate from listing/road samples. Coverage will be patchy — store `gvi_streetlevel_n_images` per listing and only display where n ≥ threshold, falling back to the NDVI proxy with a "estimated from satellite" label. Validate Phase 1 against Phase 2 where covered; if correlation is strong (likely r > 0.7 in suburbs), the NDVI proxy is defensible everywhere.

Buildable at POC scale: Phase 1 is a normal layer module (~1 day of agent work). Phase 2 is the one genuinely research-grade pipeline in the system — sequence it last (tasks.md Phase 11) and treat it as portfolio-narrative material.

## 6. Noise composite: don't build it — BTS already did

The brief assumes road/rail/flight must be combined by us. They don't: the **USDOT/BTS National Transportation Noise Map** is a published CONUS raster of 24-hour equivalent A-weighted sound level (LAeq) that already combines aviation, highway, and rail (passenger rail added in recent vintages). Use it as the base layer:

- `noise_mean_dba` — zonal mean per tract
- `noise_pct_over_45` / `noise_pct_over_55` — % of tract area at or above thresholds (45 dBA ≈ noticeable outdoors at night, 55 ≈ EPA annoyance guideline). The threshold-share metrics are more meaningful to users than the mean, because noise is spatially spiky.

Known limitation to document in `metric_definitions.notes`: it models *transportation* noise only (no industrial/neighborhood/intermittent sources) and is a modeled annual average, not measured. At ~30 m resolution it supports listing grain directly (point + buffer_100m).

**Supplemental layer — `noise_sources` (proximity indicators, not decibels).** Covers what the BTS model structurally misses: intermittent and point-source noise. Per listing (and as tract densities for Discovery): distance to nearest siren source (OSM `amenity=fire_station|police|hospital`), nightlife cluster proximity (density of `amenity=bar|nightclub|pub` within 300 m), industrial land-use adjacency (OSM/local `landuse=industrial` within 500 m), and **distance to active freight rail** (FRA rail network filtered to freight use — kept separate because an annual LAeq average underweights night horn events, the most-complained-about rail noise). These are served as labeled distances/flags ("fire station 250 m"), never synthesized into dB values — same honesty rule as raster native resolutions. Do **not** attempt a self-built physics composite for transportation modes — proximity-based dB estimates would be strictly worse than BTS's traffic-volume/flight-path model and violate the effort/value budget of a POC.

## 7. Purchasing power engine

**Location:** `app/src/lib/finance/` — pure, unit-tested TypeScript, imported by server functions (and usable client-side for instant slider feedback). No LLM involvement (CLAUDE.md rule 4).

Closed-form core: monthly budget B, down-payment fraction d, monthly mortgage constant m(r, 360) = r/12 · (1+r/12)³⁶⁰ / ((1+r/12)³⁶⁰ − 1), regional effective tax rate t, insurance rate i (state-level estimate, ~0.35–0.5%/yr), PMI rate p applied when d < 20%:

```
B = P·[(1−d)·m + t/12 + i/12 + (d<0.2 ? (1−d)·p/12 : 0)]
→ P_max = B / [ ... ]        // linear in P; no iteration needed
```

- **Rate source:** Freddie Mac PMMS weekly average via FRED API, fetched server-side, cached 24 h, with a hardcoded fallback. Level 2 credit bands apply a spread (excellent +0, good +0.4, fair +0.9 pts — documented constants, tunable).
- **Tax source:** `effective_tax_rate` metric from ACS 5-year tables **B25103 (median real-estate taxes paid) ÷ B25077 (median home value)** at county-subdivision/place level — fully automatable nationally, which is what makes Discovery-region expansion (§10) possible. County assessor mill rates are a later precision upgrade (the spec treats them as a metric *vintage* replacement, not a schema change). PA's school-district tax component is a natural showcase: in PA, district choice and tax burden are the same decision.
- **Levels 0–3** from the brief map directly to optional fields on `DiscoveryProfile` (§3.4) — the function signature doesn't change, defaults fill gaps (d=0.20, no debts, 'good' band). Level 2 debt feeds a DTI cap as a *second* ceiling: P_max = min(budget-derived, DTI-derived), clearly labeled which bound is binding — that label is itself a tradeoff insight.
- **Map shading:** precompute nothing. `computePurchasingPower(profile)` evaluates the closed form across all districts in one pass (<1 ms for hundreds of regions) and the map colors districts by P_max. The "Hudson Valley = $940k vs Lower Merion = $780k on the same $5,500/mo" moment is this endpoint plus a choropleth.

## 8. Tradeoff / archetype engine

Strict split: **deterministic numbers, LLM language.**

Deterministic (Python job, `gt archetypes build`):
1. Build the district × metric matrix from `district_metrics`; percentile-normalize each metric within the active region set (percentiles, not z-scores — geospatial metrics are heavy-tailed).
2. Cluster with **k-means over k=4..9, select k by silhouette score**; fall back to HDBSCAN only if silhouette is uniformly poor (<0.25). K-means first because archetypes should partition everything — "noise points" are bad UX.
3. Persist: `archetypes(id, model_version, centroid jsonb, silhouette)` and `region_archetypes(region_id, archetype_id, distance)`. Deterministic seed; rebuilt only on pipeline runs, versioned so the UI never sees a half-rebuilt state.

LLM (Claude API via a small script, cached in DB):
4. **Labeling:** for each cluster, send the centroid's top-5 distinguishing percentiles (vs. global median) and receive `{label, one_line_description}` — e.g., centroid high in canopy/low in transit → "Quiet Green Suburb". Human approves labels before promote (they're product copy).
5. **Tradeoff narratives:** at request time, `discover` computes the structured delta between two regions under the user's profile (P_max difference, sqft-per-dollar via ZHVI, commute delta, top metric gaps) and the LLM renders it as one paragraph. The numbers in the prompt are the numbers in the output — a post-check regex-verifies every numeral in the response appears in the input payload; on mismatch, fall back to a deterministic template. Cache by (regionA, regionB, profile-bucket).

This is where LLM reasoning earns its place: translation of verified numbers into human framing — never generation of the numbers.

## 9. Frontend architecture

Keep the stack exactly as found: TanStack Start + Router + Query, React 19, shadcn/Radix, **Leaflet** (remove the unused `mapbox-gl` and `@types/mapbox-gl` deps; keep Mapbox raster tiles + existing token server function).

Routes:

```
/                  → redirect to /explore
/explore           → existing HousingSearch, upgraded: server-fn data, district polygons,
                     reads ?profile= for Discovery handoff (pre-filter + P_max price cap)
/discover          → constraint wizard (budget slider, anchors via address geocode →
                     ORS, weight sliders for metric groups). Profile lives in typed
                     search params (zod schema §3.4) — every step is a URL.
/discover/results  → ranked region cards (archetype badge, P_max, top metrics, map
                     choropleth) + compare drawer (2 regions → tradeoff narrative §8)
                     → "See listings" = navigate to /explore?profile=...
/login /signup     → better-auth pages; "Save this search" and favorite-heart buttons
                     prompt sign-in when signed out, then persist (§3.5)
/saved             → authenticated: saved profiles (re-open = navigate to its URL) + favorites
```

Structural additions, deliberately minimal: `src/server/` (server functions), `src/lib/finance/`, `src/lib/discovery/` (profile schema, weight presets), a `RegionChoropleth` Leaflet layer component, an **Explorer listing detail panel** (replaces the bare popup on click: district + environmental metrics from `getListingMetrics`, grouped by grain with neighborhood-context metrics visually distinguished from true street-level ones per the §3.3 honesty rule), and TanStack Query everywhere data is fetched. The existing `filters.ts` client-side filtering survives as-is for the Explorer (4.5k features filter fine in-memory once loaded; bbox/server filtering is for payload size, not interactivity) and gains environmental filter dimensions (e.g., min canopy height, max noise) backed by `listing_metrics`.

## 10. Multi-region expansion (Discovery only)

A region group is a YAML manifest — the unit of expansion:

```yaml
# manifests/regions/hudson-valley.yaml
slug: hudson-valley
state_fips: ["36"]
counties: ["36119","36087","36079","36071"]   # Westchester, Rockland, Putnam, Orange
layers: [light_pollution, tree_canopy, noise, flood, risk_index, walkability,
         transit, park_access, taxes, median_prices, gvi_ndvi_street]
anchors:                                       # precomputed commute targets for map shading
  - { label: "Grand Central", lat: 40.7527, lng: -73.9772 }
```

`gt region add <manifest>` runs an idempotent sequence, all free data, **no RentCast**: TIGER tracts + county-subdivisions for the counties → NCES districts clipped to the group (national EDGE file already downloaded once) → `regions` rows + `region_overlaps` (tract↔district, tract↔municipality area weights, ZCTA↔district housing-unit weights) → ACS tax tables → ZHVI subset → then each layer in the manifest. Every step writes to staging, validates (row counts, SRID, value ranges from layer manifests, ≥99% of tracts covered per layer), and stops before promote.

Cost of a new region ≈ one agent-supervised pipeline run + API-free downloads; the only per-region marginal costs are ORS routing calls (self-hostable if volume grows). The Explorer stays frozen at PA + Hudson Valley; Discovery regions are unconstrained. When (post-POC) a Discovery region should gain an Explorer, the listings table and join pattern already generalize — that's a data purchase decision, not an architecture change.

---

## Decisions log (for traceability)

| Decision | Choice | Rejected |
|---|---|---|
| DB hosting | Neon | Supabase (redundant API layer), self-host (ops cost) |
| API | TanStack server functions + Neon serverless driver | PostgREST, separate FastAPI |
| Map serving | Simplified GeoJSON from SQL | Vector tiles (deferred) |
| SRID | 4326 everywhere | Status-quo 3857 districts |
| Compute grain | Dual: listing-grain (point/buffer, Explorer) + census tract → rollups (Discovery) | District-only metrics, tract-only metrics |
| Street-level green | 1 m canopy height (Meta/WRI) + 10 m street NDVI + Mapillary GVI later | GSV scraping (ToS), GSV API (cost), canopy-%-only |
| Walkability | EPA National Walkability Index | Walk Score API (commercial) |
| Climate risk | FEMA NRI | First Street (paid) |
| Noise | BTS National Transportation Noise Map | Self-built multimodal composite |
| GVI | NDVI road-buffer proxy now; Mapillary segmentation later | GSV scraping (ToS), GSV API (cost) |
| Pipeline language | Python (uv, Typer CLI) | TS end-to-end (no raster ecosystem) |
| Handoff/working state | URL-encoded profile (no login wall) | Login-gated app |
| Auth & persistence | better-auth in our own Postgres; accounts as optional save layer (saved searches, favorites) | Clerk/Auth0 (user data off-platform, per-MAU pricing), Supabase Auth (reintroduces second platform) |
