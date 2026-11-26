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


def test_initial_migration_drops_legacy_objects_by_actual_type() -> None:
    sql = (MIGRATIONS_DIR / "0001_initial_schema.sql").read_text(encoding="utf-8")
    assert "SELECT c.relkind INTO object_kind" in sql
    assert "DROP VIEW IF EXISTS %I CASCADE" in sql
    assert "DROP TABLE IF EXISTS %I CASCADE" in sql
    # Names that are tables in the legacy schema and views in the new one must
    # all be handled by the type-aware block.
    for name in (
        "warnlogs", "ticket_logs", "guild_logs", "logs_config",
        "automod", "antialt", "premium", "workflows",
        "star_info", "user_timezone",
    ):
        assert f"'{name}'" in sql


def test_drop_block_runs_before_any_create() -> None:
    sql = (MIGRATIONS_DIR / "0001_initial_schema.sql").read_text(encoding="utf-8")
    assert sql.index("DO $zync_drop$") < sql.index("CREATE TABLE guild_config")


def test_second_migration_drops_all_orphan_tables() -> None:
    sql = (MIGRATIONS_DIR / "0002_drop_legacy_orphans.sql").read_text(encoding="utf-8")
    assert "SELECT c.relkind INTO object_kind" in sql
    for name in (
        "afk", "auto_responders", "guild_themes", "join_automation",
        "prefix", "scheduled_messages", "star_config", "event_actions",
    ):
        assert f"'{name}'" in sql


def test_no_legacy_table_is_left_for_fresh_deployments() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for _, _, path in _migration_files()
    )
    for name in (
        "warnlogs", "ticket_logs", "guild_logs", "logs_config", "automod",
        "antialt", "afk", "auto_responders", "guild_themes", "join_automation",
        "prefix", "scheduled_messages", "star_config", "event_actions",
    ):
        assert f"'{name}'" in combined
