# park_access source onboarding

## Source choice

Approved Phase 7 source path: OpenStreetMap parks and USGS PAD-US public-access
protected/open-space polygons.

Use two complementary sources:

- OpenStreetMap via `osmnx` for local park, playground, recreation ground,
  nature reserve, pitch, garden, and related open-space polygons.
- USGS PAD-US Public Access FeatureServer for nationally aggregated protected
  lands and public-access open space.

PAD-US is the official national inventory of U.S. protected areas and includes
parks, protected open space, public lands, conservation easements, and other
managed lands. USGS documentation says PAD-US includes a public-access measure,
but also notes that public access is often assigned categorically and local
park data gaps exist. That makes PAD-US a strong supplement, not a complete
local-park replacement.

## Evidence gathered

- PAD-US Data Overview says PAD-US is available as national/state geodatabase
  downloads and web services, and cites PAD-US 4.x under DOI
  `10.5066/P96WBCHS`.
- PAD-US Web Services lists a "Public Access" feature layer view intended to
  show open, restricted, closed, and unknown public access categories.
- ArcGIS item `c91a5655a1be428daeb778888e60db24` exposes
  `https://services.arcgis.com/v01gqwM5QqNysAAi/arcgis/rest/services/PADUS_Public_Access/FeatureServer`.
- The layer metadata identifies `Pub_Access` categories:
  - `OA`: Open Access
  - `RA`: Restricted Access
  - `XA`: Closed Access
- The layer's supported query formats include JSON, GeoJSON, and PBF, with
  `maxRecordCount` 2000.

## Reduction

The app value should be simple and legible:

- Tract grain: share of tract area within 800 m of a public park/open-space
  polygon. This aligns with the Phase 7 task language.
- Listing grain: distance in meters from the listing point to the nearest
  park/open-space polygon edge.

If later we add population-weighted or parcel/residential-mask weighting, keep
the metric name stable only if the semantic remains "park access"; otherwise
add a companion metric.

## Inclusion rules

PAD-US:

- Include `Pub_Access = 'OA'` as public access.
- Track `Pub_Access = 'RA'` separately in validation and QA; do not include it
  in the default metric unless product copy explicitly labels restricted or
  permit/seasonal access.
- Exclude `Pub_Access = 'XA'` and unknown access from the default metric.

OpenStreetMap:

- Start with polygons/multipolygons tagged as `leisure=park`, `leisure=garden`,
  `leisure=playground`, `leisure=recreation_ground`, `leisure=nature_reserve`,
  `leisure=pitch`, `boundary=protected_area`, `landuse=recreation_ground`, or
  `landuse=village_green`.
- Exclude private-access polygons when explicit access tags indicate private,
  no, customers, or similar non-public access.
- Preserve source tags in intermediate artifacts for QA, but stage only the
  final metric values.

## Display grain and honesty notes

This is an access context metric. It can say "near a mapped public park/open
space" or "tract share within 800 m of mapped access polygons." It should not
promise:

- open gates at a particular entrance,
- trail/sidewalk connectivity,
- seasonal access,
- permit availability,
- schoolyard access,
- quality, safety, amenities, or playground condition.

## Implementation notes

- Query/crop both sources by region bounds plus an 800 m buffer.
- Clean all geometries to EPSG:4326 for storage/staging; use projected CRS or
  geography operations for meter buffers and distances.
- Union/deduplicate overlapping OSM and PAD-US polygons before distance and
  buffer-share calculations.
- Emit validation stats for source feature counts, invalid/fixed geometries,
  open/restricted/closed PAD-US counts, OSM tag counts, tract coverage, listing
  coverage, value range, and nearest-distance range.
