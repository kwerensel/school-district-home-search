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

## Implementation gate

Production staging is blocked until `TRANSITLAND_API_KEY` is configured and
the account quota is confirmed to support paginating both project regions.
When unblocked, cache every page plus the returned feed-version identifiers,
deduplicate stable stop identities, record active-feed provenance, and emit
stop-count, tract-coverage, listing-coverage, range, pagination, and spatial QA
statistics before promotion.
