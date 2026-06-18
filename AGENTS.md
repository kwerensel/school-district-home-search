# CLAUDE.md — Groundtruth

Geospatial home-search platform. Two tools, one data backbone:

- **Listing Explorer** (`/explore`): verifies which school district a listing is *actually* in, using point-in-polygon joins against official NCES district boundaries (not ZIP codes).
- **Discovery Engine** (`/discover`): answers "where should I even be looking?" from a user's monthly budget + life constraints, using regional median prices, effective property taxes, and enrichment layers (light pollution, noise, canopy, walkability, etc.).

Discovery narrows the user to regions → Explorer shows listings within them. The handoff carries the user's profile via URL search params.

## Hard rules (never violate)

1. **The deterministic truth layer stays deterministic.** District assignments come from PostGIS spatial joins against NCES polygons. No LLM, heuristic, or ZIP-based inference ever assigns or modifies a district. Agents/LLMs query verified data; they never produce it.
2. **RentCast is frozen.** Never call the RentCast API or add listings/regions to the Explorer. The working dataset is the ~4,505 listings already in the database (251 PA + 4,254 Hudson Valley). The Discovery Engine never uses RentCast at all — it uses free regional data only.
3. **No GreatSchools data.** Intentionally excluded. District quality will come from PVAAS / Stanford SEDA in a later phase; until then `good_district` is a curated placeholder.
4. **Financial math is code, not LLM.** Purchasing-power calculations are pure TypeScript functions with unit tests. LLMs may explain results, never compute them.
5. **All geometry is stored in EPSG:4326.** Transform on import. Use `geography` casts or `ST_Transform` for metric distance ops. Always assert SRID after any geometry import.
6. **Staging → validate → promote.** Pipeline loads write to `staging.*` tables, emit a validation report, and only a separate explicit `promote` step touches live tables.

## Repo layout

```
app/                  TanStack Start (React 19) frontend, deploys to Cloudflare
  src/components/     UI (shadcn/Radix) + housing/ map components (Leaflet)
  src/lib/housing/    types, filters, server functions
  src/lib/finance/    purchasing-power engine (pure TS, unit-tested)
  src/server/         TanStack server functions = the API layer (Neon serverless driver)
pipeline/             Python package (uv-managed): all data ingestion/processing
  gt/                 CLI entrypoint (Typer): `gt region add`, `gt layer run`, `gt promote` ...
  layers/             one module per enrichment layer
  manifests/          regions/*.yaml and layers/*.yaml (declarative configs)
sql/migrations/       numbered, idempotent migration files
docs/                 architecture-spec.md, agentic-pipeline-plan.md, tasks.md
data/                 gitignored; raw downloads and intermediates live here, never in git
```

## Conventions

- **Python:** 3.11+, `uv` for deps. geopandas / rasterio / rasterstats / osmnx for geo work. Every pipeline command is idempotent, takes explicit input/output args, and writes a JSON validation report to `data/reports/`.
- **TypeScript:** zod-validate every server-function input. DB access only through `app/src/server/db.ts` (Neon serverless driver). Shared row types live next to the queries.
- **SQL:** migrations are forward-only, numbered `NNN_description.sql`, runnable repeatedly without error (`IF NOT EXISTS` / guarded).
- **Metrics:** long format — one row per (region, metric_key, vintage) in `region_metrics`. Every metric has a row in `metric_definitions` with source, units, direction, and native resolution. Compute at census-tract grain; roll up to districts/municipalities via `region_overlaps` area weights.
- **Dual grain:** environmental/sensory layers are also computed per listing (`listing_metrics`: point, 100 m buffer, 500 m buffer) — the Explorer shows the street, Discovery shows regional averages. Never serve a metric at finer grain than its native resolution supports (VIIRS ~500 m and AQI are neighborhood context, not address-level facts); the UI must visually distinguish the two.
- **Auth:** better-auth on TanStack Start, users/sessions in our own Postgres. Accounts are a save layer, never a gate — the app is fully usable signed out, with URL search params as canonical state. Saved profiles contain sensitive financial data (budget, down payment, credit band): never log profile contents; account deletion cascades.
- **Naming:** district display names are normalized (suffixes like " Central School District" stripped — see `pipeline/gt/normalize.py`); raw NCES names are always preserved in `name_raw`.

## Commands

```
cd app && npm run dev          # frontend + server functions
cd pipeline && uv run gt --help
uv run gt region add manifests/regions/hudson-valley.yaml
uv run gt layer run light_pollution --region hudson-valley
uv run gt validate --report latest && uv run gt promote --layer light_pollution
uv run pytest                  # pipeline tests (golden-region regression suite)
cd app && npm test             # finance engine + server fn tests
```

## Working agreements for agents

- Read `docs/tasks.md` before starting work; tasks are ordered and have acceptance criteria. Don't skip phases.
- After any spatial operation, run the golden-region checks (`uv run pytest -k golden`): known listings must keep their known districts (e.g., the Lower Merion fixtures).
- When onboarding a new data source: draft the layer manifest + a sample-stats summary first, and stop for human review before writing the full ingestion module.
- Visual QA replaces QGIS: `gt qa map <layer> --region <slug>` renders PNGs to `data/reports/qa/` for human review. Generate these after every layer run.
- After every commit + push or build-phase gate, advise whether to continue in the current chat or start a fresh one. If a fresh chat is recommended, always provide a copy-paste prompt for the next session.
