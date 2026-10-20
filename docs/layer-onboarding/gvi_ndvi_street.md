# `gvi_ndvi_street` source onboarding

## Decision

Use the architecture-approved Phase 8 satellite proxy: a summer Sentinel-2
Level-2A NDVI composite masked to a 50 m corridor around the OpenStreetMap road
network. Publish tract context for Discovery and 100 m / 500 m listing-buffer
context for Explorer. The UI must call this a satellite estimate of
street-adjacent greenness, not photographic or address-level GVI.

## Sources and access

- Copernicus Sentinel-2 Collection 1 Level-2A, discovered through Element 84's
  public Earth Search STAC API (`POST /v1/search`):
  `https://earth-search.aws.element84.com/v1/collections/sentinel-2-c1-l2a`.
- Public 10 m Cloud Optimized GeoTIFF assets hosted in the AWS Registry of Open
  Data. Required assets are `red` (B04), `nir` (B08), and `scl` (the 20 m
  Scene Classification Layer and `cloud` probability layer, both resampled
  with nearest-neighbor semantics).
- OpenStreetMap road geometries, retrieved through the existing `osmnx`
  dependency (`drive` network; degree-2 chains retain exact intermediate
  coordinates, and reversed geometries are deduplicated) and cached under `data/raw/gvi_ndvi_street/`.

These paths are free and require no API key. Raw imagery, STAC responses,
OpenStreetMap responses, regional composites, and validation artifacts remain
gitignored under `data/`.

## Deterministic selection and composite

1. Query the fixed interval `2025-06-01/2025-08-31` for items intersecting the
   region envelope, require Collection 1 L2A scenes, and filter tile-wide
   `eo:cloud_cover` to at most 20%.
2. Group candidates by Sentinel MGRS tile. Sort by scene cloud percentage,
   acquisition timestamp, then item id; keep at most 12 of the clearest
   unique acquisition days per tile. Cache the selected item ids and asset URLs so retries use
   the same inputs.
3. Treat SCL classes 0 (no data), 1 (saturated/defective), 2 (dark area),
   3 (cloud shadow), 8-10 (cloud/cirrus), and 11 (snow/ice) as invalid. Keep
   valid surface classes 4-7. Also reject cloud-probability values above 50%
   and dilate the invalid mask by one native 20 m mask cell. Resample both
   masks with nearest-neighbor only.
4. Calculate `(nir - red) / (nir + red)` after applying each asset's source
   reflectance scale and offset metadata; Collection 1's nonzero offset means
   raw digital numbers cannot be used directly. Take the per-pixel median
   across valid summer scenes and require at least three valid observations.
5. Build a 50 m road corridor in a meter-based projected CRS and mask the
   composite before zonal reduction.

The implementation must record selected scenes, tile counts, valid-observation
counts, cloud-mask coverage, source CRS values, and retrieval dates in its
validation report or adjacent cached request manifest.

## Reductions and honesty rules

- Census tracts: mean of valid road-corridor composite pixels.
- Listings: mean within the intersection of the road corridor and 100 m / 500 m
  listing buffers.
- No listing point sample: a 10 m optical pixel and seasonal composite are
  context, not parcel truth.
- `green_divergence` is a derived comparison between promoted
  `tree_canopy_pct` and street-NDVI percentiles at matching grains. It should
  be generated transparently in SQL, not fetched or presented as a measured
  source value. Do not add both GVI and this linear derivative to the archetype
  feature matrix because that would double-weight greenery.

## Validation and acceptance

- At least 99% tract coverage in both project regions.
- Complete 100 m and 500 m listing-buffer coverage unless a report identifies
  a verified absent-road-corridor case under the user-approved October 19
  Unknown policy below; never silently impute a missing listing value.
- Values finite and inside `[-1, 1]`.
- QA maps for both regions plus a paired canopy-versus-street-NDVI view and a
  divergence view.
- A same-block listing spot check showing plausible 100 m variation.
- Preserve staging -> validate -> explicit promote and run spatial golden tests
  after promotion.

## Known limitations

- NDVI is sensitive to season, recent mowing, soil, water, and shadows. It does
  not equal the fraction of vegetation visible to a person standing on the
  street.
- Sentinel-2 is 10 m for red/NIR while SCL is 20 m; cloud-mask edges are
  consequently coarser than the NDVI grid.
- OpenStreetMap road completeness and classification vary. The cached request
  record is part of the source provenance.
- Both current regions fall in UTM zone 18, but the implementation must derive
  and assert source CRS metadata instead of relying on that coincidence.
- Phase 11 Mapillary segmentation is the later photographic validation track.
  Where that coverage is thin, this metric remains the explicit satellite
  fallback.

## First staged PA evidence and genuine source-support gaps

The first full PA run selected 36 unique tile/day scenes from 128 candidates
(across four MGRS tiles), with source and target CRS verified as EPSG:32618.
It produced 495/495 tract means, 251/251 listing 500 m means, and 248/251
listing 100 m means; all values are finite in 0.1631–0.8836. Valid composite
coverage is 99.72% of rasterized road-corridor pixels. The original report
was not promotable under the complete-listing gate. A fresh run after the
October 19 policy approval is promotable with three explicit Unknowns.

Three frozen listing points have no geometric support from the cached OSM
`drive` road network within their 100 m buffer plus the 50 m corridor width:

| Listing id | Nearest cached drive-road centerline | 100 m corridor intersection | Observation-supported pixels |
| --- | ---: | --- | ---: |
| 159 | 158.59 m | absent | 0 |
| 161 | 169.22 m | absent | 0 |
| 214 | 161.61 m | absent | 0 |

Each has a valid 500 m value. These are also exactly the three listings with no
Phase 11 road samples within 150 m. This is a source-support limitation relative
to the cached drive network, not a cloud-mask or zonal-reducer failure. No
value is imputed or corridor widened. On October 19 the user explicitly
approved preserving genuine source gaps as Unknown. The revised validator
requires unique, exact ID/grain diagnostic matching and complete accounting
for both buffers: computed plus explicit Unknown equals expected listings.
Accepted gaps must prove absent geometric intersection, nearest road beyond
buffer radius plus 50 m, and zero corridor/observation pixels. Cloud gaps,
outside-raster buffers, missing diagnostics and reducer inconsistencies remain
blocking. The 99% tract, finite/range, and three-valid-day gates are unchanged.
The old red report was replaced by a fresh staging/validation run, not edited.

The first cached report used the field name `cloud_mask_invalid_fraction`
(0.8479); it includes source nodata/out-of-tile cells across every selected
scene, as well as masked optical cells. It must **not** be described as 84.8%
actual cloud cover. Future implementation names this diagnostic
`scene_invalid_fraction_including_nodata`.

Local staged QA includes the standard tract map, paired canopy/NDVI/derived
percentile-divergence maps, missing-source closeups, and a nearby same-street
spot check. Listings 35 and 45 on Presidential Boulevard are 157 m apart and
have 100 m means 0.36712 and 0.47714; recomputing directly from the cached raster
matches both staged values exactly. The 10 m pixel/road/buffer closeup shows
plausible local variation while retaining the satellite-estimate limitation.

Reproduce the detailed QA with normal pipeline database configuration (no
secrets in commands or artifacts):

```python
from gt.gvi_qa import render_gvi_spotcheck, render_gvi_missing_qa
render_gvi_spotcheck("pa-mainline")
render_gvi_missing_qa("pa-mainline")
```

Both helpers read registered frozen listings and local cached source rasters;
they write PNG/JSON evidence under `data/reports/qa/` and never promote data.

## Hudson Valley access blocker

The Hudson Valley scene packet is cached (44 selected tile/day scenes from
177 candidates), but the regional OSM road cache is incomplete. Three bounded
primary `overpass-api.de` attempts and two documented same-operator
`lz4.overpass-api.de` attempts returned connection-refused errors. One bounded
recovery attempt through the public `overpass.private.coffee` OSM mirror
cached an 18 MB response, then failed on the next response with HTTP 500.
These are OSM endpoints documented by the [official OSM Overpass wiki](https://wiki.openstreetmap.org/wiki/Overpass_API), not new paid providers.

Mirror responses remain cached separately by endpoint. Recovery used the same
broad regional envelope and `drive` network semantics; no individual listing
coordinates were sent. The mirror road-source attempt had a 600-second total
budget. No final regional road GeoJSON, GVI composite, staged metric rows,
validation report, or promotion exists for Hudson Valley. Partial road
coverage must never be treated as complete source support.

Exact retry counts and retained-cache evidence are recorded in
`data/reports/gvi_source_access_hudson-valley_latest.json`. Resume the same
approved source from its cached chunks after service recovery. No additional
mirrors, repeated unbounded requests, corridor changes, or gate changes are
currently authorized by this source-recovery episode.

## PA promotion checkpoint — October 19

The freshly generated promotable report, standard and detailed QA PNGs, 142
passing pipeline tests and visual source-gap review preceded the separate
explicit promote command. Public verification found 495 tract values
(0.16306–0.79483), 248 100 m values (0.16960–0.88358), 251 500 m values
(0.37025–0.80994), and exactly missing 100 m IDs 159/161/214. The live derived
views contain 61 PA district and 499 matching listing-buffer comparisons.
Twelve post-promotion golden checks pass. No HV GVI is live; no archetype
rebuild or photographic GVI is implied by this regional checkpoint.

## Approved Geofabrik recovery — October 19

The user explicitly approved the free New York OSM download and continuation
of the build. Recovery uses the same provider's Connecticut, New Jersey and
Pennsylvania extracts only where existing Hudson Valley buffers cross borders.
No listing region is added. Pin all four files to `261018` (October 18), verify
the provider MD5 and retain SHA-256, boundary hashes, source URLs and license.

Official sources: [New York](https://download.geofabrik.de/north-america/us/new-york.html),
[Connecticut](https://download.geofabrik.de/north-america/us/connecticut.html),
[New Jersey](https://download.geofabrik.de/north-america/us/new-jersey.html),
[Pennsylvania](https://download.geofabrik.de/north-america/us/pennsylvania.html).
The downloads are OpenStreetMap data under ODbL 1.0; retain attribution to OSM
contributors and Geofabrik. No account, API key, paid service or new package is
required. Files remain gitignored under `data/raw/osm/geofabrik/`.

`gt.osm_extract.prepare_geofabrik_roads` uses the installed GDAL/pyogrio OSM
reader, reconstructing full way geometry before a SQL envelope predicate.
It deliberately avoids driver-level node spatial filtering, which can omit
vertices ([GDAL driver documentation](https://gdal.org/en/stable/drivers/vector/osm.html)).
Tests verify retained vertices outside the envelope. Closed ways remain lines
until the access/area filter; private/service/footpath/driveway ways are excluded
using the OSMnx drive regex rules. Full raw way geometry avoids graph splitting
and simplification; unlike OSMnx graph simplification it retains isolated road
rings. The source contract records this distinction. Corridor width stays 50m.
Duplicate IDs must have identical full geometry across extracts before merging.

The state boundary union covers all 4,254 listing footprints through the 500m
buffer plus 50m road-corridor allowance. New York alone leaves about 5km² of
border-buffer support uncovered. The combined union leaves only 0.1235km² at
a coastal tract, `tract-36119007600`; that entire tract is omitted from metric
computation instead of calculating from partly supported roads. The existing
99% tract gate counts it as missing (at most 436/437 before optical checks).
No missing listing result or unsupported coastal tract is filled with zero.

Per-extract intermediate GeoPackages are keyed by PBF hash, query envelope,
filter and GDAL configuration, enabling local retries without downloading or
reconstructing completed extracts again. The final `osm-request.json` records
served footprint coverage and excluded tract source gaps. The layer report
retains that provenance and still needs fresh validation/QA before promotion.

Missing-buffer closeups are paginated in groups of six (maximum eight per
page). The first PNG keeps its existing canonical filename; subsequent PNGs
use `_page-002` and later suffixes. The companion JSON lists every page and
every missing buffer diagnostic. This keeps large source-gap reviews bounded
without dropping evidence; single-case, multi-page, alternate CRS/500m and
complete-coverage branches are tested.

The composite reads up to four independent scenes concurrently. Each scene
owns separate dataset handles, every window's reads finish before the next,
and only the main thread merges acquisition days and writes output. Ordered
results preserve overlap precedence. Serial/four-reader multi-window tests
produce exactly identical bands and diagnostics with same-day tile overlap
and cloud holes. No model/algorithm fingerprint or scientific rule changes.
Source requests now have bounded connection/read timeouts and existing retry
limits. [Rasterio concurrency guidance](https://rasterio.readthedocs.io/en/stable/topics/concurrency.html)
explains the independent-dataset I/O model; shared dataset writes stay serial.
