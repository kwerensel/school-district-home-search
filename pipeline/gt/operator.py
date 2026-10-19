"""Private operator planning primitives. No provider requests, publishing or outreach.

Mutating adapters must authenticate a server session and call require_operator.
Plans are reviewable evidence, not permission to bypass explicit promotion.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import os
import re
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator
from gt.manifests.models import RegionManifest

FROZEN_BASELINE_COUNT = 4505


def require_operator(conn: Any, authenticated_user_id: str | None) -> None:
    """User ID must come from a verified session, never from request input."""
    if os.environ.get("GROUNDTRUTH_OPERATOR_ENABLED") != "true" or not authenticated_user_id:
        raise PermissionError("Operator access unavailable")
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM operator_roles WHERE user_id = %s AND role = 'admin'", (authenticated_user_id,))
        if cur.fetchone() is None:
            raise PermissionError("Operator access unavailable")


@dataclass(frozen=True)
class ProviderEstimate:
    provider: str
    area: str
    vintage: str
    estimated_records: int | None
    estimated_credits: float | None
    estimate_basis: str

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.area.strip() or not self.vintage.strip() or not self.estimate_basis.strip():
            raise ValueError("Estimate requires provider, area, vintage and evidence basis")
        if self.estimated_records is not None and self.estimated_records < 0:
            raise ValueError("Estimated record count cannot be negative")
        if self.estimated_credits is not None and (not math.isfinite(self.estimated_credits) or self.estimated_credits < 0):
            raise ValueError("Estimated credits cannot be negative or nonfinite")


class ListingProviderAdapter(Protocol):
    """An estimate-only boundary. No fetch/bill method is implemented here."""
    def estimate(self, *, area: str) -> ProviderEstimate: ...


@dataclass(frozen=True)
class ProviderApproval:
    provider: str
    account_reference: str
    terms_evidence: str
    approved_credit_budget: float
    approved_by: str
    approved_at: str

    def check(self, estimate: ProviderEstimate) -> None:
        if self.provider != estimate.provider or not all((self.account_reference, self.terms_evidence, self.approved_by, self.approved_at)):
            raise PermissionError("Explicit provider/account/terms approval is required")
        if (not math.isfinite(self.approved_credit_budget) or self.approved_credit_budget < 0
                or estimate.estimated_credits is None
                or estimate.estimated_credits > self.approved_credit_budget):
            raise PermissionError("Credit estimate is unknown or exceeds approved budget")


class ListingCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: str = Field(min_length=1, max_length=80)
    source_id: str = Field(min_length=1, max_length=160)
    region_slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    address: str = Field(min_length=1, max_length=300)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    price: int = Field(ge=0)
    beds: int | None = Field(default=None, ge=0)
    baths: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @property
    def identity(self) -> tuple[str, str]:
        return self.provider, self.source_id


def listing_dry_run(
    baseline: Sequence[ListingCandidate], candidates: Sequence[ListingCandidate],
    *, baseline_count: int = FROZEN_BASELINE_COUNT,
) -> dict[str, Any]:
    """Pure version diff. Conflicting duplicate identities block staging.

    No address/geocode heuristics merge records or assign a district. Spatially
    co-located provider IDs are review candidates, since units may be distinct.
    """
    if baseline_count != FROZEN_BASELINE_COUNT:
        raise ValueError("Frozen baseline must remain 4,505 records")
    old = {row.identity: row for row in baseline}
    if len(old) != len(baseline):
        raise ValueError("Baseline identities must be unique")
    incoming: dict[tuple[str, str], ListingCandidate] = {}
    identical_duplicates = 0
    conflicts: set[tuple[str, str]] = set()
    for row in candidates:
        if row.identity in incoming:
            if incoming[row.identity] != row:
                conflicts.add(row.identity)
            else:
                identical_duplicates += 1
        else:
            incoming[row.identity] = row
    added = sorted(incoming.keys() - old.keys())
    removed = sorted(old.keys() - incoming.keys())
    changed = sorted(key for key in incoming.keys() & old.keys() if incoming[key] != old[key])
    payload = [incoming[key].model_dump() for key in sorted(incoming)]
    co_locations: dict[tuple[str, float, float], list[tuple[str, str]]] = {}
    for row in incoming.values():
        key = (" ".join(row.address.casefold().split()), row.longitude, row.latitude)
        co_locations.setdefault(key, []).append(row.identity)
    return {
        "mode": "dry_run", "baseline_count": baseline_count,
        "candidate_count": len(candidates), "deduplicated_count": len(incoming),
        "identical_duplicates": identical_duplicates,
        "conflicting_identities": [list(key) for key in sorted(conflicts)],
        "co_location_review_groups": [sorted(group) for group in co_locations.values() if len(group) > 1],
        "added": added, "removed": removed, "changed": changed,
        "content_hash": sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "staging_eligible": not conflicts,
        "provider_requests_made": False, "baseline_modified": False,
    }


@dataclass(frozen=True)
class PromotionEvidence:
    target: str
    report_hash: str
    promotable: bool
    qa_artifacts: tuple[str, ...]
    golden_passed: bool
    expected_count: int
    actual_count: int
    unassigned_count: int = 0
    ambiguous_count: int = 0
    source_content_hash: str | None = None

    def require_green(self, target: str) -> None:
        if (self.target != target or not re.fullmatch(r"[a-f0-9]{64}", self.report_hash)
                or not self.promotable or not self.golden_passed or not self.qa_artifacts
                or any(not path.startswith("data/reports/qa/") or not path.endswith(".png") for path in self.qa_artifacts)
                or self.expected_count <= 0 or self.expected_count != self.actual_count
                or self.unassigned_count != 0 or self.ambiguous_count != 0):
            raise ValueError("Matching green validation, QA and golden evidence required")


def listing_publish_plan(
    dataset_version: str, estimate: ProviderEstimate, approval: ProviderApproval,
    evidence: PromotionEvidence, *, baseline_count: int,
) -> dict[str, Any]:
    if baseline_count != FROZEN_BASELINE_COUNT:
        raise ValueError("Frozen baseline count changed")
    approval.check(estimate)
    evidence.require_green(dataset_version)
    return {"dataset_version": dataset_version, "validation_report_hash": evidence.report_hash,
            "requires_explicit_publish": True, "published": False,
            "baseline_modified": False,
            "next_action": "Authenticated operator must explicitly publish this validated version in a transaction; no live pointer is changed by this plan."}


# Exact PostGIS membership only; boundaries/overlaps count as ambiguity and block
# publication instead of selecting a convenient district or nearest fallback.
DISTRICT_ASSIGNMENT_SQL = """
WITH matches AS (
 SELECT s.id, count(d.id) AS match_count, min(d.id) AS district_id
 FROM staging.operator_listing_records s
 LEFT JOIN school_districts d ON ST_Covers(d.geom, s.geom)
 WHERE s.dataset_version = %s
 GROUP BY s.id
)
UPDATE staging.operator_listing_records s
SET district_id = CASE WHEN m.match_count = 1 THEN m.district_id ELSE NULL END,
    district_match_count = m.match_count,
    assignment_method = CASE WHEN m.match_count = 1 THEN 'point_in_polygon' ELSE 'unresolved' END
FROM matches m WHERE s.id = m.id
"""


def draft_region_manifest(
    *, slug: str, name: str, county_fips: Sequence[str], layers: Sequence[str],
    official_selection_evidence: str,
) -> dict[str, Any]:
    if not official_selection_evidence.strip():
        raise ValueError("Official county selection evidence is required")
    if any(not re.fullmatch(r"[a-z][a-z0-9_]*",key) for key in layers):
        raise ValueError("Layer keys must name approved manifest identifiers")
    counties = sorted(set(county_fips))
    manifest = RegionManifest(slug=slug, name=name, state_fips=sorted({c[:2] for c in counties}),
                              counties=counties, layers=sorted(set(layers)), anchors=[])
    return {"status": "draft", "manifest": manifest.model_dump(),
            "official_selection_evidence": official_selection_evidence,
            "layer_coverage": {key: "unknown" for key in manifest.layers},
            "listing_coverage": "unknown", "estimated_external_credits": None,
            "estimated_runtime_seconds": None, "auto_enabled_in_explorer": False}


JOB_TRANSITIONS = {
    "draft": {"scaffolding", "failed"},
    "scaffolding": {"coverage", "blocked", "failed"},
    "coverage": {"validated", "blocked", "failed"},
    "blocked": {"coverage", "failed"},
    "validated": {"promoted", "failed"},
    "promoted": set(), "failed": set(),
}


def transition_region_job(
    current: str, desired: str, *, target: str,
    evidence: PromotionEvidence | None = None, explicit_promote: bool = False,
    coverage_complete: bool = False,
) -> str:
    if desired not in JOB_TRANSITIONS.get(current, set()):
        raise ValueError("Invalid asynchronous region-job phase transition")
    if desired in {"validated", "promoted"}:
        if not coverage_complete or evidence is None:
            raise ValueError("Layer coverage and validation evidence are required")
        evidence.require_green(target)
    if desired == "promoted" and not explicit_promote:
        raise ValueError("Promotion must be a separate explicit action")
    return desired


class AttendanceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    school_year: str = Field(pattern=r"^20\d{2}-20\d{2}$")
    grade_min: int = Field(ge=0, le=12)
    grade_max: int = Field(ge=0, le=12)
    status: str
    evidence_kind: str = "official_gis"
    source_url: str
    retrieved_at: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    written_confirmation_reference: str | None = None
    reviewer_user_id: str | None = None

    @field_validator("source_url")
    @classmethod
    def source_is_https(cls, value: str) -> str:
        if urlsplit(value).scheme != "https" or not urlsplit(value).netloc:
            raise ValueError("Evidence must retain an HTTPS official-source reference")
        return value

    def publishable(self) -> bool:
        start, end = map(int, self.school_year.split("-"))
        return (end == start + 1 and self.grade_min <= self.grade_max
                and bool(self.reviewer_user_id)
                and ((self.status == "official" and self.evidence_kind == "official_gis") or (self.status == "written-confirmed"
                     and bool(self.written_confirmation_reference))))


def attendance_assignment_plan(evidence: AttendanceEvidence) -> dict[str, Any]:
    if not evidence.publishable():
        raise ValueError("Reviewed official or written evidence is required; provisional facts cannot assign")
    return {"school_year": evidence.school_year, "grade_min": evidence.grade_min,
            "grade_max": evidence.grade_max, "assignment_method": "point_in_polygon",
            "evidence_hash": evidence.content_sha256, "requires_validated_zone_geometry": True,
            "published": False}


ATTENDANCE_ASSIGNMENT_SQL = """
SELECT z.id, z.school_nces_id, z.status
FROM attendance_zones z
JOIN attendance_evidence e ON e.id = z.evidence_id
WHERE z.district_id = %s AND z.school_year = %s
  AND %s BETWEEN z.grade_min AND z.grade_max
  AND z.status IN ('official', 'written-confirmed')
  AND e.reviewed_by IS NOT NULL
  AND (z.status = 'official' OR e.written_confirmation_reference IS NOT NULL)
  AND ST_Covers(z.geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
ORDER BY z.id
"""


def district_outreach_draft(
    *, district_name: str, sender_identity: str, school_year: str, grade_band: str,
) -> dict[str, Any]:
    if not all(value.strip() for value in (district_name, sender_identity, school_year, grade_band)):
        raise ValueError("Draft requires an identified sender, district, year and grade band")
    if any("\n" in value or "\r" in value for value in (district_name, sender_identity, school_year, grade_band)):
        raise ValueError("Draft fields must be single-line text")
    return {"status": "draft", "recipient": None, "sender_configured": False,
            "send_enabled": False, "call_enabled": False,
            "subject": f"Official attendance boundary information: {school_year}",
            "body": f"Hello {district_name} enrollment or transportation office,\n\n"
                    f"I am {sender_identity}, researching school attendance boundaries for Groundtruth. "
                    f"Could you share your official boundary GIS/download or official locator for {school_year}, "
                    f"covering {grade_band}? If no public file exists, please describe the process for obtaining "
                    "written address, grade and school-year confirmation. We will retain source/date provenance "
                    "and review written evidence before publishing. No student information is included.\n\nThank you."}


def resolve_attendance_matches(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Consume only reviewed/scoped PostGIS matches, preserving ambiguity."""
    if len(rows) != 1:
        return {"status": "unresolved", "school_nces_id": None,
                "reason": "no_covered_zone" if not rows else "overlapping_zones",
                "candidate_zone_count": len(rows)}
    row = rows[0]
    if row["status"] not in {"official", "written-confirmed"}:
        raise ValueError("Unreviewed zone cannot assign a school")
    return {"status": row["status"], "school_nces_id": row["school_nces_id"],
            "zone_id": row["id"], "assignment_method": "point_in_polygon",
            "candidate_zone_count": 1}


def verify_local_promotion_evidence(
    report_path: str, *, target: str, repo_root: Any,
) -> PromotionEvidence:
    """Read actual local report/PNG bytes; never trust a client green flag."""
    from pathlib import Path
    root = Path(repo_root).resolve()
    path = (root / report_path).resolve()
    if not path.is_relative_to(root / "data" / "reports"):
        raise ValueError("Validation report must be under data/reports")
    raw = path.read_bytes()
    report = json.loads(raw)
    checks = report.get("checks", {})
    artifact_paths = tuple(report.get("qa_artifacts", []))
    for artifact in artifact_paths:
        artifact_path = (root / artifact).resolve()
        if not artifact_path.is_relative_to(root / "data" / "reports" / "qa"):
            raise ValueError("QA artifact escaped the report directory")
        if not artifact_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("QA artifact must be an actual PNG")
        from PIL import Image
        with Image.open(artifact_path) as image:
            image.verify()
    evidence = PromotionEvidence(
        target=report["target"], report_hash=sha256(raw).hexdigest(),
        promotable=report.get("promotable") is True, qa_artifacts=artifact_paths,
        golden_passed=checks.get("golden_passed") is True,
        expected_count=checks.get("expected_count", -1), actual_count=checks.get("actual_count", -1),
        unassigned_count=checks.get("unassigned_count", -1), ambiguous_count=checks.get("ambiguous_count", -1),
        source_content_hash=checks.get("source_content_hash"),
    )
    evidence.require_green(target)
    return evidence


def _require_baseline(conn: Any) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM listings")
        if cur.fetchone()[0] != FROZEN_BASELINE_COUNT:
            raise ValueError("Frozen listing baseline count changed")
        cur.execute("SELECT count(*), min(baseline_version) FROM operator_frozen_listing_members")
        count, version = cur.fetchone()
        if count != FROZEN_BASELINE_COUNT or version is None:
            raise ValueError("Register and validate the complete frozen baseline first")
        cur.execute("""SELECT count(*) FROM operator_frozen_listing_members b JOIN listings l ON l.id=b.listing_id
                       WHERE b.source_snapshot IS DISTINCT FROM to_jsonb(l)""")
        if cur.fetchone()[0] != 0:
            raise ValueError("Frozen listing baseline snapshot changed")
    return version


def register_frozen_baseline(
    conn: Any, *, authenticated_user_id: str, version: str,
    report_path: str, repo_root: Any,
) -> dict[str, Any]:
    """Explicit baseline registration; snapshots only, never edits listings.

    Caller owns transaction commit. This operation does not select a new active
    dataset or fetch any listing. Requires on-disk report and QA evidence.
    """
    require_operator(conn, authenticated_user_id)
    evidence = verify_local_promotion_evidence(report_path, target=version, repo_root=repo_root)
    if evidence.actual_count != FROZEN_BASELINE_COUNT:
        raise ValueError("Baseline report must contain exactly 4,505 records")
    from psycopg.types.json import Jsonb
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("LOCK TABLE listings IN SHARE MODE")
            cur.execute("LOCK TABLE operator_frozen_listing_members IN EXCLUSIVE MODE")
            cur.execute("SELECT count(*) FROM listings")
            if cur.fetchone()[0] != FROZEN_BASELINE_COUNT:
                raise ValueError("Frozen listing baseline count changed")
            cur.execute("SELECT count(*) FROM operator_frozen_listing_members")
            if cur.fetchone()[0]:
                existing = _require_baseline(conn)
                if existing != version:
                    raise ValueError("A different immutable baseline is already registered")
                return {"version": version, "registered_count": FROZEN_BASELINE_COUNT, "already_registered": True}
            cur.execute("SELECT to_jsonb(l)::text FROM listings l ORDER BY l.id")
            digest = sha256("\n".join(row[0] for row in cur.fetchall()).encode()).hexdigest()
            cur.execute("""INSERT INTO listing_dataset_versions
              (version,dataset_kind,status,provider,provider_vintage,source_content_hash,
               expected_record_count,validation_report_hash,validation_report,qa_artifacts,golden_passed,
               published_by,published_at)
              VALUES (%s,'frozen_baseline','published','frozen-existing','frozen',%s,4505,%s,%s,%s,true,%s,now())""",
              (version, digest, evidence.report_hash,
               Jsonb({"target": version, "promotable": True, "report_path": report_path}),
               Jsonb(list(evidence.qa_artifacts)), authenticated_user_id))
            cur.execute("""INSERT INTO operator_frozen_listing_members (listing_id,baseline_version,source_snapshot)
                           SELECT l.id,%s,to_jsonb(l) FROM listings l ORDER BY l.id""", (version,))
    return {"version": version, "registered_count": FROZEN_BASELINE_COUNT, "already_registered": False}


def stage_listing_candidates(
    conn: Any, *, authenticated_user_id: str, version: str,
    candidates: Sequence[ListingCandidate], estimate: ProviderEstimate,
    approval: ProviderApproval,
) -> dict[str, Any]:
    """Stage supplied records after approval; performs no provider request."""
    require_operator(conn, authenticated_user_id)
    approval.check(estimate)
    if not candidates or any(row.provider != estimate.provider for row in candidates):
        raise ValueError("Candidate provider must match the approved nonempty import")
    from dataclasses import asdict
    from psycopg.types.json import Jsonb
    with conn.transaction():
        _require_baseline(conn)
        result = listing_dry_run([], candidates)
        if not result["staging_eligible"]:
            raise ValueError("Conflicting duplicate listing identities block staging")
        unique = {row.identity: row for row in candidates}
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO listing_dataset_versions
              (version,dataset_kind,status,provider,provider_vintage,provider_approval,provider_estimate,source_content_hash,expected_record_count)
              VALUES (%s,'refresh','draft',%s,%s,%s,%s,%s,%s)""",
              (version, estimate.provider, estimate.vintage, Jsonb(asdict(approval)), Jsonb(asdict(estimate)), result["content_hash"], len(unique)))
            cur.executemany("""INSERT INTO staging.operator_listing_records
              (dataset_version,provider,source_id,region_slug,record,geom)
              VALUES (%s,%s,%s,%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326))""",
              [(version,row.provider,row.source_id,row.region_slug,Jsonb(row.model_dump()),row.longitude,row.latitude)
               for _, row in sorted(unique.items())])
            cur.execute(DISTRICT_ASSIGNMENT_SQL, (version,))
            cur.execute("UPDATE listing_dataset_versions SET status='staged' WHERE version=%s", (version,))
            cur.execute("""SELECT count(*),count(*) FILTER (WHERE district_match_count=0),
                           count(*) FILTER (WHERE district_match_count>1)
                           FROM staging.operator_listing_records WHERE dataset_version=%s""", (version,))
            count, unresolved, ambiguous = cur.fetchone()
    return {"version": version, "staged_count": count, "unassigned_count": unresolved,
            "ambiguous_count": ambiguous, "provider_requests_made": False, "published": False}


def publish_listing_dataset(
    conn: Any, *, authenticated_user_id: str, version: str,
    report_path: str, repo_root: Any, explicit_publish: bool,
) -> dict[str, Any]:
    """Separate intentional publish command selecting an immutable version.

    Public Explorer continues to read its existing frozen table. This selects
    only the private operator dataset pointer; it never overwrites listings.
    """
    if not explicit_publish:
        raise ValueError("A separate explicit publish command is required")
    require_operator(conn, authenticated_user_id)
    evidence = verify_local_promotion_evidence(report_path, target=version, repo_root=repo_root)
    from psycopg.types.json import Jsonb
    with conn.transaction():
        _require_baseline(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT status,provider,provider_vintage,provider_approval,expected_record_count,provider_estimate,source_content_hash FROM listing_dataset_versions WHERE version=%s AND dataset_kind='refresh' FOR UPDATE", (version,))
            row = cur.fetchone()
            if row is None or row[0] != "staged":
                raise ValueError("Only an explicitly staged refresh can be published")
            _, provider, vintage, approval_input, expected, estimate_input, source_hash = row
            approval = ProviderApproval(**approval_input)
            approval.check(ProviderEstimate(**estimate_input))
            if evidence.source_content_hash != source_hash:
                raise ValueError("Validation report does not match staged source content")
            cur.execute("LOCK TABLE staging.operator_listing_records IN SHARE MODE")
            cur.execute("SELECT record FROM staging.operator_listing_records WHERE dataset_version=%s ORDER BY provider,source_id", (version,))
            current_payload = [ListingCandidate.model_validate(row[0]).model_dump() for row in cur.fetchall()]
            current_hash = sha256(json.dumps(current_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if current_hash != source_hash:
                raise ValueError("Staged records changed after the source snapshot was hashed")

            # Recompute from source geometry immediately before publishing; no
            # manually supplied assignment can survive this intentional step.
            cur.execute(DISTRICT_ASSIGNMENT_SQL, (version,))
            cur.execute("""SELECT count(*),count(*) FILTER (WHERE district_match_count=0),
                count(*) FILTER (WHERE district_match_count<>1 OR district_id IS NULL),
                count(*) FILTER (WHERE ST_SRID(geom)<>4326 OR NOT ST_IsValid(geom))
                FROM staging.operator_listing_records WHERE dataset_version=%s""", (version,))
            actual, unresolved, bad_assignment, bad_geometry = cur.fetchone()
            if expected != evidence.actual_count or actual != expected or unresolved or bad_assignment or bad_geometry:
                raise ValueError("Staged count, geometry or deterministic assignments failed revalidation")
            cur.execute("""UPDATE listing_dataset_versions SET status='validated',validation_report_hash=%s,
              validation_report=%s,qa_artifacts=%s,golden_passed=true WHERE version=%s""",
              (evidence.report_hash, Jsonb({"target": version, "promotable": True, "report_path": report_path}),
               Jsonb(list(evidence.qa_artifacts)), version))
            cur.execute("""UPDATE listing_dataset_versions SET status='published',published_by=%s,published_at=now()
                           WHERE version=%s""", (authenticated_user_id, version))
            cur.execute("""INSERT INTO operator_active_listing_dataset (singleton,dataset_version,selected_by)
                VALUES (true,%s,%s) ON CONFLICT (singleton) DO UPDATE
                SET dataset_version=EXCLUDED.dataset_version,selected_by=EXCLUDED.selected_by,selected_at=now()""",
                (version, authenticated_user_id))
    return {"version": version, "published": True, "baseline_modified": False,
            "public_explorer_changed": False, "validation_report_hash": evidence.report_hash}


def enqueue_region_job(conn: Any, *, authenticated_user_id: str, draft: Mapping[str, Any]) -> int:
    require_operator(conn, authenticated_user_id)
    if draft.get("status") != "draft" or not draft.get("official_selection_evidence"):
        raise ValueError("A reviewed official-selection draft is required")
    manifest = RegionManifest.model_validate(draft["manifest"])
    from psycopg.types.json import Jsonb
    with conn.cursor() as cur:
        cur.execute("SELECT EXISTS(SELECT 1 FROM regions WHERE region_group=%s)",(manifest.slug,))
        if cur.fetchone()[0]:
            raise ValueError("Region expansion requires a new slug; existing regions cannot be overwritten")
        cur.execute("""INSERT INTO operator_jobs (kind,target,requested_by,input_manifest)
                       VALUES ('region_expansion',%s,%s,%s) RETURNING id""",
                    (manifest.slug, authenticated_user_id, Jsonb(dict(draft))))
        return cur.fetchone()[0]


def claim_region_job(
    conn: Any, *, authenticated_user_id: str, worker_id: str, lease_seconds: int = 300,
    include_validated: bool = False, job_id: int | None = None,
) -> dict[str, Any] | None:
    require_operator(conn, authenticated_user_id)
    if not worker_id or not 10 <= lease_seconds <= 3600:
        raise ValueError("Worker identity and bounded lease are required")
    with conn.cursor() as cur:
        cur.execute("""WITH available AS (
          SELECT id FROM operator_jobs WHERE kind='region_expansion'
            AND (phase IN ('draft','scaffolding','coverage') OR (%s AND phase='validated'))
            AND (%s::bigint IS NULL OR id=%s::bigint)
            AND (lease_expires_at IS NULL OR lease_expires_at < clock_timestamp())
          ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1
        ) UPDATE operator_jobs j SET lease_owner=%s,
          lease_expires_at=now()+make_interval(secs => %s), attempts=j.attempts+1,updated_at=now()
          FROM available a WHERE j.id=a.id
          RETURNING j.id,j.target,j.phase,j.input_manifest""", (include_validated, job_id, job_id, worker_id, lease_seconds))
        row = cur.fetchone()
    return None if row is None else {"id": row[0], "target": row[1], "phase": row[2], "input_manifest": row[3]}


def advance_region_job(
    conn: Any, *, authenticated_user_id: str, job_id: int, worker_id: str,
    desired: str, evidence: PromotionEvidence | None = None,
    explicit_promote: bool = False, coverage_report: Mapping[str, Any] | None = None,
) -> str:
    require_operator(conn, authenticated_user_id)
    from psycopg.types.json import Jsonb
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("SELECT target,phase,lease_owner,lease_expires_at>clock_timestamp() FROM operator_jobs WHERE id=%s FOR UPDATE", (job_id,))
            row = cur.fetchone()
            if row is None or row[2] != worker_id or row[3] is not True:
                raise ValueError("A current worker lease is required")
            next_phase = transition_region_job(row[1], desired, target=row[0], evidence=evidence,
                explicit_promote=explicit_promote,
                coverage_complete=coverage_report is not None and coverage_report.get("complete") is True)
            cur.execute("""UPDATE operator_jobs SET phase=%s,coverage_report=COALESCE(%s,coverage_report),
              validation_report_hash=COALESCE(%s,validation_report_hash),
              qa_artifacts=COALESCE(%s,qa_artifacts),golden_passed=golden_passed OR %s,
              lease_owner=NULL,lease_expires_at=NULL,updated_at=now() WHERE id=%s""",
              (next_phase, Jsonb(dict(coverage_report)) if coverage_report is not None else None,
               evidence.report_hash if evidence else None, Jsonb(list(evidence.qa_artifacts)) if evidence else None,
               evidence.golden_passed if evidence else False, job_id))
    return next_phase


def release_region_job(conn: Any, *, authenticated_user_id: str, job_id: int, worker_id: str) -> None:
    require_operator(conn, authenticated_user_id)
    with conn.cursor() as cur:
        cur.execute("""UPDATE operator_jobs SET lease_owner=NULL,lease_expires_at=NULL,updated_at=now()
                       WHERE id=%s AND lease_owner=%s""", (job_id,worker_id))


def retry_blocked_region_job(conn: Any, *, authenticated_user_id: str, job_id: int) -> None:
    require_operator(conn, authenticated_user_id)
    with conn.cursor() as cur:
        cur.execute("""UPDATE operator_jobs SET phase='coverage',lease_owner=NULL,lease_expires_at=NULL,updated_at=now()
                       WHERE id=%s AND phase='blocked' AND (lease_expires_at IS NULL OR lease_expires_at<now())""", (job_id,))
        if cur.rowcount != 1:
            raise ValueError("Only an unleased blocked job can be explicitly retried")


def region_layer_coverage(repo_root: Any, manifest: RegionManifest, *, required_staged_fingerprint: str | None = None) -> dict[str, Any]:
    """Inventory actual report/QA evidence; source-manifest presence alone is not coverage."""
    from pathlib import Path
    root = Path(repo_root)
    layers: dict[str, Any] = {}
    for key in manifest.layers:
        if not re.fullmatch(r"[a-z][a-z0-9_]*",key):
            layers[key]={"complete":False,"reason":"invalid_layer_key"}
            continue
        path = root / "data" / "reports" / f"layer_{key}_{manifest.slug}_latest.json"
        qa = root / "data" / "reports" / "qa" / f"{key}_{manifest.slug}.png"
        manifest_path = root / "pipeline" / "manifests" / "layers" / f"{key}.yaml"
        reason = "missing_source_packet" if not manifest_path.is_file() else "missing_validation_report"
        entry: dict[str, Any] = {"complete": False,"reason":reason}
        if path.is_file() and manifest_path.is_file():
            raw = path.read_bytes()
            report = json.loads(raw)
            source_matches = report.get("target") == f"{key}:{manifest.slug}"
            checks=report.get("checks",{})
            if required_staged_fingerprint is not None:
                source_matches = source_matches and checks.get("region_read_context")=="staging" and checks.get("staged_source_fingerprint")==required_staged_fingerprint
            accepted = source_matches and report.get("promotable") is True and qa.is_file()
            if accepted:
                from PIL import Image
                try:
                    with Image.open(qa) as image:
                        image.verify()
                except Exception:
                    accepted = False
            entry = {"complete": accepted,"reason": None if accepted else "validation_or_qa_not_green",
                     "report_sha256":sha256(raw).hexdigest(),"report_target":report.get("target"),
                     "requested_grain":checks.get("requested_grain"),"listing_scope_status":checks.get("listing_scope_status"),
                     "qa_artifact":str(qa.relative_to(root)) if qa.is_file() else None}
        layers[key] = entry
    # Expansion does not add Explorer listings. Listing coverage remains a
    # separate paid-provider gate, never a reason to fetch RentCast here.
    return {"complete": bool(layers) and all(entry["complete"] for entry in layers.values()),
            "layers":layers,"listing_coverage":"frozen_dataset_only","provider_requests_made":False}


def _staged_region_fingerprint(conn: Any, target: str) -> tuple[str, int]:
    digest = sha256()
    count = 0
    # Fixed internal table names only. Hash all geometry and overlap inputs,
    # not just the polygon count, so revalidation cannot bless a stale join.
    for table in ("region_scaffold_regions","region_scaffold_school_districts","region_scaffold_overlaps"):
        with conn.cursor() as cur:
            cur.execute(f"SELECT to_jsonb(s)::text FROM staging.{table} s WHERE region_group=%s ORDER BY to_jsonb(s)::text",(target,))
            rows = cur.fetchall()
        digest.update(table.encode())
        for row in rows:
            digest.update(row[0].encode())
            digest.update(b"\n")
        if table == "region_scaffold_regions":
            count = len(rows)
    return digest.hexdigest(),count


def _operator_golden(repo_root: Any) -> bool:
    from pathlib import Path
    import subprocess
    root = Path(repo_root)
    result = subprocess.run([str(root / "pipeline/.venv/bin/python"),"-m","pytest","tests/test_golden.py",
                             "-q","--tb=no","-o","addopts="],cwd=root/"pipeline",capture_output=True,timeout=120)
    return result.returncode == 0


def _stage_region_with_evidence(conn: Any, manifest_path: Any, repo_root: Any) -> str:
    """Use existing official region importer, then render staged QA before promotion."""
    from pathlib import Path
    import geopandas as gpd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from gt.region import scaffold_region_add
    report, _ = scaffold_region_add(Path(manifest_path))
    if not report.promotable:
        raise ValueError("Region scaffold validation is not promotable")
    frame = gpd.read_postgis("SELECT geom FROM staging.region_scaffold_regions WHERE region_group=%s AND region_type='census_tract'",
                            conn,params=(report.target,),geom_col="geom")
    root = Path(repo_root)
    qa = root/"data/reports/qa"/f"operator_region_{report.target}.png"
    qa.parent.mkdir(parents=True,exist_ok=True)
    figure,axes = plt.subplots(figsize=(9,9))
    try:
        frame.plot(ax=axes,facecolor="#d1fae5",edgecolor="#166534",linewidth=.25)
        axes.set_title(f"{report.target}: staged official census tracts")
        axes.set_axis_off()
        figure.savefig(qa,dpi=160,bbox_inches="tight")
    finally:
        plt.close(figure)
    fingerprint,count = _staged_region_fingerprint(conn,report.target)
    golden = _operator_golden(root)
    payload = report.as_dict()
    payload["qa_artifacts"] = [str(qa.relative_to(root))]
    payload["checks"].update({"golden_passed":golden,"source_content_hash":fingerprint,
        "expected_count":count,"actual_count":count,"unassigned_count":0,"ambiguous_count":0})
    payload["promotable"] = report.promotable and golden and count>0
    path = root/"data/reports"/f"operator_region_{report.target}_latest.json"
    path.write_text(json.dumps(payload,indent=2,sort_keys=True))
    if not payload["promotable"]:
        raise ValueError("Region scaffold/golden evidence failed")
    return str(path.relative_to(root))


def run_region_job_once(
    conn: Any, *, authenticated_user_id: str, worker_id: str, repo_root: Any,
    allow_official_scaffold: bool = False, explicit_promote: bool = False, job_id: int | None = None,
    run_approved_layers: bool = False,
) -> dict[str, Any]:
    """Claim and execute one persisted phase; owns commits for lease visibility.

    Never fetches listings. An explicit run_approved_layers option runs one
    approved tract layer in a lease-scoped child; missing reports otherwise
    block coverage. No geometry is promoted before matching validation/QA.
    """
    from pathlib import Path
    import yaml
    root = Path(repo_root)
    if explicit_promote and job_id is None:
        raise ValueError("Explicit region promotion requires a specific job ID")
    job = claim_region_job(conn,authenticated_user_id=authenticated_user_id,worker_id=worker_id,lease_seconds=3600,
                           include_validated=explicit_promote,job_id=job_id)
    conn.commit()
    if job is None:
        return {"status":"idle"}
    job_id,target,phase = job["id"],job["target"],job["phase"]
    manifest = RegionManifest.model_validate(job["input_manifest"]["manifest"])
    manifest_path = root/"data/reports/operator"/f"region-job-{job_id}.yaml"
    manifest_path.parent.mkdir(parents=True,exist_ok=True)
    manifest_path.write_text(yaml.safe_dump(manifest.model_dump(),sort_keys=False))
    report_path = f"data/reports/operator_region_{target}_latest.json"
    try:
        if phase == "draft":
            desired = "scaffolding"
            kwargs: dict[str, Any] = {}
        elif phase == "scaffolding":
            if not allow_official_scaffold:
                release_region_job(conn,authenticated_user_id=authenticated_user_id,job_id=job_id,worker_id=worker_id)
                conn.commit()
                return {"id":job_id,"status":"awaiting_official_scaffold_command"}
            _stage_region_with_evidence(conn,manifest_path,root)
            desired,kwargs = "coverage",{}
        elif phase == "coverage":
            fingerprint,_=_staged_region_fingerprint(conn,target)
            coverage = region_layer_coverage(root,manifest,required_staged_fingerprint=fingerprint)
            if coverage["complete"]:
                evidence = verify_local_promotion_evidence(report_path,target=target,repo_root=root)
                desired,kwargs = "validated",{"coverage_report":coverage,"evidence":evidence}
            elif run_approved_layers:
                missing=next((key for key in manifest.layers if not coverage["layers"][key]["complete"]),None)
                if missing is None:
                    raise ValueError("A region job requires at least one approved layer")
                succeeded=_run_scoped_layer_subprocess(root,region_slug=target,job_id=job_id,worker_id=worker_id,
                    actor_user_id=authenticated_user_id,layer=missing)
                coverage=region_layer_coverage(root,manifest,required_staged_fingerprint=fingerprint)
                if succeeded:
                    _record_region_coverage_progress(conn,authenticated_user_id=authenticated_user_id,
                        job_id=job_id,worker_id=worker_id,coverage=coverage)
                    conn.commit()
                    return {"id":job_id,"phase":"coverage","layer_attempted":missing,"layer_staged":True,
                            "promoted":False,"provider_listing_requests_made":False}
                desired,kwargs="blocked",{"coverage_report":coverage}
            else:
                desired,kwargs = "blocked",{"coverage_report":coverage}
        elif phase == "validated":
            if not explicit_promote:
                release_region_job(conn,authenticated_user_id=authenticated_user_id,job_id=job_id,worker_id=worker_id)
                conn.commit()
                return {"id":job_id,"status":"awaiting_explicit_promote"}
            evidence = verify_local_promotion_evidence(report_path,target=target,repo_root=root)
            with conn.cursor() as cur:
                cur.execute("SELECT validation_report_hash,coverage_report FROM operator_jobs WHERE id=%s",(job_id,))
                validated_hash,validated_coverage = cur.fetchone()
                if validated_hash != evidence.report_hash:
                    raise ValueError("Region report changed after job validation")
            coverage = region_layer_coverage(root,manifest,required_staged_fingerprint=evidence.source_content_hash)
            fingerprint,count = _staged_region_fingerprint(conn,target)
            if not coverage["complete"] or coverage != validated_coverage or evidence.source_content_hash != fingerprint or count != evidence.actual_count:
                raise ValueError("Staged source/coverage changed after validation")
            from gt.region import promote_region
            from gt.layers.runner import promote_layer
            promote_region(target)
            for key in manifest.layers:
                promote_layer(root/"pipeline/manifests/layers"/f"{key}.yaml",target)
            if not _operator_golden(root):
                raise ValueError("Post-promote golden verification failed")
            desired,kwargs = "promoted",{"coverage_report":coverage,"evidence":evidence,"explicit_promote":True}
        else:
            raise ValueError("Claimed job has unsupported phase")
        result = advance_region_job(conn,authenticated_user_id=authenticated_user_id,job_id=job_id,
                                    worker_id=worker_id,desired=desired,**kwargs)
        conn.commit()
        return {"id":job_id,"phase":result,"provider_listing_requests_made":False}
    except Exception:
        conn.rollback()
        # Keep error payloads credential/profile-free. External source errors
        # belong in local operator diagnostics, never public clients.
        try:
            advance_region_job(conn,authenticated_user_id=authenticated_user_id,job_id=job_id,
                               worker_id=worker_id,desired="failed")
            conn.commit()
        except Exception:
            conn.rollback()
        raise RuntimeError("Operator region phase failed; inspect local validation artifacts before retry") from None


def validate_listing_dataset(conn: Any, *, authenticated_user_id: str, version: str, repo_root: Any) -> dict[str, Any]:
    """Deterministic staged validation and actual local spatial QA; no publish."""
    from pathlib import Path
    import geopandas as gpd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    require_operator(conn,authenticated_user_id)
    root = Path(repo_root)
    with conn.transaction():
        _require_baseline(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT status,expected_record_count,source_content_hash FROM listing_dataset_versions WHERE version=%s FOR UPDATE",(version,))
            metadata = cur.fetchone()
            if metadata is None or metadata[0] != "staged":
                raise ValueError("Only a staged dataset version can be validated")
            cur.execute(DISTRICT_ASSIGNMENT_SQL,(version,))
            cur.execute("""SELECT record,district_match_count,district_id,ST_SRID(geom),ST_IsValid(geom)
                           FROM staging.operator_listing_records WHERE dataset_version=%s ORDER BY provider,source_id""",(version,))
            records = cur.fetchall()
        payload = [ListingCandidate.model_validate(row[0]).model_dump() for row in records]
        source_hash = sha256(json.dumps(payload,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
        unassigned = sum(row[1]==0 for row in records)
        ambiguous = sum(row[1]>1 for row in records)
        bad = sum(row[2] is None or row[3]!=4326 or not row[4] for row in records)
        frame = gpd.read_postgis("SELECT geom FROM staging.operator_listing_records WHERE dataset_version=%s",conn,params=(version,),geom_col="geom")
        qa = root/"data/reports/qa"/f"operator_listings_{sha256(version.encode()).hexdigest()[:16]}.png"
        qa.parent.mkdir(parents=True,exist_ok=True)
        figure,axes = plt.subplots(figsize=(9,9))
        try:
            if len(frame):
                frame.plot(ax=axes,color="#2563eb",markersize=5)
            axes.set_title(f"Staged listing dataset: {version}")
            axes.set_axis_off()
            figure.savefig(qa,dpi=160,bbox_inches="tight")
        finally:
            plt.close(figure)
        # Independent golden connection observes only the unchanged public
        # baseline. Staging assignment/geometry checks are local above.
        golden = _operator_golden(root)
        checks = {"expected_count":metadata[1],"actual_count":len(records),"unassigned_count":unassigned,
                  "ambiguous_count":ambiguous,"invalid_assignment_or_geometry_count":bad,
                  "source_content_hash":source_hash,"golden_passed":golden}
        promotable = (len(records)>0 and len(records)==metadata[1] and source_hash==metadata[2]
                      and not unassigned and not ambiguous and not bad and golden)
        report = {"report_type":"operator_listing_dataset","target":version,"status":"staged",
                  "promotable":promotable,"checks":checks,"qa_artifacts":[str(qa.relative_to(root))]}
        path = root/"data/reports"/f"operator_listing_{sha256(version.encode()).hexdigest()[:16]}.json"
        path.write_text(json.dumps(report,indent=2,sort_keys=True))
    return {"version":version,"report_path":str(path.relative_to(root)),"promotable":promotable,"published":False}


def _record_region_coverage_progress(conn: Any, *, authenticated_user_id: str, job_id: int, worker_id: str, coverage: Mapping[str,Any]) -> None:
    require_operator(conn,authenticated_user_id)
    from psycopg.types.json import Jsonb
    with conn.cursor() as cur:
        cur.execute("""UPDATE operator_jobs SET coverage_report=%s,lease_owner=NULL,lease_expires_at=NULL,updated_at=clock_timestamp()
          WHERE id=%s AND phase='coverage' AND lease_owner=%s AND lease_expires_at>clock_timestamp()""",
                    (Jsonb(dict(coverage)),job_id,worker_id))
        if cur.rowcount!=1:
            raise PermissionError("Layer result cannot persist after worker lease loss")


def _run_scoped_layer_subprocess(root: Any, *, region_slug: str, job_id: int, worker_id: str, actor_user_id: str, layer: str) -> bool:
    import subprocess
    from gt.region_read_context import StagedRegionContext,staged_worker_environment,renew_staged_worker_lease
    env=staged_worker_environment(os.environ,region_slug=region_slug,job_id=job_id,worker_id=worker_id,actor_user_id=actor_user_id)
    context=StagedRegionContext(region_slug,job_id,worker_id,actor_user_id)
    process=subprocess.Popen([str(root/"pipeline/.venv/bin/python"),"-m","gt.operator_layer_worker","--layer",layer,"--region",region_slug],
        cwd=root/"pipeline",env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        while True:
            try:
                return process.wait(timeout=30)==0
            except subprocess.TimeoutExpired:
                # Separate short transaction renews only this matching active
                # lease. Role revocation or lease loss stops the child; fresh
                # checks inside reducers also guard the actual staging writes.
                with psycopg.connect(database_url(),autocommit=True,connect_timeout=10,
                                     options="-c statement_timeout=5000") as heartbeat:
                    renew_staged_worker_lease(heartbeat,context,seconds=300)
    except Exception:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        return False
