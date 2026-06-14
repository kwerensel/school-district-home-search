CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS staging.region_scaffold_school_districts (
  nces_geoid text PRIMARY KEY,
  name_raw text NOT NULL,
  name_display text NOT NULL,
  state text NOT NULL,
  school_year text NOT NULL,
  geom geometry(MultiPolygon, 4326) NOT NULL CHECK (ST_IsValid(geom)),
  region_group text NOT NULL
);
CREATE INDEX IF NOT EXISTS staging_region_scaffold_school_districts_geom_idx
  ON staging.region_scaffold_school_districts USING gist (geom);

CREATE TABLE IF NOT EXISTS staging.region_scaffold_regions (
  region_type region_type NOT NULL,
  slug text PRIMARY KEY,
  name text NOT NULL,
  state text NOT NULL,
  source_id text,
  district_source_id text,
  geom geometry(MultiPolygon, 4326) NOT NULL CHECK (ST_IsValid(geom)),
  region_group text NOT NULL
);
CREATE INDEX IF NOT EXISTS staging_region_scaffold_regions_geom_idx
  ON staging.region_scaffold_regions USING gist (geom);
CREATE INDEX IF NOT EXISTS staging_region_scaffold_regions_group_idx
  ON staging.region_scaffold_regions (region_group, region_type);

CREATE TABLE IF NOT EXISTS staging.region_scaffold_overlaps (
  child_slug text NOT NULL REFERENCES staging.region_scaffold_regions(slug) ON DELETE CASCADE,
  parent_slug text NOT NULL REFERENCES staging.region_scaffold_regions(slug) ON DELETE CASCADE,
  area_weight double precision NOT NULL,
  region_group text NOT NULL,
  PRIMARY KEY (child_slug, parent_slug)
);

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
GROUP BY parent.id, rm.metric_key, rm.vintage
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS district_metrics_unique_idx
  ON district_metrics (district_region_id, metric_key, vintage);
