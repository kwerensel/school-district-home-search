# School District Home Search — Diagrams

## 1. Problem → Solution Flow

```mermaid
flowchart LR
  A[Browse listings on Zillow / Redfin] --> B[School rating or school info feels unreliable]
  B --> C[Listing may be near a good school but not inside the desired district]
  C --> D[Use official school district polygons]
  D --> E[Match each listing point to the true district]
  E --> F[Filter listings by trusted / good districts]
  F --> G[Browse a cleaner personalized home-search map]
```

## 2. Current Prototype Architecture

```mermaid
flowchart TB
  A[RentCast Sale Listings API] --> B[JSON files saved locally by ZIP]
  B --> C[Convert to GeoJSON listing points]
  C --> D[Import into PostGIS]
  E[Official PA school district polygons] --> D
  F[Good school districts table] --> D
  D --> G[Spatial join: listing point inside district polygon]
  G --> H[Enriched listings table]
  H --> I[Export listings.geojson]
  E --> J[Export districts.geojson]
  I --> K[Lovable / React map app]
  J --> K
  K --> L[Filters: price, beds, baths, good districts only]
```

## 3. Future Scalable Architecture

```mermaid
flowchart TB
  A[Listings API / IDX feed] --> B[Scheduled ingestion job]
  B --> C[Postgres + PostGIS]
  D[Official district polygons by state] --> C
  E[District ratings, tags, curated collections] --> C
  C --> F[District assignment service]
  F --> G[App API]
  G --> H[React + Mapbox frontend]
  H --> I[Browse by state / metro / near me]
  H --> J[Filters: budget, beds, baths, commute, district quality]
  H --> K[Saved searches and alerts]
```

## 4. Data Model

```mermaid
erDiagram
  LISTINGS {
    int id
    string address
    string city
    string state
    string zip
    float price
    float beds
    float baths
    string url
    geometry geom
  }
  SCHOOL_DISTRICTS {
    int id
    string district_name
    string county_name
    string state
    geometry geom
  }
  GOOD_DISTRICTS {
    string district_name
    string collection_name
    string notes
  }
  LISTINGS_WITH_DISTRICTS {
    int listing_id
    string school_district
    string county_name
    boolean good_district
    geometry geom
  }
  LISTINGS ||--o| LISTINGS_WITH_DISTRICTS : enriched_into
  SCHOOL_DISTRICTS ||--o{ LISTINGS_WITH_DISTRICTS : contains
  GOOD_DISTRICTS ||--o{ LISTINGS_WITH_DISTRICTS : flags
```

## 5. Agentic Cleanup Workflow

```mermaid
flowchart LR
  A[New files: CSV, JSON, GeoJSON, SQL, screenshots] --> B[Agent scans folder]
  B --> C[Classify: raw data, processed data, scripts, docs]
  C --> D[Detect secrets and exclude API keys / .env]
  D --> E[Move files into repo structure]
  E --> F[Update manifest and README]
  F --> G[Open review checklist]
  G --> H[Commit to private GitHub repo]
```
