"""Bounded Phase 11 metadata research; never downloads image bytes or writes live metrics."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import time

import geopandas as gpd
import psycopg

from gt.db.migrate import database_url, repo_root
from gt.gvi_research import (
    MapillaryMetadataError, RoadSample, frozen_listings, image_coverage,
    mapillary_coverage, paired_correlation, sample_listing_roads,
)


def _digest_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_research(
    *, region: str, roads_path: Path, metadata: bool = False,
    max_requests: int = 251, interval_seconds: float = 1.0, page_size: int = 200,
    listing_location_egress_approved: bool = False,
) -> dict:
    if metadata and not listing_location_egress_approved:
        raise PermissionError("Explicit approval to send listing-derived bounding boxes to Mapillary is required")
    root = repo_root()
    roads_path = roads_path.resolve()
    cache_root = (root / "data/raw/gvi_ndvi_street" / region).resolve()
    if not roads_path.is_relative_to(cache_root) or not roads_path.is_file():
        raise ValueError("Select an existing explicit Phase 8 road-cache contract")
    if not 0 <= max_requests <= 5000 or interval_seconds < 1 or not 1 <= page_size <= 200:
        raise ValueError("Research budget must be bounded with at least one second between requests")
    with psycopg.connect(database_url()) as conn:
        listings = frozen_listings(conn, region)
    projected = listings.to_crs(5070).set_index("id")
    listing_digest = sha256()
    for row in listings.sort_values("id").itertuples():
        listing_digest.update(str(row.id).encode())
        listing_digest.update(row.geometry.wkb)
    contract = {"region":region,"road_cache":str(roads_path.relative_to(root)),
                "road_sha256":_digest_file(roads_path),"listing_sha256":listing_digest.hexdigest(),
                "listing_count":len(listings),"version":2,"spacing_m":25,"radius_m":150,"max_points":5,
                "whole_geometry_prefilter":True}
    contract_hash = sha256(json.dumps(contract,sort_keys=True).encode()).hexdigest()
    directory = root/"data/raw/gvi_streetlevel"/region/contract_hash[:16]
    directory.mkdir(parents=True,exist_ok=True)
    samples_path = directory/"road-samples.json"
    if samples_path.exists():
        cached = json.loads(samples_path.read_text())
        if cached["contract"] != contract:
            raise ValueError("Sample contract differs from cached inputs")
        samples = [RoadSample(**row) for row in cached["samples"]]
    else:
        roads = gpd.read_file(roads_path)
        samples = sample_listing_roads(listings,roads)
        samples_path.write_text(json.dumps({"contract":contract,"samples":[asdict(row) for row in samples]},indent=2))
    counts = Counter(row.listing_id for row in samples)
    listing_ids = sorted(int(value) for value in listings["id"])
    samples_by_listing: dict[int,list[RoadSample]] = {value:[] for value in listing_ids}
    for sample in samples:
        samples_by_listing[sample.listing_id].append(sample)
    locations = {int(row.id):(row.geometry.x,row.geometry.y) for row in listings.itertuples()}
    _render_sample_qa(listings,samples,counts,root/"data/reports/qa"/f"gvi_streetlevel_sampling_{region}.png")
    summary = {"region":region,"contract":contract,"sample_cache":str(samples_path.relative_to(root)),
               "sample_point_count":len(samples),"listing_count":len(listings),
               "road_sample_count_distribution":dict(sorted(Counter(counts.get(value,0) for value in listing_ids).items())),
               "listings_with_at_least_three_road_points":sum(counts.get(value,0)>=3 for value in listing_ids),
               "metadata_requested":metadata,"candidate_image_counts_status":"not_requested" if not metadata else "pending",
               "listings_with_at_least_three_candidate_images":None,"image_bytes_downloaded":0,
               "successful_segmentation_count":0,"gvi_streetlevel":None,
               "correlation":paired_correlation({},{}),"observed_at":datetime.now(timezone.utc).isoformat()}
    report_path = root/"data/reports"/f"gvi_streetlevel_research_{region}.json"
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(summary,indent=2,sort_keys=True))
    print(json.dumps({"phase":"sampling","region":region,"listings":len(listings),"samples":len(samples),
                      "eligible_road_samples":summary["listings_with_at_least_three_road_points"]}),flush=True)
    if not metadata:
        return summary
    coverage: list[dict] = []
    query_count = 0
    requests_sent = 0
    failures: list[dict] = []
    start = time.monotonic()
    last_request_at = -float("inf")
    for listing_id in listing_ids:
        road_samples = samples_by_listing[listing_id]
        if not road_samples:
            coverage.append({"listing_id":listing_id,"candidate_image_count":0,"coverage_eligible":False,
                             "image_ids":[],"status":"no_road_samples","truncated":False})
            continue
        bounds = tuple(projected.loc[[listing_id]].geometry.buffer(150).to_crs(4326).total_bounds)
        def paced_fetch(request):
            nonlocal requests_sent,last_request_at
            if requests_sent >= max_requests:
                raise RuntimeError("Configured metadata request budget exhausted")
            remaining = interval_seconds - (time.monotonic()-last_request_at)
            if remaining>0:
                time.sleep(remaining)
            from gt.gvi_research import _request_metadata
            requests_sent += 1
            last_request_at = time.monotonic()
            return _request_metadata(request)
        try:
            result = mapillary_coverage(bounds,cache_dir=directory/"mapillary-coverage",max_pages=1,
                                         page_size=page_size,requester=paced_fetch)
        except MapillaryMetadataError as error:
            failures.append({"listing_id":listing_id,"http_status":error.status_code,
                             "reason":"metadata_request_failed_or_budget_exhausted"})
            # Stop on the first provider failure, including throttling/auth:
            # retries across hundreds of listings could amplify a real block.
            break
        query_count += 1
        value = image_coverage(road_samples,result["images"],listing_ids=[listing_id],
                               listing_locations={listing_id:locations[listing_id]})[0]
        value.update({"status":"metadata_candidates_only","truncated":result["truncated"],
                      "bbox_candidate_count":len(result["images"]),"retrieved_at":result["retrieved_at"],
                      "road_sample_count":len(road_samples),"successful_segmentation_count":0})
        coverage.append(value)
        # Incremental resumable evidence includes every successful query; no
        # access token, raw provider errors or thumbnail URL is persisted.
        (directory/"listing-image-coverage.json").write_text(json.dumps(coverage,indent=2))
        if query_count % 25 == 0:
            print(json.dumps({"phase":"metadata","region":region,"listings_queried":query_count,
                              "requests_sent":requests_sent,"elapsed_seconds":round(time.monotonic()-start)}),flush=True)
    summary.update({"metadata_queries_completed":query_count,"metadata_requests_sent_this_run":requests_sent,
                    "candidate_image_counts_status":"complete" if len(coverage)==len(listings) and not failures else "partial",
                    "coverage_listings_processed":len(coverage),"coverage_complete":len(coverage)==len(listings) and not failures,
                    "provider_failures":failures,"throttle_seconds":interval_seconds,"max_pages_per_listing":1,
                    "metadata_page_size":page_size,"truncated_listing_count":sum(row["truncated"] for row in coverage),
                    "candidate_image_count_distribution":dict(sorted(Counter(row["candidate_image_count"] for row in coverage).items())),
                    "listings_with_at_least_three_candidate_images":sum(row["candidate_image_count"]>=3 for row in coverage),
                    "listing_coverage_cache":str((directory/"listing-image-coverage.json").relative_to(root)),
                    "interpretation":"Candidate coverage only; capped results are lower bounds. No photographic GVI or correlation is available."})
    (directory/"listing-image-coverage.json").write_text(json.dumps(coverage,indent=2))
    report_path.write_text(json.dumps(summary,indent=2,sort_keys=True))
    return summary


def _render_sample_qa(listings, samples, counts, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    frame = listings.to_crs(5070).copy()
    frame["n_road_samples"] = frame["id"].map(counts).fillna(0)
    figure,axes = plt.subplots(figsize=(9,9))
    try:
        frame.plot(ax=axes,column="n_road_samples",cmap="viridis",vmin=0,vmax=5,legend=True,markersize=12)
        axes.set_title("Frozen listing road sample counts (0–5), within 150 m")
        axes.set_axis_off()
        path.parent.mkdir(parents=True,exist_ok=True)
        figure.savefig(path,dpi=160,bbox_inches="tight")
    finally:
        plt.close(figure)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region",required=True,choices=("pa-mainline","hudson-valley"))
    parser.add_argument("--roads",required=True,type=Path)
    parser.add_argument("--metadata",action="store_true")
    parser.add_argument("--allow-listing-location-egress",action="store_true",
                        help="Use only after explicit user approval of Mapillary listing-derived bbox export")
    parser.add_argument("--max-requests",type=int,default=251)
    parser.add_argument("--interval-seconds",type=float,default=1.0)
    parser.add_argument("--page-size",type=int,default=200)
    args = parser.parse_args(argv)
    try:
        result = run_research(region=args.region,roads_path=args.roads,metadata=args.metadata,
                              max_requests=args.max_requests,interval_seconds=args.interval_seconds,page_size=args.page_size,
                              listing_location_egress_approved=args.allow_listing_location_egress)
        print(json.dumps(result,sort_keys=True),flush=True)
        return 0 if not result.get("provider_failures") else 1
    except Exception:
        print(json.dumps({"error":"Research run failed; inspect cached local evidence. No image bytes were requested."}),flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
