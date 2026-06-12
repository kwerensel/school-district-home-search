from __future__ import annotations

import os
from pathlib import Path

import psycopg


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("Set DATABASE_URL before running database commands")
    return url


def migration_paths() -> list[Path]:
    migrations_dir = repo_root() / "sql" / "migrations"
    return sorted(migrations_dir.glob("*.sql"))


def run_migrations() -> list[str]:
    applied: list[str] = []
    with psycopg.connect(database_url(), autocommit=True) as conn:
        with conn.cursor() as cur:
            for path in migration_paths():
                cur.execute(path.read_text())
                applied.append(path.name)
    return applied

