import pytest

from gt.region_read_context import (
    StagedRegionContext, assert_public_promotion_context, staged_context_from_env,
    staged_worker_environment,
)


def worker_env():
    return {"GROUNDTRUTH_OPERATOR_ENABLED":"true","GROUNDTRUTH_OPERATOR_USER_ID":"admin",
            "GT_STAGED_REGION":"new-area","GT_STAGED_REGION_JOB_ID":"123","GT_STAGED_REGION_WORKER_ID":"worker"}


def test_public_default_has_no_staged_behavior():
    assert staged_context_from_env({}) is None
    assert staged_context_from_env({"GROUNDTRUTH_OPERATOR_ENABLED":"true"}) is None


def test_staged_selection_requires_complete_valid_trusted_context():
    assert staged_context_from_env(worker_env()) == StagedRegionContext("new-area",123,"worker","admin")
    for field in worker_env():
        invalid=worker_env();invalid.pop(field)
        with pytest.raises(PermissionError): staged_context_from_env(invalid)
    for key,value in (("GT_STAGED_REGION","x';DROP TABLE regions;--"),("GT_STAGED_REGION_JOB_ID","-1"),
                      ("GROUNDTRUTH_OPERATOR_ENABLED","false")):
        invalid=worker_env();invalid[key]=value
        with pytest.raises(PermissionError): staged_context_from_env(invalid)


def test_worker_child_environment_does_not_mutate_parent():
    parent={"GROUNDTRUTH_OPERATOR_ENABLED":"true","UNRELATED":"preserved"}
    child=staged_worker_environment(parent,region_slug="new-area",job_id=7,worker_id="w",actor_user_id="admin")
    assert "GT_STAGED_REGION" not in parent
    assert child["UNRELATED"] == "preserved"
    assert staged_context_from_env(child).job_id == 7


def test_promote_refuses_any_staged_scope(monkeypatch):
    for key in ("GT_STAGED_REGION","GT_STAGED_REGION_JOB_ID","GT_STAGED_REGION_WORKER_ID"):
        monkeypatch.delenv(key,raising=False)
    assert_public_promotion_context()
    monkeypatch.setenv("GT_STAGED_REGION","new-area")
    with pytest.raises(PermissionError): assert_public_promotion_context()


def test_write_guard_uses_wall_clock_and_rejects_expired_lease(monkeypatch):
    from gt.region_read_context import assert_staged_write_lease
    for key,value in worker_env().items(): monkeypatch.setenv(key,value)
    class Cursor:
        def execute(self,query,params): self.query=query;self.params=params
        def fetchone(self): return None
    cursor=Cursor()
    with pytest.raises(PermissionError): assert_staged_write_lease(cursor,"new-area")
    assert "clock_timestamp()" in cursor.query
    with pytest.raises(PermissionError): assert_staged_write_lease(cursor,"other-area")


def test_empty_listing_crs_preserves_absence_without_inventing_records():
    import geopandas as gpd
    from gt.region_read_context import ensure_listing_crs
    frame=gpd.GeoDataFrame({"id":[]},geometry=gpd.GeoSeries([],name="geom"))
    result=ensure_listing_crs(frame)
    assert result.empty and result.crs.to_epsg()==4326


@pytest.mark.skipif(__import__("os").environ.get("GT_STAGED_CONTEXT_DB_TESTS")!="1",reason="Opt-in TEMP-view/DML rollback integration")
def test_live_temporary_staged_region_reads_tax_overlap_and_lease_guards(monkeypatch):
    import os
    from uuid import uuid4
    import psycopg
    from psycopg.types.json import Jsonb
    from gt.region_read_context import prepare_staged_region_reads,assert_staged_write_lease
    from gt.layers import tree_canopy,effective_tax,risk_index
    from gt.manifests import load_layer_manifest
    from gt.db.migrate import repo_root
    token=uuid4().hex
    region="qa-staged-"+token
    child_slug="tract-qa-"+token
    parent_slug="mun-cousub-qa-"+token
    user="qa-staged-user-"+token
    conn=psycopg.connect(os.environ["DATABASE_URL"],autocommit=False)
    try:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout='3s'")
            cur.execute("SET LOCAL statement_timeout='15s'")
            cur.execute("SELECT to_regclass('public.operator_jobs')")
            if cur.fetchone()[0] is None: pytest.skip("Operator migration has not been durably applied")
            # Historical CREATE TABLE IF NOT EXISTS cannot restore the old FK
            # before or after the forward-only correction on a populated DB.
            cur.execute((repo_root()/"sql/migrations/003_layer_staging.sql").read_text())
            cur.execute((repo_root()/"sql/migrations/013_staged_region_metrics.sql").read_text())
            cur.execute((repo_root()/"sql/migrations/013_staged_region_metrics.sql").read_text())
            cur.execute((repo_root()/"sql/migrations/003_layer_staging.sql").read_text())
            cur.execute("SELECT count(*) FROM pg_constraint WHERE conrelid='staging.layer_region_metrics'::regclass AND contype='f'")
            assert cur.fetchone()[0]==0
            cur.execute('INSERT INTO public."user" (id,name,email,"emailVerified") VALUES (%s,%s,%s,false)',(user,"Rollback staged reader",user+"@example.invalid"))
            cur.execute("INSERT INTO public.operator_roles(user_id,role,granted_by) VALUES (%s,'admin','rollback-test')",(user,))
            cur.execute("""INSERT INTO public.operator_jobs(kind,target,phase,requested_by,input_manifest,lease_owner,lease_expires_at)
                VALUES ('region_expansion',%s,'coverage',%s,%s,'test-worker',clock_timestamp()+interval '5 minutes') RETURNING id""",(region,user,Jsonb({})))
            job_id=cur.fetchone()[0]
            cur.execute("""SELECT child.id,parent.id,parent.source_id,ro.area_weight FROM public.region_overlaps ro
                JOIN public.regions child ON child.id=ro.child_region_id
                JOIN public.regions parent ON parent.id=ro.parent_region_id
                WHERE child.region_type='census_tract' AND parent.region_type='municipality'
                  AND parent.slug LIKE 'mun-cousub-%%' ORDER BY child.id,parent.id LIMIT 1""")
            child_id,parent_id,parent_source,weight=cur.fetchone()
            cur.execute("SELECT slug,region_group FROM public.regions WHERE id=%s",(child_id,))
            public_child_slug,public_group=cur.fetchone()
            # The ordinary existing public staging path needs no operator GUC.
            cur.execute("INSERT INTO staging.layer_region_metrics(region_group,metric_key,region_slug,value,vintage) VALUES (%s,'qa_public_'||%s,%s,1,'fixture')",(public_group,token,public_child_slug))
            for source_id,slug in ((child_id,child_slug),(parent_id,parent_slug)):
                cur.execute("""INSERT INTO staging.region_scaffold_regions(region_type,slug,name,state,source_id,geom,region_group)
                  SELECT region_type,%s,name,state,source_id,geom,%s FROM public.regions WHERE id=%s""",(slug,region,source_id))
            cur.execute("INSERT INTO staging.region_scaffold_overlaps(child_slug,parent_slug,area_weight,region_group) VALUES (%s,%s,%s,%s)",(child_slug,parent_slug,weight,region))
        env={"GROUNDTRUTH_OPERATOR_ENABLED":"true","GROUNDTRUTH_OPERATOR_USER_ID":user,
             "GT_STAGED_REGION":region,"GT_STAGED_REGION_JOB_ID":str(job_id),"GT_STAGED_REGION_WORKER_ID":"test-worker"}
        for key,value in env.items(): monkeypatch.setenv(key,value)
        context=staged_context_from_env()
        # SQL guard refuses staged-only writes without trusted connection GUCs,
        # even if Python helpers are bypassed.
        with pytest.raises(psycopg.errors.RaiseException):
            with conn.transaction():
                conn.execute("INSERT INTO staging.layer_region_metrics(region_group,metric_key,region_slug,value,vintage) VALUES (%s,'qa_scope',%s,1,'fixture')",(region,child_slug))
        prepare_staged_region_reads(conn,region,context)
        with pytest.raises(psycopg.errors.RaiseException):
            with conn.transaction():
                conn.execute("INSERT INTO staging.layer_region_metrics(region_group,metric_key,region_slug,value,vintage) VALUES (%s,'qa_scoped_public_'||%s,%s,1,'fixture')",(public_group,token,public_child_slug))
        with conn.cursor() as cur:
            cur.execute("SELECT id,slug FROM regions WHERE region_group=%s ORDER BY slug",(region,))
            first=cur.fetchall()
            assert len(first)==2 and all(row[0]<0 for row in first)
            cur.execute("SELECT count(*) FROM public.regions WHERE region_group=%s",(region,))
            assert cur.fetchone()[0]==0
            cur.execute("SELECT count(*) FROM public.listings")
            assert cur.fetchone()[0]==4505
            metrics=effective_tax._compute_tract_metrics(cur,region,{parent_source:.02})
            assert len(metrics)==1 and metrics[0].value==pytest.approx(.02)
            assert risk_index._local_tracts(cur,region)
        prepare_staged_region_reads(conn,region,context)
        with conn.cursor() as cur:
            cur.execute("SELECT id,slug FROM regions WHERE region_group=%s ORDER BY slug",(region,))
            assert cur.fetchall()==first
        tracts=tree_canopy._read_tracts(conn,region)
        listings=tree_canopy._read_listings(conn,region)
        assert len(tracts)==1 and listings.empty and listings.crs.to_epsg()==4326
        manifest=load_layer_manifest(repo_root()/"pipeline/manifests/layers/tree_canopy_pct.yaml")
        with conn.cursor() as cur:
            tree_canopy._clear_staging(cur,region,"tree_canopy_pct")
            tree_canopy._stage_region_metrics(cur,region,manifest,[tree_canopy.RegionMetric(child_slug,50)])
            checks=tree_canopy._validation_checks(cur,region,manifest,"tract")
            assert checks["tract_coverage"]==1 and checks["listings_expected"]==0
        with pytest.raises(psycopg.errors.RaiseException):
            with conn.transaction():
                conn.execute("SELECT set_config('groundtruth.staged_region_worker_id','wrong-worker',false)")
                conn.execute("INSERT INTO staging.layer_region_metrics(region_group,metric_key,region_slug,value,vintage) VALUES (%s,'qa_wrong_worker',%s,1,'fixture')",(region,child_slug))
        with pytest.raises(psycopg.errors.RaiseException):
            with conn.transaction():
                conn.execute("INSERT INTO staging.layer_region_metrics(region_group,metric_key,region_slug,value,vintage) VALUES (%s,'qa_unknown',%s,1,'fixture')",(region,'unknown-'+region))
        with pytest.raises(psycopg.errors.RaiseException):
            with conn.transaction():
                conn.execute("UPDATE public.operator_jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=%s",(job_id,))
                conn.execute("INSERT INTO staging.layer_region_metrics(region_group,metric_key,region_slug,value,vintage) VALUES (%s,'qa_expired',%s,1,'fixture')",(region,child_slug))
        with pytest.raises(PermissionError):
            with conn.transaction():
                conn.execute("UPDATE public.operator_jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=%s",(job_id,))
                with conn.cursor() as cur: tree_canopy._clear_staging(cur,region,"tree_canopy_pct")
        with pytest.raises(psycopg.errors.RaiseException):
            with conn.transaction():
                conn.execute("DELETE FROM public.operator_roles WHERE user_id=%s",(user,))
                conn.execute("INSERT INTO staging.layer_region_metrics(region_group,metric_key,region_slug,value,vintage) VALUES (%s,'qa_revoked',%s,1,'fixture')",(region,child_slug))
        with pytest.raises(PermissionError):
            with conn.transaction():
                conn.execute("DELETE FROM public.operator_roles WHERE user_id=%s",(user,))
                with conn.cursor() as cur: assert_staged_write_lease(cur,region)
        with pytest.raises(PermissionError): prepare_staged_region_reads(conn,"wrong-region",context)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM staging.region_scaffold_regions WHERE slug=%s AND region_group=%s",(child_slug,region))
            cur.execute("SELECT count(*) FROM staging.layer_region_metrics WHERE region_slug=%s AND region_group=%s",(child_slug,region))
            assert cur.fetchone()[0]==0
    finally:
        conn.rollback()
        conn.close()


def test_heartbeat_cannot_resurrect_expired_or_wrong_worker_lease(monkeypatch):
    from gt.region_read_context import renew_staged_worker_lease
    monkeypatch.setenv("GROUNDTRUTH_OPERATOR_ENABLED","true")
    for key in ("GT_STAGED_REGION","GT_STAGED_REGION_JOB_ID","GT_STAGED_REGION_WORKER_ID"):
        monkeypatch.delenv(key,raising=False)
    class Cursor:
        rowcount=0
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def execute(self,query,params): self.query=query
    cursor=Cursor()
    class Conn:
        def cursor(self): return cursor
    with pytest.raises(PermissionError):
        renew_staged_worker_lease(Conn(),StagedRegionContext("new-area",1,"worker","admin"))
    assert "lease_expires_at>clock_timestamp()" in cursor.query
    assert "operator_roles" in cursor.query


def test_staged_source_work_stops_before_uninstalled_migration(monkeypatch):
    from gt.region_read_context import prepare_staged_region_reads
    monkeypatch.setenv("GROUNDTRUTH_OPERATOR_ENABLED","true")
    class Cursor:
        def __init__(self): self.responses=iter([(1,),(False,)]);self.queries=[]
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def execute(self,query,params=None): self.queries.append(str(query))
        def fetchone(self): return next(self.responses)
    cursor=Cursor()
    class Conn:
        def cursor(self): return cursor
    with pytest.raises(PermissionError,match="migration 013"):
        prepare_staged_region_reads(Conn(),"new-area",StagedRegionContext("new-area",1,"w","admin"))
    assert len(cursor.queries)==2
    assert not any("CREATE" in query for query in cursor.queries)
