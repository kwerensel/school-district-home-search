# Phase 11 street-level GVI research packet

Status: reversible sampling, metadata coverage, aggregation and correlation
scaffold implemented; no photographic GVI calculated, staged, promoted or
served. Research is anchored to the frozen 251 PA + 4,254 Hudson Valley
listings. The satellite proxy remains the available estimate.

## Method and source contract

`pipeline/gt/gvi_research.py` reads frozen listing points from Neon with
region count assertions. The three-row local sample is never a substitute.
`sample_listing_roads` accepts EPSG:4326 listing points (`id`, geometry) and
EPSG:4326 OSM LineString/MultiLineString roads. It projects to EPSG:5070 for
metric operations, samples roads every 25 m, removes duplicate coordinates,
and chooses the nearest five points within 150 m. Stable geometric tie breaks
and canonical line orientation make retries independent of row/direction
ordering. Fewer than three points remain sparse; do not extend the radius.
Emitted longitude/latitude values remain EPSG:4326.

Use the Phase 8 road cache explicitly selected for the current run:

```
data/raw/gvi_ndvi_street/<region>/summer2025-v1-12scenes-3days-scl4to7-cloud50-dilate20m/osm-roads.geojson
```

The adjacent `osm-request.json` records retrieval, envelope and feature count.
The cache uses `osmnx` drive roads with `simplify=False`, `retain_all=True`,
`truncate_by_edge=True`. Do not silently choose a newer or older glob match.
Cache roads and sampling evidence under gitignored `data/`, preserving the
source-contract path and a hash of both geometry inputs.

The Mapillary adapter makes bounded metadata-only Graph `/images` queries for
`id,computed_geometry,captured_at,sequence`. It uses the configured
`MAPILLARY_ACCESS_TOKEN` in an authorization header, never a URL. It caches
normalized metadata, a token-free request contract, retrieval timestamp and
truncation status. It never follows provider pagination URLs, stores raw
provider errors, or fetches image bytes. A pagination-capped result is a lower
bound, not complete local coverage. Bbox results must pass the metric-distance
coverage reducer before being described as near sampled roads.

`image_coverage` counts distinct candidate images within 50 m of sampled road
points, including zero-count listings. Candidate images are not successfully
segmented images. Before an inference run, freeze a selection contract for
capture dates, image quality/orientation, same-sequence redundancy and image
radius, then retain each image's attribution/provenance. Imagery can be older
than the 2025 satellite composite; this must be reported, not hidden.

## Aggregation and display

`aggregate_segmented_images` accepts one vegetation fraction per distinct
successfully segmented image. Fractions must be finite in [0, 1]. Its
`gvi_streetlevel_n_images` counts successful images, not metadata candidates or
failed downloads. Three successful images is the research eligibility
threshold. Below it, `gvi_streetlevel` is null and the display source remains
`estimated from satellite`; do not substitute zero greenery.

The future tract reducer must aggregate actual listing/road samples and show
sample coverage. It must not imply that sampled listings represent every
street in a tract. Preserve both listing-grain evidence and count distribution
before any tract staging or public integration. Staging, reports, spatial QA,
explicit promotion and golden checks remain mandatory before live use.

`paired_correlation` joins satellite and photographic values on the same
listing IDs, excludes missing/nonfinite pairs and reports paired count and
Pearson r. Require at least three pairs and nonconstant values. Empty/constant
inputs produce `not_computable` with an explicit reason. The coefficient is
exploratory and must accompany sample count, regions, capture dates,
minimum-image threshold, selection bias and scatter plot before interpretation.
Do not assert a presumed r > 0.7.

## Access and licensing evidence, checked 2026-10-18

- [Mapillary API documentation](https://www.mapillary.com/developer/api-documentation/)
  currently requires login when fetched directly. The maintained
  [Mapillary Python SDK source](https://github.com/mapillary/mapillary-python-sdk/blob/main/src/mapillary/config/api/entities.py)
  documents image metadata fields and bbox search. No SDK dependency is added.
- [Mapillary image-license guidance](https://help.mapillary.com/hc/en-us/articles/115001770409-CC-BY-SA-license-for-open-data)
  describes image reuse under CC BY-SA and attribution linking to the image
  and creator. This does not independently settle API access, bulk retention,
  derived-data distribution or model licensing. No imagery is downloaded by
  this scaffold; verify the account's API terms and preserve attribution before
  enabling an image-fetch adapter.
- The candidate [NVIDIA SegFormer Cityscapes model](https://huggingface.co/nvidia/segformer-b0-finetuned-cityscapes-1024-1024)
  is an architecture reference, not an approved production asset. The
  [upstream NVIDIA source license](https://github.com/NVlabs/SegFormer/blob/master/LICENSE)
  limits use to research/evaluation. Pin the exact checkpoint revision and
  review its weight license and Cityscapes dataset terms separately before
  execution or distribution. Do not claim the Python package license grants
  commercial rights to the checkpoint.

## Exact remaining gates

1. `torch` and `transformers` are not installed in `pipeline/.venv`. Installing
   these heavy new dependencies needs approval under AGENTS.md. No packages or
   checkpoint files were downloaded for this scaffold.
2. A precise checkpoint revision, weights license, permissible research versus
   product use, model class mapping, image resize policy and device/runtime
   budget must be fixed before inference. Noncommercial upstream source rights
   do not authorize arbitrary product use.
3. API terms/retention and attribution evidence must be verified before imagery
   retrieval. An access-token presence check is not authorization evidence for
   broader provider use.
4. No segmented observations exist. Pearson r is currently **not computable**;
   there is no correlation finding and no photographic metric promotion.

The unit suite covers deterministic metric sampling, sparse/duplicate imagery,
count versus successful inference distinctions, finite fraction validation,
paired correlation missing/constant states, bounded pagination, credential-free
cache content and sanitized errors. All these checks run without new packages
or external provider calls.

## Bounded metadata probe

A 2026-10-18 read-only probe used the first existing frozen listing ID in each
region, queried a small coordinate bbox, and fetched metadata only. The latest
responses returned 91 metadata records around HV listing 252 and zero around
PA listing 1; neither latest response indicated a capped page. A preceding HV
request returned 100, demonstrating that live search results are not a stable
snapshot. Raw token-free responses and timestamps are cached locally under
`data/raw/gvi_streetlevel/mapillary-coverage/`; the summary is
`data/reports/gvi_streetlevel_coverage_probe.json`.

These are **bbox candidate counts**, not 150 m road-sample eligibility, distinct
usable image counts, regional coverage estimates or segmentation results. They
show the configured API can answer metadata requests and that coverage varies
by location. Full frozen-listing sampling must use the completed satellite
pipeline road caches before regional coverage can be claimed. No image bytes
were requested or downloaded, and no provider payment action occurred.
