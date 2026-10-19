"""Run the actual view SQL over isolated synthetic inputs, never live metrics."""
import os
from pathlib import Path

import psycopg
import pytest


@pytest.mark.skipif(not os.environ.get('DATABASE_URL'), reason='DATABASE_URL required for SQL behavior test')
def test_divergence_views_pair_latest_matching_grains_and_rank_locally():
    sql = (Path(__file__).parents[2] / 'sql/migrations/010_green_divergence.sql').read_text()
    with psycopg.connect(os.environ['DATABASE_URL']) as conn:
        with conn.cursor() as cur:
            cur.execute('''
                CREATE TEMP TABLE regions (id int, region_group text, region_type text);
                CREATE TEMP TABLE listings (id int, region_slug text);
                CREATE TEMP TABLE region_metrics (
                    region_id int, metric_key text, value double precision,
                    vintage text, computed_at timestamptz DEFAULT now());
                CREATE TEMP TABLE district_metrics (
                    district_region_id int, metric_key text, value double precision,
                    vintage text, computed_at timestamptz DEFAULT now());
                CREATE TEMP TABLE listing_metrics (
                    listing_id int, grain text, metric_key text, value double precision,
                    vintage text, computed_at timestamptz DEFAULT now());
                INSERT INTO regions VALUES (1,'a','census_tract'),(2,'a','census_tract'),
                  (3,'b','census_tract'),(4,'a','census_tract'),(5,'a','census_tract');
                INSERT INTO listings VALUES (1,'a'),(2,'a'),(3,'b');
                INSERT INTO region_metrics (region_id,metric_key,value,vintage) VALUES
                  (1,'tree_canopy_pct',20,'2023'),(1,'tree_canopy_pct',90,'2021'),
                  (1,'gvi_ndvi_street',0.8,'2025-summer'),
                  (2,'tree_canopy_pct',80,'2023'),(2,'gvi_ndvi_street',0.2,'2025-summer'),
                  (3,'tree_canopy_pct',50,'2023'),(3,'gvi_ndvi_street',0.1,'2025-summer'),
                  (4,'tree_canopy_pct',100,'2023'),
                  (5,'tree_canopy_pct','NaN','2023'),(5,'gvi_ndvi_street',0.5,'2025-summer');
                INSERT INTO district_metrics (district_region_id,metric_key,value,vintage)
                  SELECT region_id,metric_key,value,vintage FROM region_metrics;
                INSERT INTO listing_metrics (listing_id,grain,metric_key,value,vintage)
                  SELECT region_id,'buffer_100m',metric_key,value,vintage FROM region_metrics WHERE region_id <= 3;
                INSERT INTO listing_metrics (listing_id,grain,metric_key,value,vintage) VALUES
                  (1,'buffer_500m','tree_canopy_pct',50,'2023'),
                  (1,'buffer_500m','gvi_ndvi_street',0.3,'2025-summer'),
                  (2,'buffer_500m','tree_canopy_pct',50,'2023'),
                  (2,'buffer_500m','gvi_ndvi_street',0.3,'2025-summer');
            ''')
            cur.execute(sql.replace('CREATE OR REPLACE VIEW', 'CREATE TEMP VIEW')
                        .replace('green_divergence_district_inputs(', 'pg_temp.green_divergence_district_inputs(')
                        .replace('FROM public.district_metrics', 'FROM pg_temp.district_metrics'))
            for view, key in [('green_divergence_region_metrics','region_id'),
                              ('green_divergence_district_metrics','district_region_id')]:
                cur.execute(f'SELECT {key},value FROM {view} ORDER BY {key}')
                assert cur.fetchall() == [(1,-100.0),(2,100.0),(3,0.0)]
            cur.execute('SELECT listing_id,grain,value FROM green_divergence_listing_metrics ORDER BY grain,listing_id')
            assert cur.fetchall() == [(1,'buffer_100m',-100.0),(2,'buffer_100m',100.0),
                                      (3,'buffer_100m',0.0),(1,'buffer_500m',0.0),(2,'buffer_500m',0.0)]
            cur.execute('SELECT vintage FROM green_divergence_region_metrics WHERE region_id=1')
            assert cur.fetchone()[0] == 'canopy:2023|gvi:2025-summer'
        conn.rollback()
