# Groundtruth Agent Instructions

Read this before doing repo work. This file keeps Groundtruth sessions
continuous, autonomous, and safe without requiring a fresh chat after every
small checkpoint.

## Read First

Use `docs/CODEX_HANDOFF.md` for current build state, latest commits, staged
data status, blockers, and next-step guidance.

For product, architecture, data, and phase-order questions, use this
source-of-truth order:

1. `AGENTS.md`
2. `docs/CODEX_HANDOFF.md`
3. `docs/tasks.md`
4. `docs/architecture-spec.md`
5. `docs/agentic-pipeline-plan.md`
6. Layer onboarding notes in `docs/layer-onboarding/`
7. Existing code and migrations
8. Historical docs or chat exports, if any, as context only

Default continuation prompt:

```text
Read AGENTS.md and docs/CODEX_HANDOFF.md. Continue the next Groundtruth arc
from the latest committed state.

Work autonomously for as long as the build path remains stable. Do not stop
after one checkpoint. Continue through multiple data, pipeline, and UI
checkpoints when they are unblocked, using parallel investigation where it is
safe. Commit and push each green checkpoint when the user has asked for
autonomous arc work. Stop only for a real blocker, an approval-required data
gate or promotion, a conflict with the source-of-truth docs, or a point where
the next meaningful work requires missing product/design direction.
```

## Product Shape

Groundtruth is a geospatial home-search platform with two linked tools on one
deterministic data backbone:

- Listing Explorer (`/explore`): verifies which school district a listing is
  actually in using PostGIS point-in-polygon joins against official NCES
  district boundaries.
- Discovery Engine (`/discover`): helps users decide where to search from
  budget and lifestyle constraints using regional metrics such as canopy, flood
  exposure, risk, walkability, taxes, and home values.

Discovery narrows the user to regions; Explorer shows frozen listings within
them. Profile handoff uses URL search params as canonical state.

## Commands

Pipeline:

- `cd pipeline && ./.venv/bin/gt --help`
- `cd pipeline && ./.venv/bin/gt manifest validate layer manifests/layers/<layer>.yaml`
- `cd pipeline && ./.venv/bin/gt layer run <layer> --region <slug> --grain both`
- `cd pipeline && ./.venv/bin/gt validate --report <report>.json`
- `cd pipeline && ./.venv/bin/gt qa map <layer> --region <slug>`
- `cd pipeline && ./.venv/bin/pytest -q`
- `cd pipeline && ./.venv/bin/pytest -k golden -q`

App:

- `cd app && npm run dev`
- `cd app && npm test`
- `cd app && npm run build`

Use `uv` if available; this checkout often uses the existing
`pipeline/.venv`. A checkpoint is green only when the relevant validation,
golden checks, QA artifacts, and tests pass.

## Hard Invariants

- The deterministic truth layer stays deterministic. District assignments come
  from PostGIS spatial joins against official NCES polygons. No LLM,
  heuristic, ZIP-code inference, or manual patch may assign or modify a
  district.
- RentCast is frozen. Never call RentCast or add listings/regions to Explorer.
  The working dataset is the existing frozen listing set: 251 PA and 4,254
  Hudson Valley listings.
- Do not use GreatSchools data. District quality will come from approved public
  sources later; `good_district` is only a curated placeholder.
- Financial math is code, not LLM. Purchasing-power calculations belong in pure
  TypeScript functions with unit tests. LLMs may explain outputs, never compute
  or invent them.
- Store geometry in EPSG:4326. Transform on import, use `geography` casts or
  `ST_Transform` for metric distance operations, and assert SRID after imports.
- Preserve staging -> validate -> explicit promote. Pipeline loads write to
  `staging.*`, emit validation reports, and only an explicit promote step may
  touch live tables.
- Never serve a metric at finer grain than its source supports. Coarse sources
  such as VIIRS and AQI are neighborhood context, not address-level facts.
- Accounts are a save layer, never a gate. The app must remain usable signed
  out. Saved profiles contain sensitive financial data; never log profile
  contents.

## Data Gates

New source onboarding gate:

- Draft the layer manifest, source note, and sample stats first.
- Stop for human approval before writing the ingestion module.
- After approval, implement, stage, validate, and render QA maps in the same
  session when feasible.

Promotion gate:

- Do not promote a staged data layer without explicit human approval.
- After approval, promote both project regions when applicable, refresh
  rollups, verify public counts/ranges, and run relevant tests.

Spatial QA gate:

- After any spatial operation, run golden-region checks.
- Every spatial layer run needs validation reports and QA PNGs under
  `data/reports/qa/`.
- Data/report artifacts under `data/` are gitignored and reviewed locally
  unless the ignore policy changes.

Blocked-source rule:

- If a phase is blocked by external access or human review, work ahead only on
  reversible, non-promoting tasks: source notes, manifests, tests, scaffolding,
  docs, or isolated UI prototypes that do not imply live data availability.
- Explicit blockers must be recorded in `docs/CODEX_HANDOFF.md`.

## Autonomy

Do without asking:

- Read files, inspect repo state, and consult the handoff.
- Edit files inside the repo.
- Run local checks, pipeline validation, QA rendering, and tests.
- Implement an already-approved layer or task.
- Stage approved data into `staging.*` and generate validation/QA artifacts.
- Fix bugs discovered while implementing or validating approved work.
- Commit green checkpoints when the user has asked to power through an arc,
  phase, or follow-on work.
- Push checkpoint commits when the user asks for autonomous progress,
  commit/push, or a meaty build session.

Ask first:

- New data source approval after manifest + sample stats.
- Any data promotion from staging to live tables.
- Schema or migration changes that are not already in the approved task.
- New dependencies, paid services, provider integrations, or credentials.
- Broad product direction changes or UI behavior that changes the agreed user
  journey.
- Destructive file or git operations.

Never:

- Promote on a failed or missing validation report.
- Commit a red checkpoint unless the commit is explicitly a failing-test
  reproduction requested by the user.
- Revert user changes unless explicitly requested.
- Wire blocked/later-phase data into the main journey before its gate passes.
- Start GVI work before the planned phase.
- Print or commit secrets from `app/.env.local` or elsewhere.

## Workflow

- Prefer meaty autonomous sessions over tiny one-step chats.
- Keep building until a real blocker or surface boundary. Do not stop merely
  because one manifest, one layer, one test, or one commit is complete.
- Follow `docs/tasks.md` phase order for live behavior and promotions, but work
  ahead on reversible scaffolding when a gate is blocked.
- Use the rhythm `source gate -> implementation -> staged validation/QA ->
  promotion approval -> promote/verify -> commit`.
- After an approved layer is staged/validated/QA-rendered, stop for promotion
  approval; after promotion approval, promote, verify, commit/push, then keep
  moving to the next unblocked Phase 5/phase-ordered task.
- When a source is blocked, continue to the next reversible task allowed by the
  phase rules instead of ending the session.
- Multiple commits in one session are expected when the user asks to power
  through an arc.
- Update `docs/CODEX_HANDOFF.md` after meaningful checkpoints: source packet,
  staged/validated/QA-rendered layer, promotion, build-phase gate, commit/push,
  or blocker.
- Keep `docs/CODEX_HANDOFF.md` concise but sufficient for the default
  continuation prompt.
- Do not recommend a fresh chat after every commit. Recommend a fresh chat only
  when context is unreliable, the next work is a substantially different arc,
  or the user explicitly wants a clean handoff. Otherwise, keep going.

Stop conditions:

- A human approval gate is reached: new source approval or staged-data
  promotion approval.
- A required credential/source access/design decision is missing.
- Verification is red and the failure cannot be responsibly fixed in the
  current arc.
- The next meaningful work would violate phase order or wire blocked/later
  data into the main journey.
- The work reaches a true surface boundary, such as finishing the current data
  layer arc and needing a new product/UI direction.

## Repo Layout

```text
app/                  TanStack Start frontend + server functions
  src/components/     UI, shadcn/Radix, housing/map components
  src/lib/housing/    housing types, filters, server function clients
  src/lib/finance/    purchasing-power engine, pure TS + tests
  src/server/         API layer via TanStack server functions + Neon
pipeline/             Python geospatial pipeline
  gt/                 Typer CLI entrypoint
  layers/             one module per enrichment layer
  manifests/          regions/*.yaml and layers/*.yaml
sql/migrations/       numbered, idempotent, forward-only migrations
docs/                 architecture, plan, tasks, handoff, layer onboarding
data/                 gitignored raw/intermediate/report artifacts
```

## Conventions

- Python: 3.11+, `uv` or `pipeline/.venv`; geopandas, rasterio, rasterstats,
  osmnx, shapely, Typer, pydantic, psycopg.
- TypeScript: zod-validate every server-function input. DB access goes through
  `app/src/server/db.ts`.
- SQL: numbered forward-only migrations, rerunnable with guards.
- Metrics: long format, one row per `(region, metric_key, vintage)` in
  `region_metrics`; every metric has a `metric_definitions` row.
- Region rollups: compute at census-tract grain where appropriate; roll up to
  districts/municipalities through `region_overlaps`.
- Listing metrics: point, 100 m buffer, 500 m buffer, or exact flags only when
  source resolution supports that grain.
- District display names are normalized, but raw NCES names stay preserved in
  `name_raw`.
