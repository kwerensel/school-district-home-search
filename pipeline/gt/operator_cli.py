"""Explicit local operator commands; no paid-provider or messaging adapter.

Run: cd pipeline && .venv/bin/python -m gt.operator_cli --help
The configured actor is a trusted local worker identity, not public input.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg

from gt.db.migrate import database_url, repo_root
from gt.operator import (
    ListingCandidate, ProviderApproval, ProviderEstimate, enqueue_region_job,
    publish_listing_dataset, register_frozen_baseline, retry_blocked_region_job,
    run_region_job_once, stage_listing_candidates, validate_listing_dataset,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command",required=True)
    register = commands.add_parser("register-baseline",help="Explicitly snapshot the unchanged 4,505 baseline")
    register.add_argument("--version",required=True)
    register.add_argument("--report",required=True)
    stage = commands.add_parser("stage-local-json",help="Stage supplied approved records; no provider call")
    stage.add_argument("--version",required=True)
    stage.add_argument("--input",required=True)
    validate = commands.add_parser("validate-listings",help="Validate staged source/assignments and render QA plus golden checks")
    validate.add_argument("--version",required=True)
    publish = commands.add_parser("publish-listings",help="Separate intentional private-dataset pointer publish")
    publish.add_argument("--version",required=True)
    publish.add_argument("--report",required=True)
    publish.add_argument("--explicit-publish",action="store_true",required=True)
    enqueue = commands.add_parser("enqueue-region",help="Queue a reviewed draft without activating a region")
    enqueue.add_argument("--input",required=True)
    retry = commands.add_parser("retry-region",help="Explicitly retry blocked layer-coverage evidence")
    retry.add_argument("--job-id",type=int,required=True)
    work = commands.add_parser("work-region",help="Execute one queued phase, then exit")
    work.add_argument("--worker-id",required=True)
    work.add_argument("--run-official-scaffold",action="store_true")
    work.add_argument("--explicit-promote",action="store_true")
    work.add_argument("--job-id",type=int)
    work.add_argument("--run-approved-layers",action="store_true",help="Run one missing approved tract layer in staged geometry context")
    args = parser.parse_args(argv)
    actor = os.environ.get("GROUNDTRUTH_OPERATOR_USER_ID","")
    if not actor:
        parser.error("Configure a trusted GROUNDTRUTH_OPERATOR_USER_ID with a server-owned admin role")
    try:
        with psycopg.connect(database_url(),autocommit=False) as conn:
            if args.command == "register-baseline":
                result = register_frozen_baseline(conn,authenticated_user_id=actor,version=args.version,
                    report_path=args.report,repo_root=repo_root())
            elif args.command == "stage-local-json":
                payload = json.loads(Path(args.input).read_text())
                result = stage_listing_candidates(conn,authenticated_user_id=actor,version=args.version,
                    candidates=[ListingCandidate.model_validate(row) for row in payload["candidates"]],
                    estimate=ProviderEstimate(**payload["estimate"]),approval=ProviderApproval(**payload["approval"]))
            elif args.command == "validate-listings":
                result = validate_listing_dataset(conn,authenticated_user_id=actor,version=args.version,repo_root=repo_root())
            elif args.command == "publish-listings":
                result = publish_listing_dataset(conn,authenticated_user_id=actor,version=args.version,
                    report_path=args.report,repo_root=repo_root(),explicit_publish=args.explicit_publish)
            elif args.command == "enqueue-region":
                result = {"job_id":enqueue_region_job(conn,authenticated_user_id=actor,draft=json.loads(Path(args.input).read_text()))}
            elif args.command == "retry-region":
                retry_blocked_region_job(conn,authenticated_user_id=actor,job_id=args.job_id)
                result = {"job_id":args.job_id,"phase":"coverage"}
            else:
                result = run_region_job_once(conn,authenticated_user_id=actor,worker_id=args.worker_id,
                    repo_root=repo_root(),allow_official_scaffold=args.run_official_scaffold,
                    explicit_promote=args.explicit_promote,job_id=args.job_id,run_approved_layers=args.run_approved_layers)
        print(json.dumps(result,sort_keys=True))
        return 0
    except Exception:
        # Never echo a DSN, profile, provider response or raw SQL exception.
        print(json.dumps({"error":"Operator command failed. Check role, feature flag and local validation artifacts."}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
