-- Permit genuinely new region metrics to stage before any public geometry
-- promotion. Live metric/listing FKs remain untouched. Staged-only targets need
-- an active scoped administrator worker lease set on their trusted connection.
ALTER TABLE staging.layer_region_metrics
  DROP CONSTRAINT IF EXISTS layer_region_metrics_region_slug_fkey;

CREATE OR REPLACE FUNCTION staging.validate_layer_region_metric_scope()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  context_region text := current_setting('groundtruth.staged_region', true);
  context_job text := current_setting('groundtruth.staged_region_job_id', true);
  context_worker text := current_setting('groundtruth.staged_region_worker_id', true);
  context_actor text := current_setting('groundtruth.staged_region_actor', true);
BEGIN
  -- Ordinary existing public regions retain their previous staging behavior,
  -- with an additional exact region-group match rather than slug-only proof.
  IF EXISTS (SELECT 1 FROM public.regions r
             WHERE r.slug = NEW.region_slug AND r.region_group = NEW.region_group) THEN
    IF context_region IS NOT NULL AND context_region <> '' THEN
      RAISE EXCEPTION 'A scoped expansion worker cannot stage existing public-region targets';
    END IF;
    RETURN NEW;
  END IF;
  IF EXISTS (SELECT 1 FROM public.regions r WHERE r.slug = NEW.region_slug) THEN
    RAISE EXCEPTION 'Staged metric target conflicts with another public region group';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM staging.region_scaffold_regions r
                 WHERE r.slug = NEW.region_slug AND r.region_group = NEW.region_group) THEN
    RAISE EXCEPTION 'Staged metric requires matching public or staged region geometry';
  END IF;
  IF context_region IS DISTINCT FROM NEW.region_group
     OR context_job IS NULL OR context_job !~ '^[1-9][0-9]*$'
     OR context_worker IS NULL OR context_worker = ''
     OR context_actor IS NULL OR context_actor = '' THEN
    RAISE EXCEPTION 'Staged-only metric requires trusted worker connection context';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM public.operator_jobs j
    JOIN public.operator_roles r ON r.user_id = context_actor AND r.role = 'admin'
    WHERE j.id = context_job::bigint AND j.kind = 'region_expansion'
      AND j.target = NEW.region_group AND j.phase IN ('coverage','validated')
      AND j.lease_owner = context_worker AND j.lease_expires_at > clock_timestamp()
  ) THEN
    RAISE EXCEPTION 'Staged-only metric worker lease expired or administrator access was revoked';
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS layer_region_metrics_scope_guard ON staging.layer_region_metrics;
CREATE CONSTRAINT TRIGGER layer_region_metrics_scope_guard
  AFTER INSERT OR UPDATE ON staging.layer_region_metrics
  DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW
  EXECUTE FUNCTION staging.validate_layer_region_metric_scope();

-- Preserve the former staging FK's ON DELETE CASCADE behavior for published
-- regions. This does not permit deletion from public metric/listing tables.
CREATE OR REPLACE FUNCTION staging.cascade_deleted_public_region_metrics()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  DELETE FROM staging.layer_region_metrics
  WHERE region_slug = OLD.slug AND region_group = OLD.region_group;
  RETURN OLD;
END;
$$;
DROP TRIGGER IF EXISTS layer_region_metrics_public_delete_cascade ON public.regions;
CREATE TRIGGER layer_region_metrics_public_delete_cascade AFTER DELETE
  ON public.regions FOR EACH ROW
  EXECUTE FUNCTION staging.cascade_deleted_public_region_metrics();

-- Re-scaffolding a not-yet-public region must not strand metrics whose staged
-- source geometry was removed. Public-backed staging rows remain valid.
CREATE OR REPLACE FUNCTION staging.cascade_deleted_staged_region_metrics()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM public.regions r
                 WHERE r.slug = OLD.slug AND r.region_group = OLD.region_group) THEN
    DELETE FROM staging.layer_region_metrics
    WHERE region_slug = OLD.slug AND region_group = OLD.region_group;
  END IF;
  RETURN OLD;
END;
$$;
DROP TRIGGER IF EXISTS layer_region_metrics_staged_delete_cascade ON staging.region_scaffold_regions;
CREATE TRIGGER layer_region_metrics_staged_delete_cascade AFTER DELETE
  ON staging.region_scaffold_regions FOR EACH ROW
  EXECUTE FUNCTION staging.cascade_deleted_staged_region_metrics();
