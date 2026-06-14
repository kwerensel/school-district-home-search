# canopy_height_m onboarding note

Status: drafted for human approval before full ingestion module.

## Candidate source

Selected source: WRI and Meta Version 2 High Resolution Canopy Height Maps
(`CHMv2`), public on AWS at:

- Registry: https://registry.opendata.aws/dataforgood-fb-forestsv2/
- S3 prefix: `s3://dataforgood-fb-data/forests/v2/global/dinov3_global_chm_v2_ml3/`
- License: Creative Commons Attribution 4.0, per AWS Open Data Registry.
- Citation vintage in registry: Meta and WRI, 2026.

Reason for choosing v2: it is the current WRI/Meta canopy-height release,
superseding the v1 source named in the original architecture spec while keeping
the same schema contract: raster CHM values reduced to tract and listing metrics.

## Source shape

The dataset is organized as global zoom-10 quadkey Cloud Optimized GeoTIFFs:

- `chm/*.tif`: one canopy-height raster per quadkey tile.
- `metadata/*.geojson`: observation-date metadata.
- `tiles.geojson`: global tile extents and quadkey names.

Sample raster header checks from regional tiles:

| Region sample | Quadkey | CRS | Pixel size | Shape | Band dtype |
|---|---:|---|---:|---:|---|
| Hudson Valley | `0302323031` | EPSG:3857 | 1.194 m | 32768 x 32768 | uint8 |
| PA Main Line | `0320101022` | EPSG:3857 | 1.194 m | 32768 x 32768 | uint8 |

## Sample value checks

Windowed reads used a 1024 x 1024 center window from each sample COG, without
downloading full regional tiles.

| Region sample | Min | P50 | P90 | Max | Share > 2 m |
|---|---:|---:|---:|---:|---:|
| Hudson Valley tile `0302323031` | 0 m | 9 m | 17 m | 28 m | 68.48% |
| PA Main Line tile `0320101022` | 0 m | 0 m | 23 m | 36 m | 38.89% |

These ranges are plausible for suburban/forested Northeast tiles and fit the
manifest range `[0, 100]` meters.

## Proposed reductions

- `region_metrics`: census-tract zonal mean canopy height.
- `listing_metrics`: point sample and 100 m buffer mean.
- Initial POC implementation uses a 4096 x 4096 overview grid per zoom-10 tile
  (about 9.6 m working resolution in the Northeast) for practical remote COG
  reads. The source native resolution remains about 1.2 m and can be used later
  with local tile caching if the portfolio/demo needs house-to-house pixel-level
  QA beyond the 100 m buffer signal.
- Do not store rasters in Postgres; raw files stay under `data/raw/canopy_height_m/`.
- Transform or assert output geometries as EPSG:4326 before any database load.
- Validation threshold: at least 99% tract coverage and 4,505/4,505 listing
  coverage for listing-grain outputs.

## GVI relationship

This layer is not the Green View Index. It measures tree height from above.
The spec treats perceived greenery separately:

- Phase 8: `gvi_ndvi_street`, a road-buffered Sentinel-2 NDVI proxy for
  street-adjacent green view.
- Phase 11: `gvi_streetlevel`, a Mapillary image + segmentation research track
  that estimates vegetation pixels from street-level imagery where coverage is
  good enough.

The product story should show these as complementary: canopy height tells users
where mature/tall trees are; GVI tells users how green the street feels.
