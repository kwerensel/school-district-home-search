# Supplemental Noise Sources — Source Onboarding

## Decision

Use OpenStreetMap for mapped emergency-response facilities, nightlife venues,
and industrial land-use polygons, plus the Federal Railroad Administration's
North American Rail Network (NARN) for operational freight-capable rail lines.
Publish each quantity under a unit-honest companion metric rather than placing
distances, counts, percentages, and line densities under one `noise_sources`
key. These metrics remain separate from BTS modeled dBA and are never combined
into a synthetic sound score.

## Source evidence

- OpenStreetMap is queried through the read-only Overpass API using the exact
  tags approved in the architecture:
  - potential siren facilities: `amenity=fire_station|police|hospital`;
  - nightlife: `amenity=bar|pub|nightclub`;
  - industrial adjacency: polygonal `landuse=industrial`.
- OSM points and facility/venue polygons are both retained. A representative
  point is used only for density and buffer counts; listing distance is measured
  to the mapped feature geometry.
- FRA identifies itself as the federal government's authoritative source for
  passenger and freight rail network information and links directly to its
  NARN Lines REST service. The live service says the dataset was updated on
  July 21, 2026 and provides geometry at 1:24,000 or better in the U.S.
- FRA NARN's `NET` domain distinguishes current operational network classes
  from out-of-service, abandoned, removed, trail, and transit-only classes.
  Groundtruth keeps `M`, `I`, `O`, `S`, and `Y` (main network, industrial
  leads, long sidings, and yard tracks) and excludes `X`, `A`, `R`, `T`, and
  `Z`. This is deliberately labeled **freight-capable**, because NARN does not
  promise live train frequency or horn activity.

## Published metrics

| Metric | Grain | Meaning |
|---|---|---|
| `noise_siren_density` | tract | mapped fire/police/hospital facilities per km² |
| `noise_siren_distance_m` | listing | straight-line distance to nearest mapped emergency-response facility |
| `noise_nightlife_density` | tract | mapped bar/pub/nightclub venues per km² |
| `noise_nightlife_count_300m` | listing | mapped nightlife venue count within 300 m |
| `noise_industrial_land_pct` | tract | mapped industrial polygon share of tract land |
| `noise_industrial_distance_m` | listing | distance to nearest mapped industrial polygon edge; ≤500 m may be labeled adjacent |
| `noise_freight_rail_density` | tract | operational freight-capable rail km per km² |
| `noise_freight_rail_distance_m` | listing | distance to nearest operational freight-capable FRA line |

## Honesty and limitations

- These are potential-source proximity indicators, not sound measurements.
- OSM completeness, tagging, venue status, and operating hours vary by place.
- A nearby hospital, police station, or fire station does not imply frequent
  siren use; a nearby venue does not imply it is loud or currently operating.
- Industrial polygons cover many kinds of uses and do not describe activity,
  emissions, or hours.
- NARN location/status is suitable for screening, but FRA warns railroad
  conditions can change. The operational filter is not a train-frequency feed.
- All distance operations use projected meter coordinates; stored project
  geometry remains EPSG:4326.

## Gate

Before promotion, require complete tract/listing coverage as applicable,
finite values inside each manifest range, nonempty relevant source classes,
source-count evidence in every report, QA maps for both regions, and a pinned
listing check near a mapped emergency-response facility or freight-capable
rail line.
