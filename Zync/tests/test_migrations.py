from __future__ import annotations

from pathlib import Path

from core.database import _migration_files

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def test_migration_versions_are_unique_and_ordered() -> None:
    migrations = _migration_files()
    assert migrations
    versions = [version for version, _, _ in migrations]
    assert versions == sorted(versions)
    assert len(versions) == len(set(versions))


def test_initial_migration_defines_core_tables() -> None:
    sql = (MIGRATIONS_DIR / "0001_initial_schema.sql").read_text(encoding="utf-8")
    for table in (
        "guild_config",
        "automation_config",
        "moderation_cases",
        "tickets",
        "workflow_definitions",
        "workflow_runs",
        "workflow_run_state",
        "scheduled_tasks",
        "subscriptions",
    ):
        assert f"CREATE TABLE {table}" in sql
    assert "CREATE TABLE IF NOT EXISTS schema_migrations" in sql


def test_initial_migration_removes_legacy_tables() -> None:
    sql = (MIGRATIONS_DIR / "0001_initial_schema.sql").read_text(encoding="utf-8")
    for table in ("warnlogs", "ticket_logs", "guild_logs", "logs_config", "automod", "antialt"):
        assert f"DROP TABLE IF EXISTS {table} CASCADE" in sql


def test_views_are_dropped_before_tables() -> None:
    sql = (MIGRATIONS_DIR / "0001_initial_schema.sql").read_text(encoding="utf-8")
    first_table_drop = sql.index("\nDROP TABLE IF EXISTS")
    for view in ("premium", "workflows", "star_info", "user_timezone"):
        statement = f"DROP VIEW IF EXISTS {view} CASCADE"
        assert statement in sql
        assert sql.index(statement) < first_table_drop
