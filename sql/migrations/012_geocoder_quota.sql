-- Global per-day ceiling shared across isolates. Stores no addresses/profiles.
CREATE TABLE IF NOT EXISTS geocoder_daily_usage (
  provider text NOT NULL CHECK (provider = 'geocodio'),
  usage_day date NOT NULL,
  requests integer NOT NULL CHECK (requests BETWEEN 0 AND 1000),
  PRIMARY KEY (provider,usage_day)
);
