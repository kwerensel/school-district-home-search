# Housing data

Drop your GeoJSON files here:

- `listings.geojson` — Point features with properties:
  `address, city, zip, price, beds, baths, url, school_district, good_district`
- `districts.geojson` — Polygon/MultiPolygon features with properties:
  `name` (matching `school_district`), optional `good_district`

They are served at `/data/listings.geojson` and `/data/districts.geojson`.
