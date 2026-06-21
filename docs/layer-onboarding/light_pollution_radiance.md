# light_pollution_radiance onboarding note

Status: source verified from approved local EOG file; ingestion module added.

## Candidate source

Selected source: Earth Observation Group VIIRS Annual VNL V2.2
median-masked composite.

- Product page: https://eogdata.mines.edu/products/vnl/
- V2.2 download directory: https://eogdata.mines.edu/nighttime_light/annual/v22/
- Source publisher: Earth Observation Group, Payne Institute for Public Policy,
  Colorado School of Mines.
- Citation vintage: 2025, verified from the authenticated local EOG V2.2
  median-masked file.

Reason for choosing this source: the architecture spec names VIIRS VNL V2
annual median from EOG for Phase 5 `light_pollution_radiance`. EOG's product
page lists Annual VNL V2.2 as the latest VNL V2 update and documents the annual
V2 products as global EPSG:4326 GeoTIFFs at 15 arc-second resolution with
radiance units of `nW/cm2/sr`.

## Candidate comparison

Selected: Annual VNL V2.2 median-masked.

- Pros: official EOG VNL product, global annual composite, stable time-series
  method, native units directly match the metric, and 15 arc-second cells align
  with the spec's neighborhood-context treatment.
- Processing meaning: annual V2 uses monthly cloud-free composites, outlier
  removal, and background masking. The median-masked product is a conservative
  choice for residential context because it suppresses ephemeral high-light
  events better than a raw annual maximum or unmasked average.
- Grain honesty: tract-only for stored metrics. If Explorer later displays this
  around a listing, use the listing's containing tract value and label it as
  neighborhood context.

Rejected for this layer: monthly VNL composites.

- Reason: monthly files are useful for time-series analysis, but they have
  season/cloud-coverage complications and are not needed for the Phase 5 annual
  regional context metric.

Rejected for this layer: NASA Black Marble annual products.

- Reason: Black Marble is official and useful, but the repo spec explicitly
  names EOG VIIRS VNL V2 for this metric. Using Black Marble would change the
  source definition and should be a separate substitution decision.

Rejected for this layer: light-pollution web map tiles or citizen-science sky
brightness maps.

- Reason: tiles are display products rather than ingestion-grade source data,
  and sky brightness models are a different metric from satellite-observed
  upward radiance.

## Source shape

Source metadata verified from EOG documentation:

| Field | Value |
|---|---|
| Product family | Annual VNL V2.2 |
| Selected raster | `VNL_npp_2025_global_vcmslcfg_v2_c202604011200.median_masked.dat.tif.gz` |
| CRS | EPSG:4326 |
| Pixel size | 15 arc-second, about 500 m at the equator |
| Coverage | Global, 180W to 180E and 75N to 65S |
| Units | `nW/cm2/sr` |
| Data content options | average, average-masked, median, median-masked, min, max, cloud-free coverage, coverage |
| Metric field | raster cell radiance |
| Allowed draft range | 0-1000 `nW/cm2/sr` |

The pipeline reads the raster as a local source artifact under `data/raw/eog/`,
reduces values to local census-tract geometries, and keeps all stored vector
geometries in EPSG:4326. Rasters do not enter Postgres.

## Sample value checks

The authenticated local 2025 EOG V2.2 median-masked raster opened as EPSG:4326,
86,401 x 33,601 pixels, one `float32` band, with global bounds approximately
180W to 180E and 65S to 75N. Windowed source samples were measured on
2026-06-20:

| Region sample | Expected pattern | Pixels | Min | Mean | P50 | P90 | Max |
|---|---|---:|---:|---:|---:|---:|---:|
| PA Main Line / Center City-facing suburbs | Moderate to high radiance near Philadelphia, lower toward outer Chester County | 6,912 | 0.000 | 23.137 | 13.372 | 53.230 | 269.330 |
| Hudson Valley / Yonkers and lower Westchester | Highest radiance in Manhattan-adjacent/lower Westchester tracts | 3,600 | 0.000 | 18.845 | 11.352 | 44.818 | 137.320 |
| Hudson Valley / Putnam County | Lower radiance than lower Westchester | 6,480 | 0.000 | 2.446 | 1.440 | 4.990 | 61.025 |

## Proposed reductions

- `region_metrics`: census-tract zonal mean radiance.
- `district_metrics`: existing materialized-view rollup by tract/district
  overlap after promote.
- `listing_metrics`: none. The native grid is about 500 m, so this is
  neighborhood context only.
- Register `metric_definitions.direction = lower_better`.
- Validation threshold: at least 99% tract coverage across both current
  regions.
- Expected QA spot checks after staging:
  - Manhattan-adjacent Yonkers/lower Westchester tracts should be among the
    brightest Hudson Valley values.
  - Putnam County tracts should generally be lower than lower Westchester.
  - Philadelphia-facing PA Main Line tracts should generally exceed outer
    Chester County tracts.

## Implementation notes

- Use the verified local 2025 Annual VNL V2.2 median-masked file.
- Use `rasterstats.zonal_stats` or rasterio windowed reads against the existing
  tract geometries; do not resample to a finer grid for listing-level output.
- Treat NoData/background consistently with EOG product metadata. Valid
  background-masked non-lit cells may be zero; missing source coverage should
  remain missing and fail coverage validation if it exceeds the threshold.
- Preserve staging -> validate -> explicit promote.
- Do not call RentCast, do not infer districts, and do not start GVI.
