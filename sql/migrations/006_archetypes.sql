CREATE TABLE IF NOT EXISTS archetype_models (
  model_version text PRIMARY KEY,
  metric_keys jsonb NOT NULL,
  district_count integer NOT NULL CHECK (district_count > 0),
  cluster_count integer NOT NULL CHECK (cluster_count BETWEEN 4 AND 9),
  silhouette double precision NOT NULL,
  status text NOT NULL CHECK (status IN ('ready', 'retired')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS archetypes (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  model_version text NOT NULL REFERENCES archetype_models(model_version) ON DELETE CASCADE,
  cluster_index integer NOT NULL,
  centroid jsonb NOT NULL,
  distinguishing_metrics jsonb NOT NULL,
  silhouette double precision NOT NULL,
  label text,
  one_line_description text,
  label_status text NOT NULL DEFAULT 'unlabeled'
    CHECK (label_status IN ('unlabeled', 'pending', 'approved')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (model_version, cluster_index)
);

CREATE TABLE IF NOT EXISTS region_archetypes (
  region_id bigint NOT NULL REFERENCES regions(id) ON DELETE CASCADE,
  archetype_id bigint NOT NULL REFERENCES archetypes(id) ON DELETE CASCADE,
  model_version text NOT NULL REFERENCES archetype_models(model_version) ON DELETE CASCADE,
  distance double precision NOT NULL CHECK (distance >= 0),
  PRIMARY KEY (region_id, model_version)
);

CREATE INDEX IF NOT EXISTS region_archetypes_archetype_idx
  ON region_archetypes (archetype_id);

