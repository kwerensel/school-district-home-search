-- Private operator foundation. Intentionally unapplied during scaffolding.
-- No provider calls, baseline initialization, pointer changes or outreach occur.
CREATE TABLE IF NOT EXISTS operator_roles (
  user_id text PRIMARY KEY REFERENCES "user" (id) ON DELETE CASCADE,
  role text NOT NULL CHECK (role = 'admin'),
  granted_by text NOT NULL,
  granted_at timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON operator_roles FROM PUBLIC;

CREATE TABLE IF NOT EXISTS operator_jobs (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  kind text NOT NULL CHECK (kind IN ('listing_refresh','region_expansion','attendance_ingest')),
  target text NOT NULL,
  phase text NOT NULL DEFAULT 'draft' CHECK
    (phase IN ('draft','scaffolding','coverage','blocked','validated','promoted','failed')),
  requested_by text NOT NULL REFERENCES "user" (id),
  input_manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
  coverage_report jsonb,
  validation_report_hash text,
  qa_artifacts jsonb NOT NULL DEFAULT '[]'::jsonb,
  golden_passed boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (validation_report_hash IS NULL OR validation_report_hash ~ '^[a-f0-9]{64}$'),
  CHECK (jsonb_typeof(qa_artifacts) = 'array'),
  CHECK (phase NOT IN ('validated','promoted') OR
    (validation_report_hash IS NOT NULL AND golden_passed AND jsonb_array_length(qa_artifacts) > 0))
);
CREATE INDEX IF NOT EXISTS operator_jobs_phase_idx ON operator_jobs (phase, created_at);

CREATE TABLE IF NOT EXISTS listing_dataset_versions (
  version text PRIMARY KEY,
  dataset_kind text NOT NULL CHECK (dataset_kind IN ('frozen_baseline','refresh')),
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','staged','validated','published')),
  provider text NOT NULL,
  provider_vintage text NOT NULL,
  provider_approval jsonb,
  source_content_hash text CHECK (source_content_hash ~ '^[a-f0-9]{64}$'),
  expected_record_count integer NOT NULL CHECK (expected_record_count > 0),
  validation_report_hash text CHECK (validation_report_hash ~ '^[a-f0-9]{64}$'),
  validation_report jsonb,
  qa_artifacts jsonb NOT NULL DEFAULT '[]'::jsonb,
  golden_passed boolean NOT NULL DEFAULT false,
  published_by text REFERENCES "user" (id),
  published_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (dataset_kind <> 'frozen_baseline' OR expected_record_count = 4505),
  CHECK (jsonb_typeof(qa_artifacts) = 'array'),
  CHECK (status NOT IN ('validated','published') OR
    (validation_report_hash IS NOT NULL AND validation_report IS NOT NULL
     AND validation_report @> '{"promotable":true}'::jsonb
     AND golden_passed AND jsonb_array_length(qa_artifacts) > 0)),
  CHECK (dataset_kind <> 'refresh' OR status <> 'published' OR
    (provider_approval IS NOT NULL AND published_by IS NOT NULL AND published_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS one_frozen_baseline_idx ON listing_dataset_versions (dataset_kind)
  WHERE dataset_kind = 'frozen_baseline';

-- Deliberately populated only by an explicit baseline-registration step after
-- count/golden validation. Original listings remain the active app dataset.
CREATE TABLE IF NOT EXISTS operator_frozen_listing_members (
  listing_id bigint PRIMARY KEY REFERENCES listings(id),
  baseline_version text NOT NULL REFERENCES listing_dataset_versions(version),
  source_snapshot jsonb NOT NULL,
  registered_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.operator_listing_records (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  dataset_version text NOT NULL REFERENCES listing_dataset_versions(version),
  provider text NOT NULL,
  source_id text NOT NULL,
  region_slug text NOT NULL,
  record jsonb NOT NULL CHECK (jsonb_typeof(record) = 'object'),
  geom geometry(Point,4326) NOT NULL CHECK (ST_IsValid(geom) AND NOT ST_IsEmpty(geom)),
  district_id bigint REFERENCES school_districts(id),
  district_match_count integer NOT NULL DEFAULT 0 CHECK (district_match_count >= 0),
  assignment_method text NOT NULL DEFAULT 'unresolved' CHECK
    (assignment_method IN ('unresolved','point_in_polygon')),
  UNIQUE(dataset_version,provider,source_id),
  CHECK (assignment_method <> 'point_in_polygon' OR
    (district_id IS NOT NULL AND district_match_count = 1))
);
CREATE INDEX IF NOT EXISTS operator_listing_records_geom_idx
  ON staging.operator_listing_records USING gist(geom);

-- A future explicit publish adapter can atomically select a version here.
-- Creating this table does not change any public listing reader.
CREATE TABLE IF NOT EXISTS operator_active_listing_dataset (
  singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
  dataset_version text NOT NULL REFERENCES listing_dataset_versions(version),
  selected_at timestamptz NOT NULL DEFAULT now(),
  selected_by text NOT NULL REFERENCES "user"(id)
);

CREATE OR REPLACE FUNCTION operator_protect_baseline_members() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Frozen baseline membership and snapshots are immutable';
END;
$$;
DROP TRIGGER IF EXISTS operator_baseline_members_immutable ON operator_frozen_listing_members;
CREATE TRIGGER operator_baseline_members_immutable BEFORE UPDATE OR DELETE
  ON operator_frozen_listing_members FOR EACH ROW EXECUTE FUNCTION operator_protect_baseline_members();

CREATE OR REPLACE FUNCTION operator_protect_frozen_listings() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM operator_frozen_listing_members WHERE listing_id = OLD.id) THEN
    RAISE EXCEPTION 'Frozen baseline listings cannot be overwritten or deleted';
  END IF;
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;
DROP TRIGGER IF EXISTS operator_frozen_listing_immutable ON listings;
CREATE TRIGGER operator_frozen_listing_immutable BEFORE UPDATE OR DELETE
  ON listings FOR EACH ROW EXECUTE FUNCTION operator_protect_frozen_listings();

CREATE OR REPLACE FUNCTION operator_protect_dataset_records() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE version_status text;
BEGIN
  SELECT status INTO version_status FROM listing_dataset_versions
    WHERE version = CASE WHEN TG_OP = 'DELETE' THEN OLD.dataset_version ELSE NEW.dataset_version END;
  IF version_status IN ('validated','published') THEN
    RAISE EXCEPTION 'Validated/published version records are immutable; create a new version';
  END IF;
  IF TG_OP = 'UPDATE' AND OLD.dataset_version <> NEW.dataset_version THEN
    RAISE EXCEPTION 'Moving records between dataset versions is prohibited';
  END IF;
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;
DROP TRIGGER IF EXISTS operator_dataset_records_immutable ON staging.operator_listing_records;
CREATE TRIGGER operator_dataset_records_immutable BEFORE INSERT OR UPDATE OR DELETE
  ON staging.operator_listing_records FOR EACH ROW EXECUTE FUNCTION operator_protect_dataset_records();

CREATE TABLE IF NOT EXISTS attendance_evidence (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  district_id bigint NOT NULL REFERENCES school_districts(id),
  kind text NOT NULL CHECK (kind IN ('official_gis','official_locator','written_confirmation')),
  source_url text NOT NULL CHECK (source_url ~ '^https://'),
  retrieved_at timestamptz NOT NULL,
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
  school_year text NOT NULL CHECK (school_year ~ '^20[0-9]{2}-20[0-9]{2}$'),
  grade_min integer NOT NULL CHECK (grade_min BETWEEN 0 AND 12),
  grade_max integer NOT NULL CHECK (grade_max BETWEEN 0 AND 12 AND grade_max >= grade_min),
  written_confirmation_reference text,
  reviewed_by text REFERENCES "user"(id),
  reviewed_at timestamptz,
  notes text,
  CHECK (substring(school_year from 6 for 4)::integer = substring(school_year from 1 for 4)::integer + 1),
  CHECK (kind <> 'written_confirmation' OR written_confirmation_reference IS NOT NULL),
  CHECK ((reviewed_by IS NULL) = (reviewed_at IS NULL))
);

CREATE TABLE IF NOT EXISTS attendance_zones (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  district_id bigint NOT NULL REFERENCES school_districts(id),
  school_nces_id text NOT NULL,
  school_year text NOT NULL,
  grade_min integer NOT NULL CHECK (grade_min BETWEEN 0 AND 12),
  grade_max integer NOT NULL CHECK (grade_max BETWEEN 0 AND 12 AND grade_max >= grade_min),
  evidence_id bigint NOT NULL REFERENCES attendance_evidence(id),
  status text NOT NULL DEFAULT 'provisional' CHECK
    (status IN ('official','written-confirmed','provisional','unresolved')),
  geom geometry(MultiPolygon,4326) NOT NULL CHECK (ST_IsValid(geom) AND NOT ST_IsEmpty(geom)),
  source_zone_id text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(district_id,school_year,grade_min,grade_max,source_zone_id)
);
CREATE INDEX IF NOT EXISTS attendance_zones_geom_idx ON attendance_zones USING gist(geom);
CREATE INDEX IF NOT EXISTS attendance_zones_scope_idx ON attendance_zones (district_id,school_year,grade_min,grade_max);

CREATE OR REPLACE FUNCTION operator_validate_attendance_evidence() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE evidence attendance_evidence%ROWTYPE;
BEGIN
  SELECT * INTO STRICT evidence FROM attendance_evidence WHERE id = NEW.evidence_id;
  IF evidence.district_id <> NEW.district_id OR evidence.school_year <> NEW.school_year
     OR evidence.grade_min <> NEW.grade_min OR evidence.grade_max <> NEW.grade_max THEN
    RAISE EXCEPTION 'Zone district/year/grade scope must match its evidence';
  END IF;
  IF NEW.status IN ('official','written-confirmed') AND evidence.reviewed_by IS NULL THEN
    RAISE EXCEPTION 'Publishing a zone requires reviewed evidence';
  END IF;
  IF NEW.status = 'official' AND evidence.kind <> 'official_gis' THEN
    RAISE EXCEPTION 'Official polygons require official GIS evidence';
  END IF;
  IF NEW.status = 'written-confirmed' AND evidence.written_confirmation_reference IS NULL THEN
    RAISE EXCEPTION 'Written confirmation must be retained';
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS operator_zone_evidence_guard ON attendance_zones;
CREATE TRIGGER operator_zone_evidence_guard BEFORE INSERT OR UPDATE ON attendance_zones
  FOR EACH ROW EXECUTE FUNCTION operator_validate_attendance_evidence();

-- Locator replies remain address-specific evidence. A single written address
-- confirmation never creates or expands a zone polygon.
CREATE TABLE IF NOT EXISTS attendance_locator_results (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  listing_id bigint NOT NULL REFERENCES listings(id),
  evidence_id bigint NOT NULL REFERENCES attendance_evidence(id),
  school_nces_id text,
  result_status text NOT NULL CHECK
    (result_status IN ('official','written-confirmed','provisional','unresolved')),
  retrieved_at timestamptz NOT NULL,
  source_response_hash text NOT NULL CHECK (source_response_hash ~ '^[a-f0-9]{64}$')
);

CREATE TABLE IF NOT EXISTS district_outreach_queue (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  district_id bigint NOT NULL REFERENCES school_districts(id),
  school_year text NOT NULL,
  grade_band text NOT NULL,
  missing_evidence text NOT NULL,
  official_contact_url text,
  sender_identity text,
  draft_subject text,
  draft_body text,
  status text NOT NULL DEFAULT 'draft' CHECK
    (status IN ('draft','needs_review','awaiting_written_evidence','resolved')),
  written_evidence_id bigint REFERENCES attendance_evidence(id),
  created_by text NOT NULL REFERENCES "user"(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status <> 'resolved' OR written_evidence_id IS NOT NULL)
);

REVOKE ALL ON operator_jobs, listing_dataset_versions, operator_frozen_listing_members,
  staging.operator_listing_records, operator_active_listing_dataset,
  attendance_evidence, attendance_zones, attendance_locator_results,
  district_outreach_queue FROM PUBLIC;

CREATE OR REPLACE FUNCTION operator_protect_dataset_versions() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.dataset_kind = 'frozen_baseline' OR OLD.status = 'published' THEN
    RAISE EXCEPTION 'Frozen/published dataset versions are immutable; create a new version';
  END IF;
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;
DROP TRIGGER IF EXISTS operator_dataset_versions_immutable ON listing_dataset_versions;
CREATE TRIGGER operator_dataset_versions_immutable BEFORE UPDATE OR DELETE
  ON listing_dataset_versions FOR EACH ROW EXECUTE FUNCTION operator_protect_dataset_versions();

ALTER TABLE operator_jobs ADD COLUMN IF NOT EXISTS lease_owner text;
ALTER TABLE operator_jobs ADD COLUMN IF NOT EXISTS lease_expires_at timestamptz;
ALTER TABLE operator_jobs ADD COLUMN IF NOT EXISTS attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0);

ALTER TABLE listing_dataset_versions ADD COLUMN IF NOT EXISTS provider_estimate jsonb;
