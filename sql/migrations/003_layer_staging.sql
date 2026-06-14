CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS staging.layer_region_metrics (
  region_group text NOT NULL,
  metric_key text NOT NULL,
  region_slug text NOT NULL REFERENCES regions(slug) ON DELETE CASCADE,
  value double precision NOT NULL,
  vintage text NOT NULL,
  PRIMARY KEY (region_group, metric_key, region_slug, vintage)
);

CREATE TABLE IF NOT EXISTS staging.layer_listing_metrics (
  region_group text NOT NULL,
  metric_key text NOT NULL,
  listing_id bigint NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  grain text NOT NULL CHECK (grain IN ('point','buffer_100m','buffer_500m')),
  value double precision NOT NULL,
  vintage text NOT NULL,
  PRIMARY KEY (region_group, metric_key, listing_id, grain, vintage)
);
