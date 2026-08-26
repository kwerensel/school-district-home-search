# Commute minutes source onboarding

## Source choice

Approved Phase 7 source: openrouteservice Matrix API using the `driving-car`
profile and the anchors already stored in the region manifests. Requests use
the current `api.heigit.org/openrouteservice` host. Origins use the official
2024 ACS 5-year B01003 table-based Summary File and TIGER/Line block-group
representative points to construct a reproducible population-weighted point
for each tract without requiring a separate Census API credential:

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

## Implementation evidence

`ORS_API_KEY` is configured and a live request against the HeiGIT matrix host
returned a routed duration. Production ingestion batches 49 origins plus one
anchor, caches exact request/response pairs, retains null/unroutable cells as
explicit missing observations rather than invented times, and records origin, routed
coverage, range, batch, retry, routing-graph, and QA evidence before promotion.
The manifests require at least 99% tract coverage; every routed and unroutable
origin must be accounted for in the validation report.
