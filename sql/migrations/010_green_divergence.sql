-- Derived only from promoted inputs. Compare ranks at the displayed grain;
-- never average tract percentile differences to manufacture district ranks.
-- Latest input vintages are retained separately because the source years differ.
CREATE OR REPLACE VIEW green_divergence_region_metrics AS
WITH latest AS (
  SELECT DISTINCT ON (rm.region_id, rm.metric_key)
    rm.*, r.region_group, r.region_type
  FROM region_metrics rm JOIN regions r ON r.id = rm.region_id
  WHERE rm.metric_key IN ('tree_canopy_pct', 'gvi_ndvi_street')
    AND rm.value > '-Infinity'::double precision
    AND rm.value < 'Infinity'::double precision
  ORDER BY rm.region_id, rm.metric_key, rm.vintage DESC, rm.computed_at DESC
), paired AS (
  SELECT c.region_id, c.region_group, c.region_type,
    c.value AS canopy_value, g.value AS gvi_value,
    c.vintage AS canopy_vintage, g.vintage AS gvi_vintage,
    GREATEST(c.computed_at, g.computed_at) AS computed_at
  FROM latest c JOIN latest g USING (region_id)
  WHERE c.metric_key = 'tree_canopy_pct' AND g.metric_key = 'gvi_ndvi_street'
), ranked AS (
  SELECT *,
    percent_rank() OVER (PARTITION BY region_group, region_type ORDER BY canopy_value) AS canopy_percentile,
    percent_rank() OVER (PARTITION BY region_group, region_type ORDER BY gvi_value) AS gvi_percentile
  FROM paired
)
SELECT region_id, 'green_divergence'::text AS metric_key,
  100.0 * (canopy_percentile - gvi_percentile) AS value,
  'canopy:' || canopy_vintage || '|gvi:' || gvi_vintage AS vintage,
  computed_at, canopy_value, gvi_value, canopy_vintage, gvi_vintage,
  canopy_percentile, gvi_percentile
FROM ranked;

-- Use a fixed, invoker-rights SQL statement so the existing forward-only
-- migration runner may rebuild district_metrics without a dependent-view error.
CREATE OR REPLACE FUNCTION green_divergence_district_inputs()
RETURNS TABLE (district_region_id bigint, metric_key text, value double precision,
               vintage text, computed_at timestamptz)
LANGUAGE plpgsql STABLE SET search_path = public AS $$
BEGIN
  RETURN QUERY EXECUTE
    'SELECT district_region_id::bigint, metric_key::text, value::double precision,
            vintage::text, computed_at::timestamptz FROM public.district_metrics';
END;
$$;

CREATE OR REPLACE VIEW green_divergence_district_metrics AS
WITH latest AS (
  SELECT DISTINCT ON (dm.district_region_id, dm.metric_key)
    dm.*, r.region_group
  FROM green_divergence_district_inputs() dm JOIN regions r ON r.id = dm.district_region_id
  WHERE dm.metric_key IN ('tree_canopy_pct', 'gvi_ndvi_street')
    AND dm.value > '-Infinity'::double precision
    AND dm.value < 'Infinity'::double precision
  ORDER BY dm.district_region_id, dm.metric_key, dm.vintage DESC, dm.computed_at DESC
), paired AS (
  SELECT c.district_region_id, c.region_group,
    c.value AS canopy_value, g.value AS gvi_value,
    c.vintage AS canopy_vintage, g.vintage AS gvi_vintage,
    GREATEST(c.computed_at, g.computed_at) AS computed_at
  FROM latest c JOIN latest g USING (district_region_id)
  WHERE c.metric_key = 'tree_canopy_pct' AND g.metric_key = 'gvi_ndvi_street'
), ranked AS (
  SELECT *,
    percent_rank() OVER (PARTITION BY region_group ORDER BY canopy_value) AS canopy_percentile,
    percent_rank() OVER (PARTITION BY region_group ORDER BY gvi_value) AS gvi_percentile
  FROM paired
)
SELECT district_region_id, 'green_divergence'::text AS metric_key,
  100.0 * (canopy_percentile - gvi_percentile) AS value,
  'canopy:' || canopy_vintage || '|gvi:' || gvi_vintage AS vintage,
  computed_at, canopy_value, gvi_value, canopy_vintage, gvi_vintage,
  canopy_percentile, gvi_percentile
FROM ranked;

CREATE OR REPLACE VIEW green_divergence_listing_metrics AS
WITH latest AS (
  SELECT DISTINCT ON (lm.listing_id, lm.grain, lm.metric_key)
    lm.*, l.region_slug
  FROM listing_metrics lm JOIN listings l ON l.id = lm.listing_id
  WHERE lm.metric_key IN ('tree_canopy_pct', 'gvi_ndvi_street')
    AND lm.value > '-Infinity'::double precision
    AND lm.value < 'Infinity'::double precision
  ORDER BY lm.listing_id, lm.grain, lm.metric_key, lm.vintage DESC, lm.computed_at DESC
), paired AS (
  SELECT c.listing_id, c.grain, c.region_slug,
    c.value AS canopy_value, g.value AS gvi_value,
    c.vintage AS canopy_vintage, g.vintage AS gvi_vintage,
    GREATEST(c.computed_at, g.computed_at) AS computed_at
  FROM latest c JOIN latest g USING (listing_id, grain)
  WHERE c.metric_key = 'tree_canopy_pct' AND g.metric_key = 'gvi_ndvi_street'
), ranked AS (
  SELECT *,
    percent_rank() OVER (PARTITION BY region_slug, grain ORDER BY canopy_value) AS canopy_percentile,
    percent_rank() OVER (PARTITION BY region_slug, grain ORDER BY gvi_value) AS gvi_percentile
  FROM paired
)
SELECT listing_id, grain, 'green_divergence'::text AS metric_key,
  100.0 * (canopy_percentile - gvi_percentile) AS value,
  'canopy:' || canopy_vintage || '|gvi:' || gvi_vintage AS vintage,
  computed_at, canopy_value, gvi_value, canopy_vintage, gvi_vintage,
  canopy_percentile, gvi_percentile
FROM ranked;
