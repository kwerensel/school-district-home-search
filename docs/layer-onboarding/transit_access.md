# Transit access source onboarding

## Source choice

Approved Phase 7 source: Transitland v2 REST API stops from active GTFS feed
versions.

The current REST API base is `https://transit.land/api/v2/rest`. Its stop
endpoint supports bounding-box search, JSON/GeoJSON response formats,
pagination, and active-feed results. Every endpoint request requires an API key
through the `apikey` header or query parameter.

## Metric model

- `transit_access`: active mapped GTFS stop count per census-tract square
  kilometer.
- `transit_distance_m`: straight-line listing-point distance to the nearest
  mapped active-feed stop.

These remain separate because density and meters have different units and
directions. Neither metric claims service frequency, span, reliability,
destination usefulness, fare affordability, ADA accessibility, or a walkable
route to the stop.

## Implementation evidence

`TRANSITLAND_API_KEY` is configured and a live bounded stop request returned an
active-feed result plus a pagination cursor. Production ingestion caches every
page plus returned feed-version identifiers, deduplicates stable stop
identities, records active-feed provenance, and emits stop-count,
tract-coverage, listing-coverage, range, pagination, and spatial QA statistics
before promotion.
