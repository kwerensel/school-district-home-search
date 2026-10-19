"""Trusted, lease-scoped staged region reads for enrichment workers.

No environment selector means the ordinary public connection, unchanged.
Temporary views never shadow listings and never create public geometry.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Any, Mapping

import psycopg
from psycopg import sql

from gt.db.migrate import database_url

_CONTEXT_KEYS = ("GT_STAGED_REGION","GT_STAGED_REGION_JOB_ID","GT_STAGED_REGION_WORKER_ID")


@dataclass(frozen=True)
class StagedRegionContext:
    region_slug: str
    job_id: int
    worker_id: str
    actor_user_id: str


def staged_context_from_env(env: Mapping[str,str] | None = None) -> StagedRegionContext | None:
    env = os.environ if env is None else env
    if not any(env.get(key) for key in _CONTEXT_KEYS):
        return None
    slug,job_id,worker = (env.get(key,"") for key in _CONTEXT_KEYS)
    actor = env.get("GROUNDTRUTH_OPERATOR_USER_ID","")
    if (env.get("GROUNDTRUTH_OPERATOR_ENABLED") != "true" or not re.fullmatch(r"[a-z0-9][a-z0-9-]*",slug)
            or not job_id.isdigit() or int(job_id)<=0 or not worker or not actor):
        raise PermissionError("Complete trusted staged-region worker context is required")
    return StagedRegionContext(slug,int(job_id),worker,actor)


def staged_worker_environment(
    base: Mapping[str,str], *, region_slug: str, job_id: int, worker_id: str, actor_user_id: str,
) -> dict[str,str]:
    """Build a child-process environment without mutating shared process state."""
    result = dict(base)
    result.update({"GT_STAGED_REGION":region_slug,"GT_STAGED_REGION_JOB_ID":str(job_id),
                   "GT_STAGED_REGION_WORKER_ID":worker_id,"GROUNDTRUTH_OPERATOR_USER_ID":actor_user_id})
    staged_context_from_env(result)
    return result


def assert_public_promotion_context() -> None:
    if any(os.environ.get(key) for key in _CONTEXT_KEYS):
        raise PermissionError("Promotion cannot run inside a staged region read context")


def prepare_staged_region_reads(conn: Any, requested_region: str, context: StagedRegionContext) -> None:
    if os.environ.get("GROUNDTRUTH_OPERATOR_ENABLED") != "true":
        raise PermissionError("Staged region feature flag is disabled")
    if context.region_slug != requested_region:
        raise PermissionError("Requested layer region differs from the worker lease scope")
    with conn.cursor() as cur:
        cur.execute("""SELECT 1 FROM public.operator_jobs j
          JOIN public.operator_roles r ON r.user_id=%s AND r.role='admin'
          WHERE j.id=%s AND j.kind='region_expansion' AND j.target=%s
            AND j.phase IN ('coverage','validated') AND j.lease_owner=%s
            AND j.lease_expires_at>clock_timestamp()""",
                    (context.actor_user_id,context.job_id,context.region_slug,context.worker_id))
        if cur.fetchone() is None:
            raise PermissionError("A current administrator-owned region worker lease is required")
        cur.execute("""SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_trigger
          WHERE tgrelid='staging.layer_region_metrics'::regclass
            AND tgname='layer_region_metrics_scope_guard' AND tgenabled<>'D')""")
        if not cur.fetchone()[0]:
            raise PermissionError("Staged metric schema migration 013 requires explicit approval and installation")
        cur.execute("SELECT count(*) FROM public.regions WHERE region_group=%s",(context.region_slug,))
        if cur.fetchone()[0]:
            raise ValueError("Staged expansion context cannot replace an existing public region")
        cur.execute("""SELECT EXISTS(SELECT 1 FROM staging.region_scaffold_regions s
          JOIN public.regions p ON p.slug=s.slug WHERE s.region_group=%s)""",(context.region_slug,))
        if cur.fetchone()[0]:
            raise ValueError("Expansion overlaps live region identifiers; shared-region membership needs an explicit design")
        cur.execute("""SELECT count(*),count(*) FILTER (WHERE ST_SRID(geom)<>4326 OR NOT ST_IsValid(geom))
                       FROM staging.region_scaffold_regions WHERE region_group=%s""",(context.region_slug,))
        count,invalid = cur.fetchone()
        if not count or invalid:
            raise ValueError("Valid EPSG:4326 staged region geometry is required")
        cur.execute("""SELECT set_config('groundtruth.staged_region',%s,false),
          set_config('groundtruth.staged_region_job_id',%s,false),
          set_config('groundtruth.staged_region_worker_id',%s,false),
          set_config('groundtruth.staged_region_actor',%s,false)""",
          (context.region_slug,str(context.job_id),context.worker_id,context.actor_user_id))
        # Fixed SQL identifiers; slug is escaped as a PostgreSQL literal because
        # CREATE VIEW cannot retain bind parameters in its stored definition.
        cur.execute(sql.SQL("""CREATE OR REPLACE TEMP VIEW regions AS
          SELECT id,region_type,slug,name,state,source_id,district_id,geom,region_group
          FROM public.regions WHERE region_group IS DISTINCT FROM {slug}
          UNION ALL
          SELECT -row_number() OVER (ORDER BY s.slug) AS id,
            s.region_type,s.slug,s.name,s.state,s.source_id,d.id AS district_id,s.geom,s.region_group
          FROM staging.region_scaffold_regions s
          LEFT JOIN public.school_districts d ON d.nces_geoid=s.district_source_id
          WHERE s.region_group={slug}
        """).format(slug=sql.Literal(context.region_slug)))
        cur.execute(sql.SQL("""CREATE OR REPLACE TEMP VIEW region_overlaps AS
          SELECT ro.child_region_id,ro.parent_region_id,ro.area_weight
          FROM public.region_overlaps ro
          JOIN public.regions child ON child.id=ro.child_region_id
          JOIN public.regions parent ON parent.id=ro.parent_region_id
          WHERE child.region_group IS DISTINCT FROM {slug} AND parent.region_group IS DISTINCT FROM {slug}
          UNION ALL
          SELECT child.id,parent.id,ro.area_weight
          FROM staging.region_scaffold_overlaps ro
          JOIN pg_temp.regions child ON child.slug=ro.child_slug
          JOIN pg_temp.regions parent ON parent.slug=ro.parent_slug
          WHERE ro.region_group={slug}
        """).format(slug=sql.Literal(context.region_slug)))


def connect_layer_database(region_slug: str, **kwargs: Any) -> psycopg.Connection:
    context = staged_context_from_env()
    if context is not None and context.region_slug != region_slug:
        raise PermissionError("Requested layer region differs from the worker scope")
    conn = psycopg.connect(database_url(),**kwargs)
    try:
        if context is not None:
            prepare_staged_region_reads(conn,region_slug,context)
        return conn
    except Exception:
        conn.close()
        raise


def assert_staged_write_lease(cur: Any, region_slug: str) -> None:
    """Recheck wall-clock lease/role before staging and before validation/commit."""
    context = staged_context_from_env()
    if context is None:
        return
    if context.region_slug != region_slug:
        raise PermissionError("Staging target differs from the authorized worker scope")
    cur.execute("""SELECT 1 FROM public.operator_jobs j
      JOIN public.operator_roles r ON r.user_id=%s AND r.role='admin'
      WHERE j.id=%s AND j.target=%s AND j.kind='region_expansion'
        AND j.phase IN ('coverage','validated') AND j.lease_owner=%s
        AND j.lease_expires_at>clock_timestamp()""",
      (context.actor_user_id,context.job_id,context.region_slug,context.worker_id))
    if cur.fetchone() is None:
        raise PermissionError("Staged layer write refused after role or worker lease loss")


def ensure_listing_crs(frame: Any) -> Any:
    """An empty frozen Point4326 query still needs its declared source CRS."""
    return frame.set_crs(4326) if frame.empty and frame.crs is None else frame


def resolve_worker_region_manifest(path: Any) -> Any:
    """Resolve only the selected job's local generated manifest, never arbitrary paths."""
    from pathlib import Path
    from gt.db.migrate import repo_root
    context = staged_context_from_env()
    if context is None:
        return path
    if Path(path).stem != context.region_slug:
        raise PermissionError("Manifest differs from staged worker region scope")
    selected = repo_root()/"data/reports/operator"/f"region-job-{context.job_id}.yaml"
    if not selected.is_file():
        raise ValueError("Selected worker job manifest is missing")
    return selected


def renew_staged_worker_lease(conn: Any, context: StagedRegionContext, *, seconds: int = 300) -> None:
    """Bounded heartbeat cannot resurrect expired/revoked/wrong-owner leases."""
    current=staged_context_from_env()
    if current is not None and current != context:
        raise PermissionError("Heartbeat scope differs from active worker context")
    if os.environ.get("GROUNDTRUTH_OPERATOR_ENABLED") != "true" or not 30<=seconds<=3600:
        raise PermissionError("Trusted worker feature flag and bounded lease are required")
    with conn.cursor() as cur:
        cur.execute("""UPDATE public.operator_jobs j
          SET lease_expires_at=clock_timestamp()+make_interval(secs=>%s),updated_at=clock_timestamp()
          WHERE j.id=%s AND j.target=%s AND j.kind='region_expansion'
            AND j.phase='coverage' AND j.lease_owner=%s AND j.lease_expires_at>clock_timestamp()
            AND EXISTS(SELECT 1 FROM public.operator_roles r WHERE r.user_id=%s AND r.role='admin')""",
          (seconds,context.job_id,context.region_slug,context.worker_id,context.actor_user_id))
        if cur.rowcount != 1:
            raise PermissionError("Worker lease expired or administrator authorization was revoked")
