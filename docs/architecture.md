# Architecture Notes

## 1. Problem → Solution Flow

```mermaid
flowchart LR
  A[Browse homes online] --> B[School filter feels unreliable]
  B --> C[Use official district boundaries]
  C --> D[Match each listing point to district polygon]
  D --> E[Filter listings by trusted districts]
  E --> F[Interactive browsing map]
```

## 2. Current Prototype Architecture

```mermaid
flowchart TD
  A[Manual CSV / RentCast API pull] --> B[Listing points: address, price, beds, baths, lat/lon]
  C[Official PA school district polygons] --> D[PostGIS]
  B --> D
  D --> E[Spatial join: ST_Contains district polygon + listing point]
  E --> F[listings_with_districts]
  G[good_school_districts table] --> H[good_district flag]
  F --> H
  H --> I[Export listings.geojson]
  I --> J[Lovable/Replit React map prototype]
```

## 3. Future Scalable Architecture

```mermaid
flowchart TD
  A[Listings API / IDX feed] --> B[Scheduled ingestion job]
  B --> C[Postgres + PostGIS]
  D[School district polygons by state] --> C
  E[District scoring, tags, curated collections] --> C
  C --> F[API layer]
  F --> G[React + Mapbox/Leaflet app]
  G --> H[Filters: price, beds, baths, good districts, near me]
  G --> I[Popups, saved searches, alerts]
```

## Product framing

The core differentiator is not generic listing search; it is a verified district intelligence layer:

```text
Listings are commodity data.
District intelligence is the product layer.
```
