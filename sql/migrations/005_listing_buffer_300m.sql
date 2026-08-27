ALTER TABLE listing_metrics
  DROP CONSTRAINT IF EXISTS listing_metrics_grain_check;

ALTER TABLE listing_metrics
  ADD CONSTRAINT listing_metrics_grain_check
  CHECK (grain IN ('point', 'buffer_100m', 'buffer_300m', 'buffer_500m'));

ALTER TABLE staging.layer_listing_metrics
  DROP CONSTRAINT IF EXISTS layer_listing_metrics_grain_check;

ALTER TABLE staging.layer_listing_metrics
  ADD CONSTRAINT layer_listing_metrics_grain_check
  CHECK (grain IN ('point', 'buffer_100m', 'buffer_300m', 'buffer_500m'));
