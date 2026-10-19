# Private operator track

Status: private workflow foundations and explicit local commands implemented.
`sql/migrations/011_operator.sql` was exercised in a rollback-only Neon test;
it **has not been durably applied**. No permanent role has been granted, no provider request made, no permanent
listing version loaded/published, no region expanded, no attendance polygon
imported and no external message or call sent. The rollback test temporarily
registered snapshots, staged two fixture records and selected a private pointer;
all database effects rolled back.

## Security boundary

Operator access requires both the server deployment environment
`GROUNDTRUTH_OPERATOR_ENABLED=true` and an `operator_roles` row for the user ID
from a verified Better Auth session. `pipeline/gt/operator.py:require_operator`
queries this server-owned role table with a bound parameter and fails closed.
The app must perform the corresponding check for every server operation; a
hidden button, route guard, request field or client-provided role is not a
security boundary. The feature flag does not grant a role.

Role grants are an explicit database-owner operation. No client API to create
or change roles is provided. New tables revoke privileges from PostgreSQL's
PUBLIC role; the trusted server/database owner still has privileges, so this
is not a substitute for endpoint session checks. Do not expose the server
connection string or allow arbitrary SQL through an operator endpoint.

## Versioned listing refresh

`ListingProviderAdapter` defines an **estimate-only** boundary. Its estimate
includes provider, area, source vintage, estimated records/credits and estimate
basis. Unknown credits remain unknown. There is no fetch/bill method, no
RentCast request and no new provider integration.

`ListingCandidate` validates explicit provider/source IDs, point coordinates
and basic record values. `listing_dry_run` compares two supplied snapshots by
provider/source identity, removes identical duplicates, blocks conflicting
duplicate identities, reports additions/removals/changes and hashes a stable
normalized snapshot. Co-located IDs are surfaced for review instead of merged:
units can legitimately share an address or coordinates. No heuristic changes a
district assignment. The `baseline_count` gate is an invariant assertion, not a
replacement for a database count; adapters must independently verify 4,505.

The implemented supplied-record workflow follows these separate steps:

1. Authenticate admin and feature flag. Present the approved area, provider,
   vintage, records/credits, terms and credit-budget evidence. Record explicit
   provider/account/terms/budget approval before any paid fetch. The existing
   RentCast freeze remains active until separately superseded by the user.
2. Before enabling any publish operation, register all 4,505 existing listings
   as immutable baseline members with source snapshots in one transaction,
   after verifying frozen counts and golden assignments. `register_frozen_baseline` implements this explicit registration; it is not
   invoked by the migration. Baseline membership/snapshots then reject
   updates/deletes, and registered original listing rows reject overwrite or
   deletion. Future refreshes go into a distinct version and staging records.
3. `stage_listing_candidates` loads a new `listing_dataset_versions` row and
   `staging.operator_listing_records` from supplied validated records, with
   duplicate checks, estimate/approval records and a stable source hash.
   Do not update `listings`. Source geometry must be EPSG:4326; query/load
   adapters must assert SRID and geometry validity after transforming imports.
4. Run `DISTRICT_ASSIGNMENT_SQL`. Only a unique official NCES polygon covering
   the point yields an assignment. Zero matches or boundary/overlap ambiguity
   remain unresolved and block publication. No ZIP, nearest-school or LLM
   inference is allowed. Retain match counts and spatial QA.
5. Generate a target-specific validation report/hash, exact expected/actual
   counts, zero unresolved/ambiguous assignments, QA PNGs under
   `data/reports/qa/`, and a passing golden run. Retain the validated source hash; publication refuses changed staging.
   The explicit publisher locks records while rechecking and freezes the version
   as it transitions through validated to published. Actual adapters must read and verify the report/artifact bytes;
   never accept `promotable`/`golden_passed` booleans from an untrusted client.
6. Present the report and diff for a separate intentional publish command.
   `listing_publish_plan` checks matching evidence, provider approval and the
   frozen-count invariant, but intentionally **does not publish**. `publish_listing_dataset` transactionally rechecks the unchanged source
   hash, staged record count, unique PostGIS assignment, approval and actual
   report/PNG evidence before marking it published and selecting a version in
   `operator_active_listing_dataset`. It requires `explicit_publish=True`. Preserve the old
   version and immutable baseline. Published version metadata/records reject
   mutation. Current public Explorer readers continue using frozen `listings`;
   no active-reader switch is implemented here.

`ProviderApproval` records references to approval evidence, never credentials.
The scaffold's input objects are server evidence contracts, not an authorization
UI or permission to call a provider. Estimated credits are not a guaranteed
invoice; unknown estimates or over-budget estimates block the publish plan.

## Region expansion jobs

`draft_region_manifest` validates official county FIPS selections through the
existing `RegionManifest` model, sorts/deduplicates them and generates draft
state/county/layer fields. It requires official selection evidence and marks
layer/listing coverage, external credits and runtime unknown until measured.
Generating a draft does not activate a region or fetch listings.

`enqueue_region_job`, `claim_region_job`, `advance_region_job` and
`run_region_job_once` persist `operator_jobs`, acquire an expiring worker lease
with `FOR UPDATE SKIP LOCKED`, and resume a single phase at a time. Claim
attempts and lease ownership are stored. Drafts cannot overwrite an existing
public region slug. The tested state machine is:

```
draft -> scaffolding -> coverage -> validated -> promoted
                            |          |
                         blocked    explicit promote required
```

Blocked coverage may return to coverage; terminal failed/promoted jobs do not
restart silently. Scaffolding invokes existing region staging primitives.
Coverage records each approved layer's source/licensing/access/runtime and
actual listing coverage. Validated/promoted transitions require complete
coverage plus matching green report, QA and golden evidence. Promotion is a
separate explicit action, not a map checkbox. The worker is callable through `work-region`. Its source-scaffolding step is
explicitly enabled with `--run-official-scaffold` and invokes the existing
official region importer, renders **staged** QA and runs golden checks. It
hashes all staged polygons, district inputs and overlap rows. Coverage checks
actual matching layer reports and QA PNGs, not just source packet existence.
Missing/failed layers block the job; `retry-region` explicitly requeues coverage.
Enrichment runs themselves remain operator-controlled existing pipeline commands;
the worker never invents a provider call or listing import. Existing layer
reducers read public region rows, so genuinely new-region layer staging may
require separate geometry-foundation promotion or a future staging-aware layer
reader; this ordering gate is recorded as blocked coverage rather than bypassed.
An empty layer list cannot pass coverage.

A validated job is skipped by normal worker claims and waits for a targeted
`--explicit-promote --job-id ID`. It rechecks the stored report hash, exact layer
coverage evidence, actual QA and unchanged staged source fingerprint, then calls
the existing explicit region/layer promoters and runs golden verification. Public
promotion primitives commit separately; a failure after one promotion is
recorded as failed and needs operator inspection before further work. No job
claim is proof that a new region's data coverage is complete.

## Attendance zones and evidence

District boundaries and school attendance zones remain separate facts.
`attendance_evidence` stores district, source kind/URL, retrieval time, content
hash, school year, grade range, written-reference and human review.
`attendance_zones` stores school NCES ID, source zone ID, matching evidence
scope and valid nonempty EPSG:4326 MultiPolygon geometry. Grades use 0 for
kindergarten and 1–12 for numbered grades. An ingestion adapter must explicitly
map source grade codes to these values; preschool is outside this draft scope.

Evidence statuses are `official`, `written-confirmed`, `provisional`, and
`unresolved`. Only reviewed official GIS or a written-confirmed boundary file
can support published polygons. The trigger verifies matching district/year/
grade scope. An official locator or written confirmation of one address is
address-specific evidence stored in `attendance_locator_results`; it never
creates or expands a polygon. No claim is inferred from ZIP, proximity, an LLM,
or an undocumented verbal answer.

`AttendanceEvidence` and `attendance_assignment_plan` gate the reviewable
scope. `ATTENDANCE_ASSIGNMENT_SQL` applies exact PostGIS point-in-polygon
coverage within district/year/grade scope. `resolve_attendance_matches`
returns an assignment only for one reviewed covered zone. No match or multiple
covered zones remain unresolved with a reason. A future ingestion adapter must
freeze reviewed evidence, validate geometries/overlap and golden examples,
generate QA/report evidence and explicitly promote before public display.
Neither official GIS fetching nor locator automation is implemented here.

The SQL is forward-only/rerunnable schema scaffolding, not proof of source
completeness. It was executed twice in a rollback-only Neon fixture, including registration,
assignment, private publication, immutability and leased queue transitions. The
fixture left no durable schema or data. Attendance ingestion/locator integration
and real provider/region acceptance remain required before enabling those
private operations.

## District outreach

`district_outreach_queue` retains missing evidence, district/year/grade scope,
contact provenance, identified sender and draft. `district_outreach_draft`
produces a neutral request to the district enrollment/transportation office for
an official GIS file/locator or written confirmation procedure. It includes no
student information, parent impersonation or undocumented school assignment.

No recipient is auto-selected. There is no send/call adapter, configured sender,
telephony integration, call recording or bulk-school outreach. The draft's
`send_enabled` and `call_enabled` are false. Any future transmission needs an
explicitly authorized sender/provider/account, budget and applicable consent
setup; store written replies and require human review before publishing.

## Explicit local commands

The CLI is separate from the shared `gt` entry point:

```
cd pipeline
./.venv/bin/python -m gt.operator_cli --help
./.venv/bin/python -m gt.operator_cli register-baseline --version frozen-4505-v1 --report data/reports/baseline.json
./.venv/bin/python -m gt.operator_cli stage-local-json --version refresh-v1 --input ../data/operator/supplied-records.json
./.venv/bin/python -m gt.operator_cli validate-listings --version refresh-v1
./.venv/bin/python -m gt.operator_cli publish-listings --version refresh-v1 --report data/reports/VALIDATED_REPORT.json --explicit-publish
./.venv/bin/python -m gt.operator_cli enqueue-region --input ../data/operator/region-draft.json
./.venv/bin/python -m gt.operator_cli work-region --worker-id local-worker
./.venv/bin/python -m gt.operator_cli work-region --worker-id local-worker --run-official-scaffold
./.venv/bin/python -m gt.operator_cli retry-region --job-id 123
./.venv/bin/python -m gt.operator_cli work-region --worker-id local-worker --explicit-promote --job-id 123
```

All commands require server-side `GROUNDTRUTH_OPERATOR_ENABLED=true`, the existing
`DATABASE_URL`, and a trusted local `GROUNDTRUTH_OPERATOR_USER_ID` with an admin
role. The latter is a configured worker audit identity, not a public-session
login mechanism. Public app endpoints must derive identity from the verified
session; they must never forward a client-selected user ID into these functions.
Schema application and initial role provisioning remain explicit owner actions.
CLI exceptions are sanitized and never print connection strings or raw provider
responses.

`validate-listings` renders real PNG QA, reassigns districts from geometry,
checks counts/source hash/SRID/ambiguity and invokes the spatial golden suite.
It writes a staged report and does not publish. Reports include `target`,
`promotable`, `qa_artifacts` and `checks` containing `golden_passed`,
`expected_count`, `actual_count`, `unassigned_count`, `ambiguous_count` and
`source_content_hash`. Publication reads these on disk, hashes their bytes,
verifies the PNGs and refuses stale/changed content.

## Validation and remaining gates

Pure tests cover server flag/database roles, deterministic diffs, duplicates,
provider budgets, actual report/PNG evidence, phase order, explicit promotion,
matching layer coverage, attendance ambiguity and disabled outreach. The live
rollback fixture applies migration 011 twice, creates a temporary admin user,
registers 4,505 snapshots, stages supplied fixture records, publishes only the
private pointer, exercises immutability and queue leases, then rolls everything
back. No provider is contacted.

**DDL-lock test rule:** trigger creation/replacement can hold an exclusive lock
on `listings` until the rollback fixture ends. Run golden checks *before* opening
that DDL transaction, and reuse their verified result inside the rollback test.
Never start a second golden connection while holding the DDL lock. Coordinate
live fixture timing with browser QA and keep the locked test section short.
Production validation, after durable migration completion, runs independent
golden connections normally.

Before any durable operator rollout: apply the schema intentionally, register
real baseline evidence, grant the intended administrator role, verify the app's
server-session checks and flag, and complete real region/attendance acceptance.
Actual provider fetching, paid credits, external communications and production
release remain separately gated. No segmentation dependency/model gate is
changed by this operator work.

Latest verification: 13 operator tests passed against Neon with the rollback-only
fixture enabled (8.17 seconds), including staged source tamper refusal, real QA
rendering and private publication. The independent golden suite ran before DDL
locks. The fixture rolled back and closed its connection. Combined pure operator
and research suites: 19 passed, one opt-in live test skipped by default.
