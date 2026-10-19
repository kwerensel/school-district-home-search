"""Verify the app's global no-overage quota against real PostgreSQL semantics."""
import os
from pathlib import Path
import psycopg
import pytest

@pytest.mark.skipif(not os.environ.get('DATABASE_URL'),reason='DATABASE_URL required')
def test_geocoder_reservation_refuses_over_cap_and_migration_replays():
    migration=(Path(__file__).parents[2]/'sql/migrations/012_geocoder_quota.sql').read_text()
    with psycopg.connect(os.environ['DATABASE_URL']) as conn:
        cur=conn.cursor()
        cur.execute(migration.replace('CREATE TABLE IF NOT EXISTS','CREATE TEMP TABLE IF NOT EXISTS'))
        cur.execute(migration.replace('CREATE TABLE IF NOT EXISTS','CREATE TEMP TABLE IF NOT EXISTS'))
        cur.execute("INSERT INTO geocoder_daily_usage VALUES ('geocodio','2026-10-18',999)")
        query="""INSERT INTO geocoder_daily_usage (provider,usage_day,requests)
          VALUES ('geocodio','2026-10-18',1)
          ON CONFLICT (provider,usage_day) DO UPDATE SET requests=geocoder_daily_usage.requests+1
          WHERE geocoder_daily_usage.requests<1000 RETURNING requests"""
        cur.execute(query)
        assert cur.fetchone()==(1000,)
        cur.execute(query)
        assert cur.fetchone() is None
        assert conn.execute('SELECT requests FROM geocoder_daily_usage').fetchone()==(1000,)
        conn.rollback()
