# `aqi_annual_mean` source onboarding

## Decision

Use EPA AirData's account-free 2025 daily-summary ZIPs for criteria-pollutant
AQI values. These files are an official bulk distribution of AQS daily-summary
records. Reduce duplicate monitor/standard rows to one maximum AQI per site and
day, average those daily AQI values per qualifying site, then apply the approved
tract reducer: inverse-distance-squared weighting within 30 km, with a county
monitor mean fallback.

This resolves an ambiguity in the architecture's shorthand “annual summary
API.” AQS annual summaries contain pollutant concentrations in incompatible
units. The daily-summary response contains EPA's calculated `aqi` field, so an
annual mean of daily AQI remains one comparable index without recreating EPA's
pollutant breakpoints.

## Evidence

- Official API documentation: <https://aqs.epa.gov/aqsweb/documents/data_api.html>
- Official daily/AQI field documentation:
  <https://aqs.epa.gov/aqsweb/airdata/FileFormats.html>
- Official bulk-download index:
  <https://aqs.epa.gov/aqsweb/airdata/download_files.html>
- File pattern: `https://aqs.epa.gov/aqsweb/airdata/daily_<parameter>_2025.zip`
- Criteria parameter codes requested: ozone `44201`, PM2.5 `88101` and
  `88502`, PM10 `81102`, CO `42101`, SO2 `42401`, and NO2 `42602`.
- A public-test-account sample for PM2.5 returned 94 daily-summary rows for one
  week, including monitor coordinates, local date, event type, sample duration,
  pollutant standard, and non-null daily AQI records. Duplicate standard rows
  carried the same daily AQI, supporting an explicit max-per-site-day reducer.
- EPA API rules request sequential scripting, no more than 10 requests per
  minute, and a five-second pause between requests. The production reducer uses
  the separately published bulk files instead, downloading each archive once
  and reusing its exact cache across both regions.
- The 2025 ozone archive was verified available and contained the documented
  fields, including monitor identifiers/coordinates, local date, event type,
  pollutant standard, and daily AQI.

## Reduction and honesty rules

1. Read each national daily-summary archive in chunks and retain records inside
   a 30 km buffered region bounding box for the latest complete calendar year
   (`2025`).
2. Discard rows with null/non-numeric AQI or invalid coordinates.
3. For each AQS site and local date, take the maximum AQI across criteria
   pollutants and duplicate standards/event variants.
4. Keep sites with at least 30 valid daily AQI values and compute their annual
   arithmetic mean.
5. At each tract representative point, apply inverse-distance-squared weights
   to qualifying monitors within 30 km. If none are available, use the
   day-count-weighted qualifying-monitor mean for that tract's county.
6. Leave a tract missing when neither path exists. Never synthesize an
   address-level value or silently extend the interpolation radius.
7. Store only tract metrics. Explorer may inherit the containing tract value as
   “Neighborhood Context”; there is no listing-grain AQS claim.

## Credential status

On 2026-08-25, a minimal request using the configured `AQS_API_EMAIL` and
`AQS_API_KEY` returned `Email and/or key are invalid.` This does not block the
layer: the runner uses EPA's official account-free AirData archives. Correcting
the API pair is optional unless API-specific access is needed later.
