# Groundtruth

A deterministic geospatial home-search platform for browsing frozen listings
by verified school-district boundaries and comparing supported districts by
budget and lifestyle context.

## Problem

When browsing homes online, school filters can feel misleading because ZIP codes, towns, nearby schools, and actual school district boundaries do not always line up. This project tests a better workflow:

```text
listing latitude/longitude
→ official school district polygon
→ spatial join in PostGIS
→ trusted-district flag
→ interactive map filters
```

## Current prototype

- Pull listings from a legal listings API or manually curated CSV.
- Store/listing points in PostGIS.
- Load official school district polygons.
- Run a spatial join to assign each listing to the district containing its point.
- Export app-ready GeoJSON for a Lovable/Replit/React map prototype.

## Planned Discovery constraints and preference ranges

The Discovery profile must distinguish strict requirements from flexible
preferences, especially once commute data is available. Each supported
criterion should allow the user to choose one of these modes:

- **Must have:** exclude districts that fail the requirement.
- **Prefer:** retain districts but rank those meeting the preference higher.
- **Doesn't matter:** omit the criterion from filtering and ranking.

Range-based criteria should support an ideal target and a hard limit. For
example, a commute profile may prefer 35 minutes or less, accept up to 50
minutes, and exclude districts over 50 minutes. Multiple commute anchors must
have independently configurable ranges.

Discovery should apply this profile transparently:

1. Determine the explicit comparison area and state how many districts it
   contains.
2. Apply hard constraints without silently relaxing them.
3. State how many districts remain eligible.
4. Rank eligible districts using flexible preferences.
5. Explain each result's strengths and tradeoffs.
6. If nothing qualifies, offer the closest misses and identify which
   constraint each one fails.

Hard constraints, preferred ranges, anchors, and the comparison area must be
encoded in the shareable URL. The same model should extend beyond commute to
purchasing power, flood exposure, transit and park access, and environmental
preferences where the source resolution supports the requested constraint.

The current prototype uses the selected supported region (Hudson Valley, PA
Main Line, or both) as the comparison area. As coverage expands, the profile
must let the user define that universe explicitly—for example by named region,
map extent, radius from a place, commute catchment, and included or excluded
districts. Results should always say `#x of N districts` after hard constraints
are applied. A normalized internal score may order the list, but the UI should
not present that score as a probability, a `73/100` grade, or the percentage of
requirements satisfied.

## Current Discovery UX conventions

- Call the financial concept **purchasing power** and the district output
  **estimated max home price**. Keep that estimate separate from the district
  median home value and expose the mortgage-rate, credit, tax, insurance, and
  PMI assumptions behind the estimate.
- Explain ranked results with their explicit comparison position, strongest
  relative factors, and important tradeoffs. Do not show the normalized overall
  score to consumers.
- Allow one district-level map layer at a time for purchasing power, tree
  coverage, FEMA flood-zone exposure, light pollution, EPA walkability, and
  natural-hazard risk, and mapped park access. Every layer needs a
  plain-language legend and must state its geographic grain.
- Describe district flood exposure as the share of district land in a mapped
  FEMA Special Flood Hazard Area. Keep that distinct from the Explorer property
  flag, which only says whether the listing point falls inside the mapped zone.
- Present tree coverage and light pollution with consumer categories while
  retaining the raw value as supporting detail. VIIRS radiance is not a
  1-to-10 score, and canopy height is not tree age or old-growth evidence.

## Planned walking access, comfort, and pedestrian safety

Walking access must be computed along a connected, traversable pedestrian
network. Straight-line proximity to a park, transit stop, business, or other
destination is not enough: a nearby place may be unreachable because of a
highway, river, missing crossing, disconnected street network, or other
barrier. Discovery and Explorer should use walking-route distance or time and
show the route or 10/15-minute walking catchment on the map. Proximity may be
retained only as a clearly labeled fallback when routable pedestrian data is
unavailable.

Keep these concepts distinct:

- **Walking access:** destinations and daily-needs categories reachable by an
  actual pedestrian route, including parks, public transit, groceries,
  pharmacies, schools, restaurants, and cafes.
- **Walking comfort:** known sidewalk continuity, crossing infrastructure,
  road-traffic stress, shade, slope, greenway exposure, and other qualities
  that affect how pleasant a route may feel.
- **Pedestrian traffic safety context:** vehicle speeds and volumes, roadway
  design, high-stress crossings, and geocoded pedestrian crash history. Do not
  present this as a guarantee that an area or route is safe.

A future consumer-facing "nice-to-walk" result may be built from these
components, but the underlying methodology must remain deterministic,
versioned, auditable, and coverage-aware. It must:

- show the component evidence and important tradeoffs instead of relying on an
  unexplained overall percentage;
- distinguish observed data from proxies and unknown/missing coverage;
- refuse to score areas below a documented coverage threshold;
- expose the supporting sidewalks, crossings, routes, road stress, shade, and
  crash context as map layers;
- allow users to set hard constraints, preferred ranges, and personal weights;
- avoid folding crime data or a general claim of personal safety into the
  pedestrian model without a separately approved and defensible methodology.

The preferred product language is **walking comfort** or **nice-to-walk
potential**, not an unqualified "safe walking score." If a numeric index is
eventually shown, its reference population and scale must be explicit; a
plain-language category with reasons and tradeoffs is the safer default.

## Repo structure

```text
app/public/data/        GeoJSON files for a static frontend prototype
data/raw/               Original input files kept for local reference
data/processed/         Cleaned/exported app-ready data
docs/                   Notes, screenshots, diagrams, build logs
sql/                    SQL scripts for PostGIS processing
scripts/                Local helper scripts for API pulls/conversion
```

## Important safety notes

Do not commit API keys, `.env` files, or unrestricted paid API data. Keep this repo private while experimenting.

## Core data files currently included

- `data/raw/home_listings_raw.csv` — early manual listing CSV.
- `data/raw/Zip_zhvi_uc_sfr_tier_0.33_0.67_sm_sa_month.csv` — Zillow ZHVI ZIP time series export.
- `data/processed/listings.geojson` — app-ready listing points from the first prototype.
- `app/public/data/listings.geojson` — copy for frontend upload/use.
