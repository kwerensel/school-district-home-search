-- Example Zillow latest ZIP home-value extraction.
-- Update the source table/date column as needed.

DROP TABLE IF EXISTS zillow_latest;

CREATE TABLE zillow_latest AS
SELECT
    "RegionName"::text AS zip_code,
    "State" AS state,
    "Metro" AS metro,
    "CountyName" AS county,
    "2026-03-31" AS zhvi_latest
FROM "Zip_zhvi_uc_sfr_tier_0.33_0.67_sm_sa_month"
WHERE "State" IN ('PA', 'NY');
