CREATE TABLE IF NOT EXISTS tradeoff_narratives (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  region_a_id bigint NOT NULL REFERENCES regions(id) ON DELETE CASCADE,
  region_b_id bigint NOT NULL REFERENCES regions(id) ON DELETE CASCADE,
  profile_bucket text NOT NULL,
  payload_hash text NOT NULL,
  narrative text NOT NULL,
  source text NOT NULL CHECK (source IN ('claude', 'template')),
  model text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (region_a_id, region_b_id, profile_bucket, payload_hash)
);

CREATE INDEX IF NOT EXISTS tradeoff_narratives_lookup_idx
  ON tradeoff_narratives (region_a_id, region_b_id, profile_bucket, created_at DESC);

