DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_matviews
    WHERE schemaname = 'public'
      AND matviewname = 'district_metrics'
  ) THEN
    EXECUTE 'DROP MATERIALIZED VIEW district_metrics';
  END IF;
END $$;

DROP VIEW IF EXISTS district_metrics;
CREATE MATERIALIZED VIEW district_metrics AS
WITH tract_rollups AS (
  SELECT
    parent.id AS district_region_id,
    rm.metric_key,
    SUM(rm.value * ro.area_weight * ST_Area(child.geom::geography))
      / NULLIF(SUM(ro.area_weight * ST_Area(child.geom::geography)), 0) AS value,
    rm.vintage,
    MAX(rm.computed_at) AS computed_at
  FROM region_metrics rm
  JOIN regions child ON child.id = rm.region_id
  JOIN region_overlaps ro ON ro.child_region_id = child.id
  JOIN regions parent ON parent.id = ro.parent_region_id
  WHERE child.region_type = 'census_tract'
    AND parent.region_type = 'school_district'
    AND NOT EXISTS (
      SELECT 1
      FROM region_metrics direct_rm
      JOIN regions direct_region ON direct_region.id = direct_rm.region_id
      WHERE direct_region.id = parent.id
        AND direct_rm.metric_key = rm.metric_key
        AND direct_rm.vintage = rm.vintage
    )
  GROUP BY parent.id, rm.metric_key, rm.vintage
),
direct_district_metrics AS (
  SELECT
    r.id AS district_region_id,
    rm.metric_key,
    rm.value,
    rm.vintage,
    rm.computed_at
  FROM region_metrics rm
  JOIN regions r ON r.id = rm.region_id
  WHERE r.region_type = 'school_district'
)
SELECT * FROM tract_rollups
UNION ALL
SELECT * FROM direct_district_metrics
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS district_metrics_unique_idx
  ON district_metrics (district_region_id, metric_key, vintage);
