"""PostgreSQL connection management and ordered schema migrations.

Schema changes live in ``lucent/migrations/*.sql``. Each migration is applied once,
inside a transaction, and recorded in ``schema_migrations``. Startup does not
silently create or alter tables outside that ledger.
"""

from __future__ import annotations

import re
import ssl
from pathlib import Path
from typing import Any

import asyncpg

from utils.config import PG_URL

_MIGRATION_FILE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


async def create_db_pool() -> asyncpg.Pool:
    """Create the application connection pool with TLS verification enabled."""

    return await asyncpg.create_pool(
        PG_URL,
        ssl=ssl.create_default_context(),
        min_size=1,
        max_size=10,
        command_timeout=30,
        server_settings={"application_name": "lucent"},
    )


def _migration_files() -> list[tuple[int, str, Path]]:
    if not _MIGRATIONS_DIR.is_dir():
        return []

    migrations: list[tuple[int, str, Path]] = []
    for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        match = _MIGRATION_FILE.match(path.name)
        if match is None:
            raise RuntimeError(f"Invalid migration filename: {path.name}")
        migrations.append((int(match.group(1)), match.group(2), path))

    versions = [version for version, _, _ in migrations]
    if len(versions) != len(set(versions)):
        raise RuntimeError("Duplicate migration versions found")
    return migrations


async def applied_versions(pool: Any) -> set[int]:
    """Return the set of migration versions already applied."""

    rows = await pool.fetch("SELECT version FROM schema_migrations")
    return {int(row["version"]) for row in rows}


async def run_migrations(pool: Any) -> list[int]:
    """Apply pending migrations in order and return the versions applied."""

    await pool.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )

    applied = await applied_versions(pool)
    newly_applied: list[int] = []

    for version, name, path in _migration_files():
        if version in applied:
            continue

        sql = path.read_text(encoding="utf-8")
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(sql)
                await connection.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES ($1, $2) "
                    "ON CONFLICT (version) DO NOTHING",
                    version,
                    name,
                )
        newly_applied.append(version)

    return newly_applied


async def bootstrap_database(pool: Any) -> None:
    await run_migrations(pool)
