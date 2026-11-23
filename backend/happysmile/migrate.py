"""Apply SQL migrations in order. Each file runs once, inside a transaction.

Usage:  python -m happysmile.migrate
"""

from __future__ import annotations

from pathlib import Path

import psycopg

from .config import get_settings

MIGRATIONS = Path(__file__).parent / "migrations"


def migrate(url: str | None = None) -> list[str]:
    applied_now: list[str] = []
    with psycopg.connect(url or get_settings().database_url, autocommit=False) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
        conn.execute("SELECT pg_advisory_xact_lock(7001)")  # one migrator at a time
        done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.stem in done:
                continue
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,))
            applied_now.append(path.stem)
        conn.commit()
    return applied_now


if __name__ == "__main__":
    done = migrate()
    print("Applied: " + (", ".join(done) if done else "nothing (up to date)"))
