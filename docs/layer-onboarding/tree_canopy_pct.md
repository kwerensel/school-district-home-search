# tree_canopy_pct onboarding note

Status: drafted for human approval before full ingestion module.

## Candidate source

Selected source: USDA Forest Service / MRLC NLCD Tree Canopy Cover Product
Suite v2025.6, using the CONUS NLCD TCC 2025 raster:

- Product page: https://data.fs.usda.gov/geodata/rastergateway/treecanopycover/
- Download: https://data.fs.usda.gov/geodata/rastergateway/treecanopycover/docs/v2025-6/nlcd_tcc_conus_2025_v2025-6_wgs84.zip
- Source publisher: USDA Forest Service as an MRLC partner.
- Citation vintage for this metric: 2025.
- Release note on product page: v2025.6 product suite released in 2026.

Reason for choosing this source: it is the current official NLCD TCC product
listed by the Forest Service raster gateway. The architecture spec named NLCD
TCC as the Phase 5 `tree_canopy_pct` source; the current product page now
offers annual CONUS NLCD TCC files through 2025. This is fresher than the older
ScienceBase item for "National Land Cover Database (NLCD) 2021 USFS Tree
Canopy Cover".

## Candidate comparison

Selected: NLCD TCC v2025.6.

- Pros: official Forest Service/MRLC product, 30 m national coverage, annual
  CONUS files through 2025, values directly match the desired percentage metric.
- Processing meaning: post-processed from Forest Service Science TCC with
  masking, filtering, minimum-mapping-unit routines, and temporal noise
  reduction for NLCD-style use.

Rejected for this layer: Forest Service Science TCC.

- Reason: it is the direct model-output product and may retain canopy-like
  estimates in water or non-tree cropland. That can be useful for scientific
  uncertainty analysis, but `tree_canopy_pct` in the app should be the cleaner
  NLCD-facing layer.

Rejected as stale primary source: ScienceBase 2021 USFS TCC item.

- Reason: official, but older than the current v2025.6 raster gateway release.
  It remains useful as archive/provenance evidence, not as the default ingest.

## Source shape

Remote ZIP member inspected without downloading the full 3.6 GB archive:

| Field | Value |
|---|---|
| ZIP file | `nlcd_tcc_conus_2025_v2025-6_wgs84.zip` |
| Raster member | `nlcd_tcc_conus_wgs84_v2025-6_20250101_20251231.tif` |
| CRS | WGS84-datum Albers equal-area projection |
| Pixel size | 30 m |
| Shape | 154,180 x 97,279 |
| Band dtype | uint8 |
| NoData | 255 |
| Valid data range | 0-100 percent |

## Sample value checks

Windowed reads sampled two approximately 10 km regional windows from the remote
ZIP via byte-range requests; no full raster was downloaded.

| Region sample | Pixels | Min | Mean | P50 | P90 | Max | Share > 30% |
|---|---:|---:|---:|---:|---:|---:|---:|
| PA Main Line / Wayne | 135,372 | 0% | 45.05% | 47% | 83% | 98% | 66.66% |
| Hudson Valley / Ardsley | 180,840 | 0% | 40.43% | 39% | 84% | 97% | 58.61% |

These ranges fit the manifest range `[0, 100]` and are plausible for suburban
Northeast landscapes with mixed mature canopy, open parcels, roads, and
developed surfaces.

## Proposed reductions

- `region_metrics`: census-tract zonal mean percent canopy.
- `listing_metrics`: 100 m and 500 m buffer means.
- Do not expose listing point samples. At 30 m native resolution, point samples
  could overstate address-level precision; buffer means are the honest Explorer
  grain.
- Keep raw ZIP/TIFF artifacts under `data/raw/tree_canopy_pct/` if cached.
- Rasters never enter Postgres.
- Assert all loaded geometries remain EPSG:4326 after reduction.
- Validation threshold: at least 99% tract coverage and 4,505/4,505 listing
  coverage for listing-grain outputs.

## Relationship to canopy_height_m

`canopy_height_m` measures vertical structure and can distinguish tall mature
trees from low or sparse vegetation. `tree_canopy_pct` measures horizontal
canopy cover at 30 m resolution. These are complementary: a street can have
high cover but moderate height, or scattered tall trees with lower cover.
