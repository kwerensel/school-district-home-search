# Commute minutes source onboarding

## Source choice

Approved Phase 7 source: openrouteservice Matrix API using the `driving-car`
profile and the anchors already stored in the region manifests:

- PA Main Line -> Center City Philadelphia (`39.9526,-75.1652`).
- Hudson Valley -> Grand Central (`40.7527,-73.9772`).

The ORS matrix endpoint accepts one-to-many, many-to-one, and many-to-many
location matrices and requires API-key authorization.

## Metric model

- `commute_minutes_center_city_philadelphia`
- `commute_minutes_grand_central`

Each value is a routed driving duration from a population-weighted tract
centroid to the approved anchor, stored in minutes and rolled up to districts
through the existing tract-overlap model. Runtime user anchors remain a Phase
10 request-time feature; these layer manifests cover only the fixed approved
regional anchors.

## Implementation gate

Production staging is blocked until `ORS_API_KEY` is configured and quota/
matrix-size limits are confirmed. When unblocked, batch requests within the
account limit, cache the exact request/response pairs, retain null/unroutable
cells as validation failures rather than invented times, and record routed
coverage, range, batch count, retries, and QA maps before promotion.
