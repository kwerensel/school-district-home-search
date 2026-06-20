# Groundtruth — Agentic Pipeline Plan

First-principles recommendation, per the brief. Prior thinking was not consulted. The governing constraint is restated up front because every design choice below flows from it: **the deterministic data layer stays deterministic — agents query verified district boundaries, they never infer them.**

---

## 1. Where agents provide leverage (ranked)

The useful question isn't "where could an agent act?" but "where is the work research-heavy, repeatable, and *cheaply verifiable*?" Geospatial enrichment scores maximally on all three: every layer is the same shape of job (find authoritative dataset → download → wrangle CRS/format → reduce to per-tract numbers → sanity-check distributions → load), the per-layer details differ enough to need judgment, and the output is numeric with known-in-advance valid ranges — which means validation can be automated and the agent can check its own work.

1. **Enrichment layer ingestion** (highest leverage). VIIRS, NLCD, BTS noise, FEMA NFHL/NRI, EPA AQS/Walkability, OSM, GTFS, ACS — a dozen sources, each a half-day of fiddly format/CRS/documentation work for a human, each an agent-sized task with mechanical acceptance criteria. This is also the work that would otherwise rate-limit the whole Discovery Engine.
2. **Pipeline operations + QA.** Running region expansions, reading validation reports, investigating anomalies (e.g., "18 invalid geometries in the NY shapefile" — exactly what the manual HV run hit), and rendering visual-QA maps. This *replaces the QGIS step*: the agent renders PNG choropleths/overlays (matplotlib + contextily) into `data/reports/qa/` and the human eyeballs PNGs instead of driving a GIS desktop app.
3. **The build itself.** Claude Code executing `docs/tasks.md` is the largest total agent contribution and part of the public narrative. The spec and tasks are written at that precision deliberately.
4. **Runtime language generation.** Archetype labels and tradeoff narratives (architecture-spec §8) — LLM as translator of verified numbers, with the numeral post-check guard.
5. **Explicitly not agentic:** district assignment (PostGIS only), financial math (pure TS), metric values (pipeline code only), clustering math (scikit-learn). Agents *write and run* this code; they never *are* this code at runtime.

## 2. Architecture: agent orchestrates, scripts execute

Two separate agent surfaces — don't conflate them:

**A. Build/data agents = Claude Code sessions driving a deterministic CLI toolbox.** The agent's "tools" are the `gt` CLI subcommands, each idempotent, each emitting a machine-readable JSON validation report. The agent plans, invokes, reads reports, diagnoses, retries — but every state change to data goes through a script a human can also run by hand. This is the single most important pattern in the plan: it makes agent runs reproducible, auditable, and resumable, and it means "agentic" never degrades into "an LLM transformed my data in ways I can't replay."

```
gt region add <manifest>      # tract/district/overlap scaffolding for a region group
gt layer run <key> --region <slug>   # fetch → process → reduce → load(staging) + report
gt validate --report latest   # re-run checks, exit nonzero on failure
gt qa map <key> --region <slug>      # render QA PNGs for human review
gt promote --layer <key> [--target neon]   # staging → live; refuses if validation failed
gt archetypes build && gt archetypes label  # cluster (deterministic) + LLM labels (gated)
```

Validation reports are the agent's ground truth, e.g.:

```json
{ "layer": "light_pollution", "region": "hudson-valley",
  "tracts_expected": 489, "tracts_computed": 489,
  "value_range_ok": true, "range_seen": [0.21, 38.4], "range_allowed": [0, 500],
  "nulls": 0, "srid_checks": "pass", "golden_checks": "pass", "promotable": true }
```

**B. Runtime LLM = two narrow, cached API calls** (labels, narratives) inside otherwise-deterministic server code. No tool use, no orchestration, no data access beyond the structured payload it's handed.

No long-running autonomous orchestrator for the POC. A solo builder gets more from interactive Claude Code sessions over a great CLI than from building agent infrastructure; if scheduled refreshes are ever needed (data vintages update yearly), a GitHub Actions cron invoking `gt layer run && gt validate` covers it without any agent in the loop at all. Revisit only if region count makes interactive runs tedious — and even then, the upgrade is "Claude Agent SDK script that loops the same CLI," not a new architecture.

## 3. Automated vs. human-reviewed

| Fully automated | Stop only when |
|---|---|
| Draft manifest/source note/sample stats for sources already named in the approved spec, then fetch/process/reduce | The source/provider is new, ambiguous, paid, credentials-constrained, ToS-constrained, or conflicts with the approved spec |
| Validation checks, report generation, QA map rendering | Validation is red/missing, QA artifacts are missing, or results are surprising enough to need interpretation |
| Explicit `gt promote` from a promotable validation report for an approved layer | The report is not promotable, the layer is marked blocked, or the promote would violate phase order |
| Geometry repair (`ST_MakeValid`) when count ≤ manifest threshold | Geometry repair above threshold → stop and show the broken features |
| Cluster computation | **Archetype labels:** product copy — human approves before they ship |
| Narrative generation (numeral-guard enforced) | Guard failures fall back to template + get logged for review |

The pattern: automation owns the normal build path once the source/application
plan is in the approved docs. Humans are needed for genuinely new commitments
or missing information, not routine yes/no re-approval. Trust still comes from
the deterministic CLI: staging first, validation reports, QA artifacts, and an
explicit promote command that can be replayed.

### The source-research protocol (what "onboarding" means concretely)

Most layers in the spec are pre-researched national sources — for those, agents
execute instead of stopping for approval. But the system has known research
moments: county assessor tax data (the per-county precision upgrade over ACS),
local LiDAR canopy swaps, regional GTFS feed discovery, and any future layer
idea. When an agent hits one, it follows this protocol:

1. **Enumerate candidates** (web search + data portals: data.gov, state GIS clearinghouses, county open-data sites), preferring official/primary publishers over aggregators.
2. **Evaluate each against fixed criteria:** license/ToS permits derived stored products; cost (free strongly preferred); coverage of target counties; native resolution vs. the grain we want to serve (honesty rule); vintage/update cadence; format sanity (machine-fetchable, documented CRS).
3. **Pull a sample** for one county/tract and compute trial statistics — distribution, nulls, range — against physical expectations.
4. **Draft the layer manifest** (source URL, vintage, allowed range, grains, reduction) plus a short comparison note: candidates considered, the one chosen, why, and what was rejected (this becomes the `metric_definitions.notes` provenance).
5. **Decide whether this is already covered.** If the source/application is
   covered by the approved architecture/tasks/handoff, continue into the full
   ingestion module. If it is a new commitment or missing-information decision,
   stop with the evidence packet and the specific question.

The deliverable of agent research is always a *manifest plus evidence* before
live data changes, never silently-loaded data — which keeps even open-ended
research work inside the staging/validate/explicit-promote trust model.

## 4. Sequencing

Build order = `docs/tasks.md` phases; the agent-relevant logic of the order:

1. **CLI skeleton + validation/report/promote machinery before any layer** (Phase 4). The toolbox is what makes every subsequent layer cheap; layers built before the harness exists become tech debt.
2. **Golden-region tests before migration** (Phase 1): pin known truths (specific Lower Merion / Scarsdale listings → their districts; 251 + 4,254 row counts) so the schema unification and every later change is regression-checked. These doubles as the agent's self-check.
3. **Easiest-data layers first** (Phase 5: light pollution, canopy, NRI, walkability, flood) to harden the pattern on clean sources before the messy ones (AQS interpolation, GTFS, noise thresholds, NDVI masking).
4. **Money before vibes** (Phase 6: taxes + purchasing power precede remaining enrichment): the purchasing-power map is the Discovery Engine's spine and demo moment; environmental layers compound on it.
5. **GVI street-level segmentation last** (Phase 11): the only research-grade pipeline; everything else must not wait on it.

## 5. Agent patterns suited to geospatial pipelines

- **Reduce-then-verify.** Rasters/polygons reduce to scalars with physically known valid ranges (canopy 0–100%, NDVI −1–1, dBA 35–90). Range + coverage + null checks catch the majority of geospatial bugs (wrong band, wrong CRS, unit confusion) mechanically — ideal for agent self-verification.
- **CRS as contract.** Every CLI step asserts input/output SRID and fails loudly. CRS confusion is the classic silent geospatial failure (this repo's 3857/4326 split is the live example); making it un-silent is what lets an agent operate safely.
- **Golden-region regression.** A handful of hand-verified facts ("this address is in Lower Merion SD", "Bronxville tract canopy ∈ [20, 60]%") run on every pipeline change. The geospatial analogue of snapshot tests.
- **Manifest-driven idempotency.** Declarative configs + resume-safe steps (the existing `fetch_hv_listings.py` already does skip-if-exists — generalize it) mean an interrupted or re-run agent session converges instead of duplicating.
- **Staging/promote with DB branching.** Neon branches give the agent a disposable full copy to test promotes against — agent experiments can't corrupt serving data even in principle.
- **Render-for-review.** Maps are the one artifact humans verify faster than any check can: standardize "every layer run produces a PNG." It's the highest-bandwidth human-in-the-loop channel this domain has.
