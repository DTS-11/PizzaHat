"""Database access for workflow definitions, runs, state and scheduled tasks.

Every user-facing query is guild-scoped and parameterized. JSONB values are
serialized here and revalidated on read, so no raw dictionary from the database
is ever trusted by the engine.
"""

from __future__ import annotations

import datetime
import json
import logging
import uuid
from typing import Any

from workflows import schema

logger = logging.getLogger("bot")

_DEFINITION_COLUMNS = (
    "id, definition_id, guild_id, name, description, enabled, schema_version, "
    "revision, trigger_type, trigger_config, conditions, actions, created_by, "
    "created_at, updated_at"
)


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, separators=(",", ":"))


def _as_utc(value: Any) -> datetime.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


class WorkflowRepository:
    """Thin asyncpg wrapper around the workflow tables."""

    def __init__(self, pool: Any | None) -> None:
        self.pool = pool

    @property
    def available(self) -> bool:
        return self.pool is not None

    @staticmethod
    def _definition(row: Any) -> dict[str, Any] | None:
        raw: dict[str, Any] = {
            "id": row["id"],
            "definition_id": str(row["definition_id"]),
            "guild_id": row["guild_id"],
            "name": row["name"],
            "description": row["description"] or "",
            "enabled": row["enabled"],
            "schema_version": row["schema_version"],
            "revision": row["revision"],
            "trigger_type": row["trigger_type"],
            "trigger_config": schema.parse_jsonb(row["trigger_config"]),
            "conditions": schema.parse_jsonb(row["conditions"]),
            "actions": schema.parse_jsonb(row["actions"]),
            "created_by": row["created_by"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        try:
            return schema.validate_workflow(raw, allow_row_fields=True)
        except schema.WorkflowValidationError as exc:
            logger.warning("Skipping invalid workflow %s: %s", row["id"], exc)
            return None

    async def list_enabled(
        self, guild_id: int, *, trigger_type: str | None = None
    ) -> list[dict[str, Any]]:
        """Return validated enabled workflows for one guild."""

        if self.pool is None:
            return []
        if trigger_type is None:
            rows = await self.pool.fetch(
                f"SELECT {_DEFINITION_COLUMNS} FROM workflow_definitions "
                "WHERE guild_id=$1 AND enabled=TRUE ORDER BY id",
                guild_id,
            )
        else:
            rows = await self.pool.fetch(
                f"SELECT {_DEFINITION_COLUMNS} FROM workflow_definitions "
                "WHERE guild_id=$1 AND enabled=TRUE AND trigger_type=$2 ORDER BY id",
                guild_id,
                trigger_type,
            )
        return [item for row in rows if (item := self._definition(row)) is not None]

    async def list_all(self, guild_id: int) -> list[dict[str, Any]]:
        if self.pool is None:
            return []
        rows = await self.pool.fetch(
            f"SELECT {_DEFINITION_COLUMNS} FROM workflow_definitions "
            "WHERE guild_id=$1 ORDER BY id",
            guild_id,
        )
        return [item for row in rows if (item := self._definition(row)) is not None]

    async def get(self, guild_id: int, workflow_id: int) -> dict[str, Any] | None:
        if self.pool is None:
            return None
        row = await self.pool.fetchrow(
            f"SELECT {_DEFINITION_COLUMNS} FROM workflow_definitions "
            "WHERE id=$1 AND guild_id=$2",
            workflow_id,
            guild_id,
        )
        return self._definition(row) if row is not None else None

    async def get_by_definition(
        self, guild_id: int, definition_id: str
    ) -> dict[str, Any] | None:
        if self.pool is None:
            return None
        row = await self.pool.fetchrow(
            f"SELECT {_DEFINITION_COLUMNS} FROM workflow_definitions "
            "WHERE definition_id=$1::uuid AND guild_id=$2",
            str(definition_id),
            guild_id,
        )
        return self._definition(row) if row is not None else None

    async def count_active(
        self, guild_id: int, *, exclude_id: int | None = None
    ) -> int:
        if self.pool is None:
            return 0
        if exclude_id is None:
            value = await self.pool.fetchval(
                "SELECT COUNT(*) FROM workflow_definitions "
                "WHERE guild_id=$1 AND enabled=TRUE",
                guild_id,
            )
        else:
            value = await self.pool.fetchval(
                "SELECT COUNT(*) FROM workflow_definitions "
                "WHERE guild_id=$1 AND enabled=TRUE AND id<>$2",
                guild_id,
                exclude_id,
            )
        return int(value or 0)

    async def create(
        self, guild_id: int, definition: dict[str, Any], created_by: int
    ) -> dict[str, Any] | None:
        if self.pool is None:
            return None
        row = await self.pool.fetchrow(
            "INSERT INTO workflow_definitions "
            "(definition_id, guild_id, name, description, enabled, schema_version, "
            "revision, trigger_type, trigger_config, conditions, actions, created_by) "
            "VALUES ($1::uuid, $2, $3, $4, $5, $6, 1, $7, $8::jsonb, $9::jsonb, "
            "$10::jsonb, $11) "
            f"RETURNING {_DEFINITION_COLUMNS}",
            str(uuid.uuid4()),
            guild_id,
            definition["name"],
            definition.get("description", ""),
            bool(definition.get("enabled", True)),
            int(definition.get("schema_version") or schema.CURRENT_SCHEMA_VERSION),
            definition["trigger_type"],
            _json(definition["trigger_config"]),
            _json(definition["conditions"]),
            _json(definition["actions"]),
            created_by,
        )
        return self._definition(row) if row is not None else None

    async def update(
        self, guild_id: int, workflow_id: int, definition: dict[str, Any]
    ) -> dict[str, Any] | None:
        if self.pool is None:
            return None
        row = await self.pool.fetchrow(
            "UPDATE workflow_definitions SET "
            "name=$3, description=$4, enabled=$5, schema_version=$6, "
            "revision=revision+1, trigger_type=$7, trigger_config=$8::jsonb, "
            "conditions=$9::jsonb, actions=$10::jsonb, updated_at=NOW() "
            "WHERE id=$1 AND guild_id=$2 "
            f"RETURNING {_DEFINITION_COLUMNS}",
            workflow_id,
            guild_id,
            definition["name"],
            definition.get("description", ""),
            bool(definition.get("enabled", True)),
            int(definition.get("schema_version") or schema.CURRENT_SCHEMA_VERSION),
            definition["trigger_type"],
            _json(definition["trigger_config"]),
            _json(definition["conditions"]),
            _json(definition["actions"]),
        )
        return self._definition(row) if row is not None else None

    async def toggle(
        self, guild_id: int, workflow_id: int, enabled: bool
    ) -> dict[str, Any] | None:
        if self.pool is None:
            return None
        row = await self.pool.fetchrow(
            "UPDATE workflow_definitions SET enabled=$3, updated_at=NOW() "
            "WHERE id=$1 AND guild_id=$2 "
            f"RETURNING {_DEFINITION_COLUMNS}",
            workflow_id,
            guild_id,
            bool(enabled),
        )
        return self._definition(row) if row is not None else None

    async def delete(self, guild_id: int, workflow_id: int) -> bool:
        if self.pool is None:
            return False
        result = await self.pool.execute(
            "DELETE FROM workflow_definitions WHERE id=$1 AND guild_id=$2",
            workflow_id,
            guild_id,
        )
        return str(result).endswith("1")

    async def record_run_start(
        self,
        guild_id: int,
        workflow_id: int,
        trigger_type: str,
        event_key: str,
        matched_conditions: list[dict[str, Any]] | None = None,
    ) -> str | None:
        """Insert a run row; ``None`` means this event was already processed."""

        if self.pool is None:
            return None
        value = await self.pool.fetchval(
            "INSERT INTO workflow_runs "
            "(run_id, workflow_id, guild_id, trigger_type, event_key, status, "
            "matched_conditions, action_results) "
            "VALUES ($1::uuid, $2, $3, $4, $5, 'running', $6::jsonb, '[]'::jsonb) "
            "ON CONFLICT (event_key) DO NOTHING RETURNING run_id",
            str(uuid.uuid4()),
            workflow_id,
            guild_id,
            trigger_type,
            event_key,
            _json(matched_conditions or []),
        )
        return str(value) if value is not None else None

    async def finish_run(
        self,
        run_id: str,
        status: str,
        action_results: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> None:
        if self.pool is None:
            return
        if status not in ("completed", "failed", "cancelled", "skipped"):
            status = "failed"
        await self.pool.execute(
            "UPDATE workflow_runs SET status=$2, action_results=$3::jsonb, "
            "error=$4, finished_at=NOW() WHERE run_id=$1::uuid",
            str(run_id),
            status,
            _json(action_results or []),
            (str(error)[:2000] if error else None),
        )

    async def set_state(
        self,
        workflow_id: int,
        guild_id: int,
        scope_key: str,
        run_at: datetime.datetime | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self.pool is None:
            return
        await self.pool.execute(
            "INSERT INTO workflow_run_state "
            "(state_id, workflow_id, guild_id, scope_key, run_at, metadata) "
            "VALUES ($1::uuid, $2, $3, $4, $5, $6::jsonb) "
            "ON CONFLICT (workflow_id, scope_key) DO UPDATE SET "
            "run_at=EXCLUDED.run_at, metadata=EXCLUDED.metadata, updated_at=NOW()",
            str(uuid.uuid4()),
            workflow_id,
            guild_id,
            scope_key,
            run_at,
            _json(metadata or {}),
        )

    async def get_state(
        self, workflow_id: int, guild_id: int, scope_key: str
    ) -> dict[str, Any] | None:
        if self.pool is None:
            return None
        row = await self.pool.fetchrow(
            "SELECT state_id, run_at, metadata FROM workflow_run_state "
            "WHERE workflow_id=$1 AND guild_id=$2 AND scope_key=$3",
            workflow_id,
            guild_id,
            scope_key,
        )
        return dict(row) if row is not None else None

    async def cooldown_ready(
        self,
        workflow_id: int | None,
        guild_id: int,
        scope_key: str,
        seconds: int,
        *,
        consume: bool = True,
    ) -> bool:
        """Return whether a cooldown has expired, consuming the slot when asked."""

        if self.pool is None or workflow_id is None:
            return True
        row = await self.pool.fetchrow(
            "SELECT run_at FROM workflow_run_state "
            "WHERE workflow_id=$1 AND guild_id=$2 AND scope_key=$3",
            workflow_id,
            guild_id,
            scope_key,
        )
        now = datetime.datetime.now(datetime.timezone.utc)
        if row is not None and row["run_at"] is not None:
            expires = _as_utc(row["run_at"])
            if expires > now:
                return False
        if consume:
            expires = now + datetime.timedelta(seconds=seconds)
            await self.set_state(
                workflow_id,
                guild_id,
                scope_key,
                expires,
                {"kind": "cooldown", "seconds": seconds},
            )
        return True

    async def claim_state(
        self,
        workflow_id: int,
        guild_id: int,
        scope_key: str,
        *,
        lease_seconds: int = 900,
    ) -> bool:
        """Atomically claim a due state row (``run_at`` NULL means in progress)."""

        if self.pool is None:
            return False
        value = await self.pool.fetchval(
            "UPDATE workflow_run_state SET run_at=NULL, updated_at=NOW() "
            "WHERE state_id = ("
            "  SELECT state_id FROM workflow_run_state "
            "  WHERE workflow_id=$1 AND guild_id=$2 AND scope_key=$3 "
            "  AND ((run_at IS NOT NULL AND run_at <= NOW()) "
            "       OR (run_at IS NULL AND updated_at < NOW() - make_interval(secs => $4))) "
            "  FOR UPDATE SKIP LOCKED LIMIT 1"
            ") RETURNING state_id",
            workflow_id,
            guild_id,
            scope_key,
            int(lease_seconds),
        )
        return value is not None

    async def clear_state(self, guild_id: int, workflow_id: int | None = None) -> None:
        """Remove cooldown/schedule state (used when definitions are deleted)."""

        if self.pool is None:
            return
        if workflow_id is None:
            await self.pool.execute(
                "DELETE FROM workflow_run_state WHERE guild_id=$1", guild_id
            )
        else:
            await self.pool.execute(
                "DELETE FROM workflow_run_state WHERE guild_id=$1 AND workflow_id=$2",
                guild_id,
                workflow_id,
            )

    async def clear_cache_keys(
        self, guild_id: int, workflow_id: int | None = None
    ) -> None:
        """Drop persisted cache-like keys for changed definitions."""

        await self.clear_state(guild_id, workflow_id)

    async def create_task(
        self,
        guild_id: int,
        kind: str,
        payload: dict[str, Any],
        run_at: datetime.datetime,
        task_id: str | None = None,
    ) -> str | None:
        if self.pool is None:
            return None
        value = await self.pool.fetchval(
            "INSERT INTO scheduled_tasks "
            "(task_id, guild_id, kind, payload, run_at) "
            "VALUES ($1::uuid, $2, $3, $4::jsonb, $5) "
            "ON CONFLICT (task_id) DO NOTHING RETURNING task_id",
            str(task_id or uuid.uuid4()),
            guild_id,
            kind,
            _json(payload),
            run_at,
        )
        return str(value) if value is not None else None

    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        if self.pool is None:
            return None
        row = await self.pool.fetchrow(
            "SELECT task_id, guild_id, kind, payload, run_at, status "
            "FROM scheduled_tasks WHERE task_id=$1::uuid",
            str(task_id),
        )
        if row is None:
            return None
        return {
            "task_id": str(row["task_id"]),
            "guild_id": row["guild_id"],
            "kind": row["kind"],
            "payload": schema.parse_jsonb(row["payload"]),
            "run_at": row["run_at"],
            "status": row["status"],
        }

    async def reactivate_task(
        self, task_id: str, payload: dict[str, Any], run_at: datetime.datetime
    ) -> None:
        """Re-queue a finished schedule task after its workflow is re-enabled."""

        if self.pool is None:
            return
        await self.pool.execute(
            "UPDATE scheduled_tasks SET status='pending', payload=$2::jsonb, "
            "run_at=$3, updated_at=NOW() WHERE task_id=$1::uuid "
            "AND status IN ('done', 'cancelled', 'failed')",
            str(task_id),
            _json(payload),
            run_at,
        )

    async def claim_due_tasks(
        self, *, kinds: tuple[str, ...] = ("workflow_schedule",), limit: int = 10
    ) -> list[dict[str, Any]]:
        """Atomically claim due tasks so restarts never re-fire the same slot."""

        if self.pool is None:
            return []
        rows = await self.pool.fetch(
            "UPDATE scheduled_tasks SET status='running', updated_at=NOW() "
            "WHERE task_id IN ("
            "  SELECT task_id FROM scheduled_tasks "
            "  WHERE status='pending' AND run_at <= NOW() AND kind = ANY($1::text[]) "
            "  ORDER BY run_at FOR UPDATE SKIP LOCKED LIMIT $2"
            ") RETURNING task_id, guild_id, kind, payload, run_at",
            list(kinds),
            max(1, min(int(limit), 50)),
        )
        return [
            {
                "task_id": str(row["task_id"]),
                "guild_id": row["guild_id"],
                "kind": row["kind"],
                "payload": schema.parse_jsonb(row["payload"]),
                "run_at": row["run_at"],
            }
            for row in rows
        ]

    async def finish_task(
        self,
        task_id: str,
        status: str,
        run_at: datetime.datetime | None = None,
    ) -> None:
        if self.pool is None:
            return
        if status == "pending" and run_at is not None:
            await self.pool.execute(
                "UPDATE scheduled_tasks SET status='pending', run_at=$2, "
                "updated_at=NOW() WHERE task_id=$1::uuid",
                str(task_id),
                run_at,
            )
            return
        if status not in ("done", "cancelled", "failed"):
            status = "failed"
        await self.pool.execute(
            "UPDATE scheduled_tasks SET status=$2, updated_at=NOW() "
            "WHERE task_id=$1::uuid",
            str(task_id),
            status,
        )

    async def recover_stale_tasks(self, *, minutes: int = 15) -> int:
        """Requeue tasks left ``running`` by a crashed process."""

        if self.pool is None:
            return 0
        result = await self.pool.execute(
            "UPDATE scheduled_tasks SET status='pending', updated_at=NOW() "
            "WHERE status='running' AND updated_at < NOW() - make_interval(mins => $1)",
            max(1, int(minutes)),
        )
        return int(str(result).rsplit(" ", 1)[-1] or 0)

    async def cancel_pending_schedule(self, guild_id: int, workflow_id: int) -> None:
        if self.pool is None:
            return
        await self.pool.execute(
            "UPDATE scheduled_tasks SET status='cancelled', updated_at=NOW() "
            "WHERE guild_id=$1 AND kind='workflow_schedule' AND status='pending' "
            "AND (payload->>'workflow_id') ~ '^[0-9]+$' "
            "AND (payload->>'workflow_id')::bigint=$2",
            guild_id,
            workflow_id,
        )

    async def get_dedupe(self, guild_id: int, source_message_id: int) -> int | None:
        if self.pool is None:
            return None
        value = await self.pool.fetchval(
            "SELECT bot_message_id FROM workflow_dedupe "
            "WHERE guild_id=$1 AND source_message_id=$2",
            guild_id,
            source_message_id,
        )
        return int(value) if value is not None else None

    async def set_dedupe(
        self, guild_id: int, source_message_id: int, bot_message_id: int
    ) -> None:
        if self.pool is None:
            return
        await self.pool.execute(
            "INSERT INTO workflow_dedupe (guild_id, source_message_id, bot_message_id) "
            "VALUES ($1, $2, $3) ON CONFLICT (guild_id, source_message_id) DO NOTHING",
            guild_id,
            source_message_id,
            bot_message_id,
        )

    async def clear_dedupe(
        self, guild_id: int, source_message_id: int | None = None
    ) -> None:
        if self.pool is None:
            return
        if source_message_id is None:
            await self.pool.execute(
                "DELETE FROM workflow_dedupe WHERE guild_id=$1", guild_id
            )
        else:
            await self.pool.execute(
                "DELETE FROM workflow_dedupe WHERE guild_id=$1 AND source_message_id=$2",
                guild_id,
                source_message_id,
            )
