CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS school_districts (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nces_geoid text UNIQUE NOT NULL,
  name_raw text NOT NULL,
  name_display text NOT NULL,
  state text NOT NULL,
  school_year text NOT NULL,
  geom geometry(MultiPolygon, 4326) NOT NULL CHECK (ST_IsValid(geom))
);
CREATE INDEX IF NOT EXISTS school_districts_geom_idx ON school_districts USING gist (geom);
CREATE INDEX IF NOT EXISTS school_districts_state_idx ON school_districts (state);

CREATE TABLE IF NOT EXISTS listings (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_id text,
  source text NOT NULL DEFAULT 'rentcast',
  region_slug text NOT NULL,
  address text,
  city text,
  state text,
  zip text,
  county text,
  price integer,
  beds integer,
  baths double precision,
  property_type text,
  square_footage integer,
  year_built integer,
  url text,
  listed_date date,
  days_on_market integer,
  status text,
  district_id bigint REFERENCES school_districts(id),
  assignment_method text NOT NULL CHECK (assignment_method IN ('within','nearest')),
  assignment_dist_m double precision,
  geom geometry(Point, 4326) NOT NULL,
  UNIQUE (source, source_id)
);
CREATE INDEX IF NOT EXISTS listings_geom_idx ON listings USING gist (geom);
CREATE INDEX IF NOT EXISTS listings_district_id_idx ON listings (district_id);

CREATE TABLE IF NOT EXISTS district_quality (
  district_id bigint PRIMARY KEY REFERENCES school_districts(id),
  good_district boolean NOT NULL,
  source text NOT NULL DEFAULT 'curated_placeholder',
  notes text
);

DO $$
BEGIN
  CREATE TYPE region_type AS ENUM ('school_district','municipality','census_tract','county','zcta');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS regions (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  region_type region_type NOT NULL,
  slug text UNIQUE NOT NULL,
  name text NOT NULL,
  state text NOT NULL,
  source_id text,
  district_id bigint REFERENCES school_districts(id),
  geom geometry(MultiPolygon, 4326) NOT NULL CHECK (ST_IsValid(geom)),
  region_group text
);
CREATE INDEX IF NOT EXISTS regions_geom_idx ON regions USING gist (geom);
CREATE INDEX IF NOT EXISTS regions_type_state_idx ON regions (region_type, state);

CREATE TABLE IF NOT EXISTS region_overlaps (
  child_region_id bigint REFERENCES regions(id),
  parent_region_id bigint REFERENCES regions(id),
  area_weight double precision NOT NULL,
  PRIMARY KEY (child_region_id, parent_region_id)
);

CREATE TABLE IF NOT EXISTS metric_definitions (
  metric_key text PRIMARY KEY,
  name text NOT NULL,
  units text,
  direction text CHECK (direction IN ('higher_better','lower_better','neutral')),
  source text NOT NULL,
  grain region_type NOT NULL,
  native_resolution text,
  notes text
);

CREATE TABLE IF NOT EXISTS region_metrics (
  region_id bigint REFERENCES regions(id),
  metric_key text REFERENCES metric_definitions(metric_key),
  value double precision NOT NULL,
  vintage text NOT NULL,
  computed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (region_id, metric_key, vintage)
);

CREATE TABLE IF NOT EXISTS listing_metrics (
  listing_id bigint REFERENCES listings(id),
  metric_key text REFERENCES metric_definitions(metric_key),
  grain text NOT NULL CHECK (grain IN ('point','buffer_100m','buffer_500m')),
  value double precision NOT NULL,
  vintage text NOT NULL,
  computed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (listing_id, metric_key, grain, vintage)
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
CREATE VIEW district_metrics AS
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
GROUP BY parent.id, rm.metric_key, rm.vintage;

CREATE OR REPLACE FUNCTION normalize_name_for_compare(value text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT regexp_replace(lower(coalesce(value, '')), '[^a-z0-9]+', '', 'g')
$$;
