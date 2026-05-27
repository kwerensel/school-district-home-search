# School District Home Search Prototype

A personal GIS/web-app prototype for browsing real estate listings using verified school district boundaries instead of relying only on listing-site school filters.

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
