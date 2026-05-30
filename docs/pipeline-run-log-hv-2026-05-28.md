# Hudson Valley Pipeline Run Log
**Date:** 2026-05-28  
**Region:** Westchester, Rockland, Putnam, Orange counties — New York  
**Run type:** New region expansion + PA dry-run validation

---

## Phase 1: PA Dry-Run Validation (read-only)

| Check | Result |
|-------|--------|
| `pa_school_districts` row count | 500 |
| `pa_school_districts` SRID | 3857 (Web Mercator) — as expected |
| Valid geometries | 499 / 500 |
| Invalid geometry | William Penn SD (ring self-intersection) — no PA listings affected |
| `rentcast_listings_with_districts` row count | 251 |
| Listings with geometry | 251 / 251 |
| Listings with district assigned | 251 / 251 |
| Spatial join validation (all 251) | 0 true mismatches |

**Decision:** All PA listings have correct district assignments. The "MISMATCH" status in the raw check was formatting only — shapefile uses "Lower Merion SD", stored column uses "Lower Merion". No data correction needed.

**Note on PA table:** `listings_map_ready` stores `price`, `beds`, `baths` as `character varying`. This is a known issue. It was not corrected here (read-only constraint) but is fixed in the HV equivalent.

---

## Phase 2: HV Data Ingestion

### County boundaries
- **Source:** Census TIGER 2023 national county file
- **File:** `data/shapefiles/ny/counties/tl_2023_us_county.shp`
- Filtered to NY state (STATEFP='36'), then spatially to 4 HV counties
- Loaded as temporary table `ny_counties_temp` (not a permanent project table)

### ZIP code derivation
- **Method:** `ST_Within(ST_Centroid(us_zctas.geom), ny_counties_temp.wkb_geometry)`
- Used centroid containment (not `ST_Intersects`) to avoid picking up border ZCTAs in CT/NJ/PA
- **Result:** 155 ZIPs — Westchester (72), Orange (46), Rockland (28), Putnam (9)

### NY school district boundaries
- **Source:** NCES EDGE SY2022-23 national shapefile
- **File:** `data/shapefiles/ny/school_districts/nces_edge/EDGE_SCHOOLDISTRICT_TL23_SY2223/`
- Filtered to NY (STATEFP='36'), projected to SRID 3857 to match `pa_school_districts`
- **Rows imported:** 681
- **Invalid geometries:** 18 (ring self-intersections) — repaired with `ST_MakeValid()`
- **Table:** `ny_school_districts`

### HV listings (RentCast API)
- **Endpoint:** `GET /v1/listings/sale?zipCode={ZIP}&status=Active&limit=500`
- **ZIPs queried:** 155
- **Errors:** 0
- **Raw JSON files:** `data/rentcast_hv/rentcast_{ZIP}.json` (155 files)
- **Total listings:** 4,254 (0 missing coordinates)
- **GeoJSON:** `data/rentcast_hv/hv_listings_raw.geojson`
- **Table:** `rentcast_hv_listings_raw` (SRID 4326)

**Note:** RentCast API does not return `listingUrl`. The `url` field is null for all HV listings (same as PA data). This is a RentCast API plan limitation, not a pipeline error.

---

## Phase 3: Spatial Joins and Enrichment

### Coordinate systems
- Listings: SRID 4326 (WGS84)
- Districts: SRID 3857 (Web Mercator)
- Transform applied: `ST_Transform(listing.geom, 3857)` before `ST_Within()`

### Spatial join
- **Method:** `LEFT JOIN LATERAL ... ST_Within() LIMIT 1` — ensures each listing gets at most one district
- **Results:** 4,250 / 4,254 matched via `ST_Within()`
- **Fallback:** 4 waterfront listings (Haverstraw ×2, Croton-on-Hudson, Rye) had no polygon match — assigned via `ORDER BY ... <->` nearest-district, all within 300m
- **Final:** 4,254 / 4,254 with district assigned (100%)

### District name normalization
Shapefile full names normalized to display names by stripping standard suffixes:
- ` Union Free School District` → removed
- ` Central School District` → removed
- ` City School District` → removed
- ` School District` → removed
- Special case: `Union Free School District of the Tarrytowns` → `Tarrytowns`

**Result:** 75 distinct district names. Note: 6 districts span county lines (e.g., Lakeland CSD in Westchester and Putnam) — listings show the RentCast-assigned county, not the district's primary county. Correct behavior.

### good_district flag
**Criterion for this iteration:** Explicit approved list of 18 districts based on well-established public reputation for academic performance. Raw NCES names matched exactly.

**Approved list:**
- Westchester (12): Ardsley, Blind Brook-Rye, Briarcliff Manor, Bronxville, Byram Hills, Chappaqua, Edgemont, Harrison, Irvington, Pelham, Rye City, Scarsdale
- Rockland (3): Nanuet, Pearl River, South Orangetown
- Putnam (1): Haldane
- Orange (2): Cornwall, Warwick Valley

**Future replacement:** This step is intentionally isolated. To replace with PVAAS or Stanford SEDA data, update only the `d.name = ANY(ARRAY[...])` expression in the pipeline SQL — no other pipeline logic changes needed.

**Result:** 572 listings with `good_district = true`

### Output table: `rentcast_hv_listings_with_districts`
Mirrors structure of `rentcast_listings_with_districts` (PA equivalent). SRID 4326. Spatial index on `geom`.

---

## Phase 4: Frontend-Ready Output

### `hv_listings_map_ready`
Same column structure as `listings_map_ready` (PA) with these corrections:
- `price`: `integer` (was `character varying` in PA table)
- `beds`: `integer` (was `character varying` in PA table)
- `baths`: `double precision` (was `character varying` in PA table)

### `hv_district_home_values`
New table with district polygons + price aggregates. Geometry stored at SRID 4326. Includes:
- `name` (normalized), `district_raw_name` (NCES full name)
- `listing_count`, `median_price`, `min_price`, `max_price`, `avg_price`
- `good_district` boolean
- 71 districts (HV counties only; 4 border-county listings are in Sullivan/Dutchess districts and are excluded from this table)

### GeoJSON exports
| File | Features | Size |
|------|----------|------|
| `data/processed/hv_listings.geojson` | 4,254 listings | 1.5 MB |
| `data/processed/hv_districts.geojson` | 71 districts | 1.3 MB |

---

## Database tables created (this run)

| Table | Description | Permanent? |
|-------|-------------|-----------|
| `ny_counties_temp` | Census TIGER county boundaries for NY | Temporary (can drop) |
| `ny_school_districts` | All 681 NY NCES districts, SRID 3857 | Yes |
| `rentcast_hv_listings_raw` | 4,254 raw RentCast listings, SRID 4326 | Yes |
| `rentcast_hv_listings_with_districts` | Enriched listings + district + good_district | Yes |
| `hv_listings_map_ready` | Frontend-optimized listings, correct numeric types | Yes |
| `hv_district_home_values` | District polygons + price aggregates, SRID 4326 | Yes |

---

## Issues encountered and resolutions

| Issue | Resolution |
|-------|------------|
| PA: 1 invalid geometry (William Penn SD) | No action — no listings affected. Log for reference. |
| HV: 18 invalid district geometries | Repaired with `ST_MakeValid()` before indexing |
| SSL cert error in Python `urllib` | Fixed by using `certifi` CA bundle via `ssl.create_default_context()` |
| 4 waterfront listings outside district polygons | Nearest-district fallback (all ≤300m, all correct) |
| RentCast `listingUrl` field absent | Not available in API response — `url` is null for all HV listings (same as PA) |

---

## Future automation flags (manual in this iteration)

1. **good_district classification** — Currently an explicit approved list. Replace the `= ANY(ARRAY[...])` expression with a threshold query against PVAAS growth data or Stanford SEDA scores.
2. **ZIP derivation** — Currently inline SQL. Wrap as a reusable function accepting a county name array.
3. **Regional expansion** — Pattern is established: new NCES shapefile → new district table → RentCast pull → spatial join → output tables. No existing tables modified.
4. **Scheduling** — Currently manual. Wrap in a cron job (weekly/monthly) to refresh `rentcast_hv_listings_raw` and downstream tables.
