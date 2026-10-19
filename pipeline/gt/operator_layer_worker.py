"""One authorized staged-region tract layer plus QA; no promotion path."""
from __future__ import annotations

import argparse
import json
import re

from gt.db.migrate import repo_root
from gt.region_read_context import connect_layer_database, staged_context_from_env, assert_staged_write_lease


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layer",required=True)
    parser.add_argument("--region",required=True)
    args=parser.parse_args(argv)
    try:
        if not re.fullmatch(r"[a-z][a-z0-9_]*",args.layer):
            raise ValueError("Invalid approved layer identifier")
        context=staged_context_from_env()
        if context is None or context.region_slug!=args.region:
            raise PermissionError("A scoped operator worker lease is required")
        from gt.manifests import load_layer_manifest
        from gt.operator import _staged_region_fingerprint,_operator_golden
        from gt.layers.runner import render_layer_qa
        root=repo_root()
        manifest_path=root/"pipeline/manifests/layers"/f"{args.layer}.yaml"
        manifest=load_layer_manifest(manifest_path)
        if "tract" not in manifest.grains and "both" not in manifest.grains:
            raise ValueError("Listing-only layer is blocked without an approved listing dataset")
        with connect_layer_database(args.region) as conn:
            before,_=_staged_region_fingerprint(conn,args.region)
        # Existing registered dispatch preserves source-specific access/range
        # rules; explicit tract grain does not fabricate listing coverage.
        from gt.cli import layer_run
        layer_run(args.layer,region=args.region,grain="tract")
        path=root/"data/reports"/f"layer_{args.layer}_{args.region}_latest.json"
        payload=json.loads(path.read_text())
        if payload.get("target")!=f"{args.layer}:{args.region}" or payload.get("promotable") is not True:
            raise ValueError("Layer staging is not promotable")
        qa=render_layer_qa(manifest_path,args.region)
        with connect_layer_database(args.region) as conn:
            with conn.cursor() as cur:
                assert_staged_write_lease(cur,args.region)
            after,_=_staged_region_fingerprint(conn,args.region)
        if before!=after:
            raise ValueError("Staged source geometry changed during the layer run")
        golden=_operator_golden(root)
        payload["promotable"]=payload["promotable"] and golden
        payload["qa_artifacts"]=[str(qa.relative_to(root))]
        payload["checks"].update({"region_read_context":"staging","staged_region_job_id":context.job_id,
            "staged_source_fingerprint":after,"requested_grain":"tract","golden_passed":golden,
            "listing_scope_status":"blocked_no_listing_dataset"})
        path.write_text(json.dumps(payload,indent=2,sort_keys=True))
        print(json.dumps({"layer":args.layer,"region":args.region,"promotable":payload["promotable"],
                          "report":str(path.relative_to(root)),"promoted":False}),flush=True)
        return 0 if payload["promotable"] else 1
    except Exception:
        print(json.dumps({"error":"Staged layer failed or lost its authorized lease; inspect cached local reports and retry after review."}),flush=True)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
