from dataclasses import replace

import pytest
from pydantic import ValidationError

from gt.operator import (
    ATTENDANCE_ASSIGNMENT_SQL, DISTRICT_ASSIGNMENT_SQL,
    AttendanceEvidence, ListingCandidate, PromotionEvidence, ProviderApproval, ProviderEstimate,
    attendance_assignment_plan, district_outreach_draft, draft_region_manifest,
    listing_dry_run, listing_publish_plan, require_operator, transition_region_job, resolve_attendance_matches,
)


def candidate(source_id="1", **changes):
    return ListingCandidate(provider="fixture", source_id=source_id, region_slug="pa-mainline",
                            address="123 Example Road", longitude=-75, latitude=40, price=500000, **changes)


def green(target="refresh-v1"):
    return PromotionEvidence(target=target, report_hash="a" * 64, promotable=True,
                             qa_artifacts=("data/reports/qa/operator.png",), golden_passed=True,
                             expected_count=2, actual_count=2)


def estimate():
    return ProviderEstimate("fixture", "approved-area", "2026-10-18", 2, 2, "fixture credit schedule")


def approval():
    return ProviderApproval("fixture", "account-ref", "terms-review-ref", 2, "verified-admin", "2026-10-18")


def test_operator_access_needs_server_flag_and_database_role(monkeypatch):
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, query, params): self.params = params
        def fetchone(self): return self.result
    class Conn:
        def cursor(self): return cursor
    cursor = Cursor()
    cursor.result = (1,)
    with pytest.raises(PermissionError): require_operator(Conn(), "u1")
    monkeypatch.setenv("GROUNDTRUTH_OPERATOR_ENABLED", "true")
    require_operator(Conn(), "u1")
    assert cursor.params == ("u1",)
    cursor.result = None
    with pytest.raises(PermissionError): require_operator(Conn(), "u1")
    with pytest.raises(PermissionError): require_operator(Conn(), None)


def test_dry_run_dedupes_without_merging_units_or_changing_baseline():
    first = candidate()
    second = candidate("2")
    changed = first.model_copy(update={"price": 510000})
    result = listing_dry_run([first, candidate("gone")], [changed, second, second])
    assert result["changed"] == [("fixture", "1")]
    assert result["added"] == [("fixture", "2")]
    assert result["removed"] == [("fixture", "gone")]
    assert result["identical_duplicates"] == 1
    assert result["deduplicated_count"] == 2
    assert len(result["co_location_review_groups"]) == 1
    assert result["staging_eligible"]
    assert not result["baseline_modified"] and not result["provider_requests_made"]
    assert result["content_hash"] == listing_dry_run([first, candidate("gone")], [second, changed])["content_hash"]
    assert first.price == 500000


def test_conflicting_duplicate_ids_block_staging_and_invalid_coordinates_reject():
    row = candidate()
    result = listing_dry_run([], [row, row.model_copy(update={"price": 0})])
    assert not result["staging_eligible"]
    assert result["conflicting_identities"] == [["fixture", "1"]]
    with pytest.raises(ValueError): listing_dry_run([], [], baseline_count=4504)
    with pytest.raises(ValidationError): candidate().model_validate({**candidate().model_dump(), "longitude": float("nan")})


def test_publish_requires_provider_budget_and_matching_green_report():
    plan = listing_publish_plan("refresh-v1", estimate(), approval(), green(), baseline_count=4505)
    assert plan["requires_explicit_publish"] and not plan["published"]
    with pytest.raises(PermissionError):
        listing_publish_plan("refresh-v1", replace(estimate(), estimated_credits=None), approval(), green(), baseline_count=4505)
    with pytest.raises(PermissionError):
        listing_publish_plan("refresh-v1", estimate(), replace(approval(), approved_credit_budget=1), green(), baseline_count=4505)
    with pytest.raises(PermissionError):
        listing_publish_plan("refresh-v1", estimate(), replace(approval(), terms_evidence=""), green(), baseline_count=4505)
    for invalid in (replace(green(), promotable=False), replace(green(), golden_passed=False),
                    replace(green(), qa_artifacts=()), replace(green(), target="other"),
                    replace(green(), unassigned_count=1), replace(green(), ambiguous_count=1),
                    replace(green(), actual_count=1)):
        with pytest.raises(ValueError):
            listing_publish_plan("refresh-v1", estimate(), approval(), invalid, baseline_count=4505)


def test_region_manifest_is_draft_with_unknown_coverage():
    result = draft_region_manifest(slug="new-area", name="New Area", county_fips=["42091", "42029", "42091"],
                                   layers=["tree_canopy_pct"], official_selection_evidence="official-county-selection")
    assert result["manifest"]["state_fips"] == ["42"]
    assert result["manifest"]["counties"] == ["42029", "42091"]
    assert result["layer_coverage"] == {"tree_canopy_pct": "unknown"}
    assert not result["auto_enabled_in_explorer"]
    with pytest.raises(ValidationError):
        draft_region_manifest(slug="new-area", name="New Area", county_fips=["ZIP"], layers=[], official_selection_evidence="x")


def test_async_workflow_cannot_skip_coverage_qa_or_explicit_promote():
    assert transition_region_job("draft", "scaffolding", target="area") == "scaffolding"
    assert transition_region_job("scaffolding", "coverage", target="area") == "coverage"
    with pytest.raises(ValueError): transition_region_job("draft", "promoted", target="area")
    with pytest.raises(ValueError): transition_region_job("coverage", "validated", target="area", evidence=green("area"))
    assert transition_region_job("coverage", "validated", target="area", evidence=green("area"), coverage_complete=True) == "validated"
    with pytest.raises(ValueError):
        transition_region_job("validated", "promoted", target="area", evidence=green("area"), coverage_complete=True)
    assert transition_region_job("validated", "promoted", target="area", evidence=green("area"), coverage_complete=True, explicit_promote=True) == "promoted"


def evidence(**changes):
    return AttendanceEvidence(**{
        "school_year": "2026-2027", "grade_min": 0, "grade_max": 5, "status": "official",
        "source_url": "https://district.example/official-zones", "retrieved_at": "2026-10-18",
        "content_sha256": "b" * 64, "reviewer_user_id": "u1", **changes,
    })


def test_attendance_requires_specific_reviewed_year_grade_and_evidence():
    plan = attendance_assignment_plan(evidence())
    assert plan["assignment_method"] == "point_in_polygon" and not plan["published"]
    for invalid in (evidence(status="provisional"), evidence(status="unresolved"),
                    evidence(reviewer_user_id=None), evidence(school_year="2026-2028"),
                    evidence(grade_min=9, grade_max=5), evidence(status="written-confirmed"),
                    evidence(evidence_kind="official_locator")):
        with pytest.raises(ValueError): attendance_assignment_plan(invalid)
    assert evidence(status="written-confirmed", written_confirmation_reference="written-zone-boundary-file").publishable()
    with pytest.raises(ValidationError): evidence(source_url="file:///unverified")


def test_spatial_queries_use_exact_cover_and_no_inference():
    assert "ST_Covers" in DISTRICT_ASSIGNMENT_SQL and "match_count = 1" in DISTRICT_ASSIGNMENT_SQL
    assert "ST_Covers" in ATTENDANCE_ASSIGNMENT_SQL and "school_year = %s" in ATTENDANCE_ASSIGNMENT_SQL
    assert "BETWEEN z.grade_min AND z.grade_max" in ATTENDANCE_ASSIGNMENT_SQL
    assert "nearest" not in DISTRICT_ASSIGNMENT_SQL.lower()


def test_outreach_draft_is_identified_and_cannot_send():
    draft = district_outreach_draft(district_name="Example District", sender_identity="Alex, Groundtruth researcher",
                                    school_year="2026-2027", grade_band="K–5")
    assert "Groundtruth researcher" in draft["body"]
    assert "official boundary" in draft["body"]
    assert draft["recipient"] is None
    assert not draft["send_enabled"] and not draft["call_enabled"]
    with pytest.raises(ValueError):
        district_outreach_draft(district_name="Example\nBcc: x", sender_identity="Alex", school_year="2026", grade_band="K")


def test_attendance_overlap_and_missing_zones_remain_unresolved():
    row = {"id": 1, "school_nces_id": "school-1", "status": "official"}
    assert resolve_attendance_matches([row])["school_nces_id"] == "school-1"
    assert resolve_attendance_matches([])["reason"] == "no_covered_zone"
    assert resolve_attendance_matches([row, {**row, "id": 2}])["reason"] == "overlapping_zones"
    with pytest.raises(ValueError):
        resolve_attendance_matches([{**row, "status": "provisional"}])


def test_local_evidence_reads_real_report_and_png_files(tmp_path):
    import json
    from gt.operator import verify_local_promotion_evidence
    reports = tmp_path / "data/reports"
    qa = reports / "qa"
    qa.mkdir(parents=True)
    from PIL import Image
    Image.new("RGB", (2, 2)).save(qa / "fixture.png")
    report = {"target": "fixture-version", "promotable": True,
              "qa_artifacts": ["data/reports/qa/fixture.png"],
              "checks": {"golden_passed": True, "expected_count": 1, "actual_count": 1,
                         "unassigned_count": 0, "ambiguous_count": 0}}
    (reports / "fixture.json").write_text(json.dumps(report))
    evidence_result = verify_local_promotion_evidence("data/reports/fixture.json", target="fixture-version", repo_root=tmp_path)
    assert evidence_result.actual_count == 1
    with pytest.raises(ValueError):
        verify_local_promotion_evidence("data/reports/fixture.json", target="other", repo_root=tmp_path)
    (qa / "fixture.png").write_text("not-a-png")
    with pytest.raises(ValueError):
        verify_local_promotion_evidence("data/reports/fixture.json", target="fixture-version", repo_root=tmp_path)


@pytest.mark.skipif(__import__("os").environ.get("GT_OPERATOR_DB_TESTS") != "1", reason="Explicit rollback-only Neon integration opt-in")
def test_operator_live_migration_registration_publish_and_queue_rollback(tmp_path, monkeypatch):
    """All DDL, user/role fixtures, snapshots and private pointer roll back."""
    import json
    import os
    from pathlib import Path
    from uuid import uuid4
    import psycopg
    from gt.operator import (
        advance_region_job, claim_region_job, enqueue_region_job,
        publish_listing_dataset, register_frozen_baseline, stage_listing_candidates, validate_listing_dataset,
    )
    monkeypatch.setenv("GROUNDTRUTH_OPERATOR_ENABLED", "true")
    root = Path(__file__).resolve().parents[2]
    user_id = "operator-rollback-" + uuid4().hex
    version = "rollback-refresh-" + uuid4().hex
    baseline_version = "rollback-baseline-" + uuid4().hex
    reports = tmp_path / "data/reports"
    qa = reports / "qa"
    qa.mkdir(parents=True)
    # This intentionally synthetic evidence is confined to the rollback test.
    from PIL import Image
    Image.new("RGB", (2, 2)).save(qa / "fixture.png")
    def write_report(target, count, filename, source_hash=None):
        checks = {"golden_passed": True, "expected_count": count, "actual_count": count,
                  "unassigned_count": 0, "ambiguous_count": 0, "source_content_hash": source_hash}
        (reports / filename).write_text(json.dumps({"target": target,"promotable": True,
            "qa_artifacts": ["data/reports/qa/fixture.png"],"checks":checks}))
        return "data/reports/" + filename
    # Verify live golden BEFORE acquiring migration DDL locks. Inside this
    # rollback transaction use the verified result; a second connection cannot
    # read listings while DROP/CREATE TRIGGER locks are still uncommitted.
    import gt.operator as operator_module
    golden_result = operator_module._operator_golden(root)
    assert golden_result
    monkeypatch.setattr(operator_module, "_operator_golden", lambda _: golden_result)
    conn = psycopg.connect(os.environ["DATABASE_URL"], autocommit=False)
    try:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = '10s'")
            cur.execute("SET LOCAL statement_timeout = '60s'")
            cur.execute((root / "sql/migrations/008_better_auth.sql").read_text())
            cur.execute((root / "sql/migrations/011_operator.sql").read_text())
            cur.execute((root / "sql/migrations/011_operator.sql").read_text())
            cur.execute("SELECT count(*) FROM operator_frozen_listing_members")
            # Do not reuse or modify a real operator baseline in this test.
            if cur.fetchone()[0]:
                pytest.skip("A real immutable baseline is already registered")
            cur.execute("SELECT count(*) FROM operator_jobs")
            if cur.fetchone()[0]:
                pytest.skip("Real operator jobs exist; isolated worker test refused")
            cur.execute('INSERT INTO "user" (id,name,email,"emailVerified") VALUES (%s,%s,%s,false)',
                        (user_id,"Rollback Operator",user_id+"@example.invalid"))
            cur.execute("INSERT INTO operator_roles (user_id,role,granted_by) VALUES (%s,'admin','rollback-test')", (user_id,))
        baseline_report = write_report(baseline_version,4505,"baseline.json")
        registered = register_frozen_baseline(conn, authenticated_user_id=user_id,version=baseline_version,
                                              report_path=baseline_report,repo_root=tmp_path)
        assert registered["registered_count"] == 4505
        with conn.cursor() as cur:
            cur.execute("SELECT id,ST_X(geom),ST_Y(geom) FROM listings WHERE assignment_method='within' ORDER BY id LIMIT 2")
            fixtures = cur.fetchall()
        rows = [ListingCandidate(provider="fixture",source_id=str(row[0]),region_slug="pa-mainline",
                address="Rollback fixture",longitude=row[1],latitude=row[2],price=500000) for row in fixtures]
        staged = stage_listing_candidates(conn,authenticated_user_id=user_id,version=version,candidates=rows,
                                          estimate=estimate(),approval=approval())
        assert staged["staged_count"] == 2 and staged["unassigned_count"] == 0 and staged["ambiguous_count"] == 0
        with conn.cursor() as cur:
            cur.execute("SELECT source_content_hash FROM listing_dataset_versions WHERE version=%s",(version,))
            source_hash = cur.fetchone()[0]
        refresh_report = write_report(version,2,"refresh.json",source_hash)
        with pytest.raises(ValueError):
            publish_listing_dataset(conn,authenticated_user_id=user_id,version=version,
                report_path=refresh_report,repo_root=tmp_path,explicit_publish=False)
        with pytest.raises(ValueError):
            with conn.transaction():
                conn.execute("UPDATE staging.operator_listing_records SET record=jsonb_set(record,'{price}','42') WHERE dataset_version=%s",(version,))
                publish_listing_dataset(conn,authenticated_user_id=user_id,version=version,
                    report_path=refresh_report,repo_root=tmp_path,explicit_publish=True)
        validated = validate_listing_dataset(conn,authenticated_user_id=user_id,version=version,repo_root=root)
        assert validated["promotable"]
        published = publish_listing_dataset(conn,authenticated_user_id=user_id,version=version,
            report_path=validated["report_path"],repo_root=root,explicit_publish=True)
        assert published["published"] and not published["public_explorer_changed"]
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM listings")
            assert cur.fetchone()[0] == 4505
            cur.execute("SELECT dataset_version FROM operator_active_listing_dataset")
            assert cur.fetchone()[0] == version
        with pytest.raises(psycopg.errors.RaiseException):
            with conn.transaction():
                conn.execute("UPDATE staging.operator_listing_records SET district_id=NULL WHERE dataset_version=%s",(version,))
        with pytest.raises(psycopg.errors.RaiseException):
            with conn.transaction():
                conn.execute("DELETE FROM operator_frozen_listing_members WHERE listing_id=%s",(fixtures[0][0],))
        draft = draft_region_manifest(slug="rollback-test-area",name="Rollback Area",county_fips=["42091"],layers=[],official_selection_evidence="fixture-only")
        job_id = enqueue_region_job(conn,authenticated_user_id=user_id,draft=draft)
        claimed = claim_region_job(conn,authenticated_user_id=user_id,worker_id="rollback-worker")
        assert claimed["id"] == job_id
        assert claim_region_job(conn,authenticated_user_id=user_id,worker_id="other-worker") is None
        assert advance_region_job(conn,authenticated_user_id=user_id,job_id=job_id,worker_id="rollback-worker",desired="scaffolding") == "scaffolding"
        assert claim_region_job(conn,authenticated_user_id=user_id,worker_id="rollback-worker")["phase"] == "scaffolding"
        assert advance_region_job(conn,authenticated_user_id=user_id,job_id=job_id,worker_id="rollback-worker",desired="coverage") == "coverage"
        assert claim_region_job(conn,authenticated_user_id=user_id,worker_id="rollback-worker")["phase"] == "coverage"
        assert advance_region_job(conn,authenticated_user_id=user_id,job_id=job_id,worker_id="rollback-worker",desired="validated",evidence=green("rollback-test-area"),coverage_report={"complete":True}) == "validated"
        assert claim_region_job(conn,authenticated_user_id=user_id,worker_id="rollback-worker",include_validated=True,job_id=job_id)["phase"] == "validated"
        assert advance_region_job(conn,authenticated_user_id=user_id,job_id=job_id,worker_id="rollback-worker",desired="promoted",evidence=green("rollback-test-area"),coverage_report={"complete":True},explicit_promote=True) == "promoted"
    finally:
        conn.rollback()
        conn.close()


def test_region_coverage_requires_actual_matching_report_and_qa(tmp_path):
    import json
    from PIL import Image
    from gt.manifests.models import RegionManifest
    from gt.operator import region_layer_coverage
    manifest = RegionManifest(slug="new-area",name="New Area",state_fips=["42"],counties=["42091"],layers=["tree_canopy_pct"])
    assert not region_layer_coverage(tmp_path,manifest)["complete"]
    source = tmp_path/"pipeline/manifests/layers/tree_canopy_pct.yaml"
    source.parent.mkdir(parents=True)
    source.write_text("approved-source-packet")
    reports = tmp_path/"data/reports"
    qa = reports/"qa"
    qa.mkdir(parents=True)
    report = reports/"layer_tree_canopy_pct_new-area_latest.json"
    report.write_text(json.dumps({"target":"tree_canopy_pct:new-area","promotable":True}))
    assert not region_layer_coverage(tmp_path,manifest)["complete"]
    Image.new("RGB",(2,2)).save(qa/"tree_canopy_pct_new-area.png")
    assert region_layer_coverage(tmp_path,manifest)["complete"]
    report.write_text(json.dumps({"target":"tree_canopy_pct:wrong-region","promotable":True}))
    assert not region_layer_coverage(tmp_path,manifest)["complete"]
    assert not region_layer_coverage(tmp_path,manifest.model_copy(update={"layers":[]}))["complete"]
