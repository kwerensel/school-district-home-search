# Commute anchor address lookup

On 2026-10-18 the user approved Geocodio **free tier only**. Mapbox permanent
geocoding was considered but not selected. The integration uses Geocodio v2
single-address forward lookup, USA only, with no paid data appends. It never
assigns school districts: those remain official NCES/PostGIS joins.

Official references reviewed on that date:

- [Pricing](https://www.geocod.io/pricing): 2,500 free lookups per day, then
  $1 per 1,000. No payment method is needed within the free tier.
- [Terms section 8.4](https://www.geocod.io/terms-of-use): storage and reuse
  permitted subject to underlying source licenses and applicable attribution.
- [API documentation](https://www.geocod.io/docs/): v2 forward geocoding,
  Bearer authorization, ordered candidates with accuracy and source metadata.

## Configuration and caps

Set `GEOCODIO_API_KEY` in the private environment and
`GEOCODIO_FREE_TIER_ONLY=true` only after confirming that the provider account
has **paid usage disabled/no payment method**. Name the separate app key anything descriptive, such as `Groundtruth commute
lookup`. Grant only **Geocoding → GET /v2/geocode**; batch POST, Lists, Distance
and Jobs permissions are not needed. The key label does not affect the app;
the environment variable must be named exactly `GEOCODIO_API_KEY`. Configure the provider account's usage limit. Never paste the key into chat,
logs or version control. Apply `012_geocoder_quota.sql` before enabling.

The server reserves one request atomically in `geocoder_daily_usage` before
calling the provider and refuses after **1,000 lookups per America/New_York
calendar day**, including failed calls. This lower app limit leaves headroom
below the provider allowance. Other applications sharing the provider account
can still consume its free quota, so the provider-side no-paid-use setting is
mandatory. Database failure prevents the provider call.

No request runs on keystrokes: the user submits an address explicitly and
confirms a candidate. Coordinates, formatted label, accuracy, and source are
returned; raw provider error bodies and credentials are never returned. Address
lookups are private/no-store responses. Saved/shareable user anchors may retain
the chosen coordinates. Keep source attribution with displayed candidates.
Manual coordinate entry remains available without the key.

## Live acceptance — October 19, 2026

The user saved the key locally and confirmed paid usage is disabled or no payment
method is attached. `GEOCODIO_FREE_TIER_ONLY=true` is enabled locally. The private
environment file remains gitignored; no account billing settings were changed.

The Philadelphia City Hall public address returned one candidate with valid
coordinates and confidence 1. Selecting the candidate filled the destination;
adding it persisted the anchor in the shareable URL. The existing 45-minute ORS
filter returned 27 districts. The initial dev server failed twice; direct provider
and Node adapter checks passed, and restarting the local server resolved the UI
failure. Five total attempts were reserved in the atomic daily counter, including
the failed calls and diagnostics; no paid appends were requested. No further
lookup requests were needed. Candidate cards now display provider/source attribution.

All 79 app tests pass (two unrelated opt-in skips), with TypeScript/build and focused
component lint checks passing. Local proof:
`data/reports/qa/geocodio-live-commute.png`. No production deployment.
