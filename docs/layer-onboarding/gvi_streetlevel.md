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
The cache uses `osmnx` drive roads with `simplify=True` (retaining intermediate geometry vertices), `retain_all=True`,
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

## Frozen PA sampling checkpoint

The actual simplified Phase 8 PA road cache is available and was processed
without clipping road geometries. An EPSG:5070 spatial index first restricts
whole roads to those within 150 m of a frozen listing; canonical interpolation
still starts from the original full line, so optimization does not move sample
positions. New tests compare long lines with/without far-away roads and verify
that image candidates can be restricted to the listing's own 150 m radius.

The completed PA run uses all **251** live frozen listing IDs and produced
**1,237** road sample points: **247** listings have five points, **one** has two,
and **three** have none within 150 m. Thus 247/251 listings meet the research
minimum of three road points. Sparse counts are retained; no distant road or
zero-greenery value was imputed. The source input and listing geometry hashes,
exact cache contract and sample coordinates are stored under
`data/raw/gvi_streetlevel/pa-mainline/893967d1486c62be/road-samples.json`.
The local summary is `data/reports/gvi_streetlevel_research_pa-mainline.json`;
spatial QA is `data/reports/qa/gvi_streetlevel_sampling_pa-mainline.png`.

A standalone repeatable command is available:

```
cd pipeline
./.venv/bin/python -m gt.gvi_research_cli --region pa-mainline --roads ../data/raw/gvi_ndvi_street/pa-mainline/summer2025-v1-12scenes-3days-scl4to7-cloud50-dilate20m/osm-roads.geojson
```

This command only reads the frozen database points and local road cache. The
optional metadata mode is bounded to one page per listing, at most 200 records
per response and one outgoing request per second; it stops on the first provider
failure, including authentication or throttling, and preserves prior cached
results. This pacing is conservative rather than a claim about a current quota:
the main API policy page requires login and historical forum numbers are not
sufficient evidence for a current account quota. No thumbnail URLs or image
bytes are requested.

**Regional metadata gate:** automatic approval review rejected the proposed
251-query PA metadata run **before execution**, because listing-derived road
bounding boxes would be sent to Mapillary and the review required explicit
user approval for that location egress. Its instruction explicitly prohibits
bypassing the rejection. Only offline sampling/QA continued. Regional candidate
image eligibility is therefore **unknown**, not zero; this run sent zero
metadata queries and requested zero image bytes. Earlier representative probes
remain illustrative only. Do not scale those probes or resume regional queries
until the user explicitly approves the export of these bounding boxes.

Successful segmentation remains **zero** and photographic GVI remains **null**.
There are zero satellite/photographic pairs; correlation remains
`not_computable: insufficient_pairs`. The torch/transformers and checkpoint/
licensing/imagery-retention gates above remain in force. Hudson Valley sampling
awaits its exact Phase 8 road cache and does not justify substituting a different
source or extending coverage claims.

The CLI additionally fails before database/source access when `--metadata` is
requested without `--allow-listing-location-egress`. That flag is only for a
future run after explicit user approval; adding a flag does not itself supply
human approval or supersede the automatic-review rejection. The completed PA
sampling run was followed by **12 passing spatial golden tests**.
