"""Moderation casefiles.

Every punishment is recorded as a row in ``moderation_cases``. Warnings are
soft-resolved (never hard-deleted) so the audit trail survives moderation.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Iterable

from asyncpg import Record

ACTION_TYPES = frozenset(
    {"warn", "timeout", "kick", "ban", "unban", "autoban", "automod", "antialt"}
)
SOURCES = frozenset({"manual", "automod", "antialt", "workflow", "migration"})
STATUSES = frozenset({"active", "resolved", "expired"})

# Actions that count toward warn thresholds. Historically automod warnings and
# anti-alt kicks were written to the same warn log as manual warnings.
WARN_ACTIONS = ("warn", "automod", "antialt")

_SHORT_ID = re.compile(r"^[0-9a-fA-F]{4,8}$")


def _row(row: Record | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def short_case_id(case_id: Any) -> str:
    """Return the compact identifier shown to staff for a case."""

    return str(case_id)[:8]


class ModerationService:
    """CRUD helpers for moderation cases and their edit history."""

    def __init__(self, pool: Any | None) -> None:
        self.db = pool

    # ── creation ────────────────────────────────────────────────────────────

    async def create_case(
        self,
        guild_id: int,
        subject_user_id: int,
        moderator_user_id: int,
        action_type: str,
        *,
        source: str = "manual",
        reason: str = "",
        duration_seconds: int | None = None,
        status: str = "active",
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any] | None:
        """Create a case, returning the existing row when the key already ran.

        A fresh UUID and a unique idempotency key are generated for every call
        unless the caller supplies one for deduplication (scheduled actions,
        retries, event handlers). All values are bound parameters.
        """

        if self.db is None:
            return None
        if action_type not in ACTION_TYPES:
            raise ValueError(f"Unknown moderation action: {action_type}")
        if source not in SOURCES:
            raise ValueError(f"Unknown moderation source: {source}")
        if status not in STATUSES:
            raise ValueError(f"Unknown moderation status: {status}")

        case_id = uuid.uuid4()
        key = idempotency_key or uuid.uuid4().hex
        payload = json.dumps(metadata or {}, default=str)

        row = await self.db.fetchrow(
            """INSERT INTO moderation_cases (
                   case_id, guild_id, subject_user_id, moderator_user_id,
                   action_type, source, reason, duration_seconds, status,
                   metadata, idempotency_key
               ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11)
               ON CONFLICT (idempotency_key) DO NOTHING
               RETURNING *""",
            case_id,
            guild_id,
            subject_user_id,
            moderator_user_id,
            action_type,
            source,
            reason or "",
            duration_seconds,
            status,
            payload,
            key,
        )
        if row is not None:
            return _row(row)

        # The key was already used: return that case rather than raising.
        return _row(
            await self.db.fetchrow(
                "SELECT * FROM moderation_cases WHERE idempotency_key=$1", key
            )
        )

    async def record_manual(
        self,
        guild_id: int,
        subject_user_id: int,
        moderator_user_id: int,
        action_type: str,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        return await self.create_case(
            guild_id,
            subject_user_id,
            moderator_user_id,
            action_type,
            source="manual",
            **kwargs,
        )

    async def record_automod(
        self,
        guild_id: int,
        subject_user_id: int,
        moderator_user_id: int,
        *,
        action_type: str = "automod",
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        return await self.create_case(
            guild_id,
            subject_user_id,
            moderator_user_id,
            action_type,
            source="automod",
            **kwargs,
        )

    async def record_antialt(
        self,
        guild_id: int,
        subject_user_id: int,
        moderator_user_id: int,
        *,
        action_type: str = "antialt",
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        return await self.create_case(
            guild_id,
            subject_user_id,
            moderator_user_id,
            action_type,
            source="antialt",
            **kwargs,
        )

    # ── reads ───────────────────────────────────────────────────────────────

    async def get_case(
        self, guild_id: int, case_id: Any
    ) -> dict[str, Any] | None:
        if self.db is None:
            return None
        return _row(
            await self.db.fetchrow(
                "SELECT * FROM moderation_cases WHERE guild_id=$1 AND case_id=$2",
                guild_id,
                case_id,
            )
        )

    async def recent_antialt_kick(
        self, guild_id: int, subject_user_id: int, *, hours: int = 24
    ) -> dict[str, Any] | None:
        """Return a recent anti-alt kick case for a member, if one exists."""

        if self.db is None:
            return None
        return _row(
            await self.db.fetchrow(
                """SELECT * FROM moderation_cases
                   WHERE guild_id=$1 AND subject_user_id=$2
                     AND action_type='antialt' AND source='antialt'
                     AND metadata->>'action'='kick'
                     AND created_at > NOW() - ($3::int * INTERVAL '1 hour')
                   ORDER BY created_at DESC LIMIT 1""",
                guild_id,
                subject_user_id,
                hours,
            )
        )

    async def resolve_identifier(
        self,
        guild_id: int,
        identifier: str | int,
        *,
        subject_user_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Resolve a full UUID or the short prefix shown in warning lists."""

        if self.db is None:
            return None
        raw = str(identifier).strip()
        try:
            parsed = uuid.UUID(raw)
        except ValueError:
            if not _SHORT_ID.fullmatch(raw):
                return None
            rows = await self.db.fetch(
                """SELECT * FROM moderation_cases
                   WHERE guild_id=$1 AND case_id::text LIKE $2
                     AND ($3::bigint IS NULL OR subject_user_id=$3)
                   ORDER BY created_at DESC LIMIT 2""",
                guild_id,
                raw.lower() + "%",
                subject_user_id,
            )
            return _row(rows[0]) if len(rows) == 1 else None
        else:
            return await self.get_case(guild_id, parsed)

    async def list_cases(
        self,
        guild_id: int,
        *,
        subject_user_id: int | None = None,
        moderator_user_id: int | None = None,
        action_types: Iterable[str] | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if self.db is None:
            return []
        clauses = ["guild_id=$1"]
        args: list[Any] = [guild_id]

        def add(clause: str, value: Any) -> None:
            args.append(value)
            clauses.append(clause.replace("?", f"${len(args)}"))

        if subject_user_id is not None:
            add("subject_user_id=?", subject_user_id)
        if moderator_user_id is not None:
            add("moderator_user_id=?", moderator_user_id)
        if action_types is not None:
            values = tuple(action_types)
            if not values:
                return []
            add("action_type = ANY(?::text[])", list(values))
        if status is not None:
            add("status=?", status)

        args.append(max(1, min(int(limit), 500)))
        sql = (
            "SELECT * FROM moderation_cases WHERE "
            + " AND ".join(clauses)
            + f" ORDER BY created_at DESC LIMIT ${len(args)}"
        )
        return [dict(row) for row in await self.db.fetch(sql, *args)]

    async def warn_count(
        self,
        guild_id: int,
        subject_user_id: int,
        *,
        decay_days: int | None = None,
        action_types: Iterable[str] = WARN_ACTIONS,
    ) -> int:
        """Count active warnings, optionally ignoring ones older than *decay_days*."""

        if self.db is None:
            return 0
        values = tuple(action_types)
        if not values:
            return 0
        return int(
            await self.db.fetchval(
                """SELECT COUNT(*) FROM moderation_cases
                   WHERE guild_id=$1 AND subject_user_id=$2
                     AND status='active' AND action_type = ANY($3::text[])
                     AND ($4::int IS NULL
                          OR created_at >= NOW() - ($4::int * INTERVAL '1 day'))""",
                guild_id,
                subject_user_id,
                list(values),
                decay_days if decay_days and decay_days > 0 else None,
            )
            or 0
        )

    async def case_edits(self, case_id: Any) -> list[dict[str, Any]]:
        if self.db is None:
            return []
        rows = await self.db.fetch(
            "SELECT * FROM moderation_case_edits WHERE case_id=$1 ORDER BY created_at",
            case_id,
        )
        return [dict(row) for row in rows]

    async def insights(self, guild_id: int) -> dict[str, Any]:
        """Aggregates used by ``/mod insights`` from the casefile tables."""

        if self.db is None:
            return {
                "warning_count": 0,
                "total_cases": 0,
                "top_warned": [],
                "top_moderators": [],
                "action_counts": [],
            }

        total = (
            await self.db.fetchval(
                "SELECT COUNT(*) FROM moderation_cases WHERE guild_id=$1", guild_id
            )
            or 0
        )
        warnings = await self.warn_count_all(guild_id)
        top_warned = await self.db.fetch(
            """SELECT subject_user_id AS user_id, COUNT(*) AS count
               FROM moderation_cases
               WHERE guild_id=$1 AND status='active' AND action_type = ANY($2::text[])
               GROUP BY subject_user_id ORDER BY count DESC LIMIT 5""",
            guild_id,
            list(WARN_ACTIONS),
        )
        top_moderators = await self.db.fetch(
            """SELECT moderator_user_id AS mod_id, COUNT(*) AS count
               FROM moderation_cases
               WHERE guild_id=$1 AND action_type='warn'
               GROUP BY moderator_user_id ORDER BY count DESC LIMIT 5""",
            guild_id,
        )
        action_counts = await self.db.fetch(
            """SELECT action_type, COUNT(*) AS count FROM moderation_cases
               WHERE guild_id=$1 GROUP BY action_type ORDER BY count DESC""",
            guild_id,
        )
        return {
            "warning_count": warnings,
            "total_cases": total,
            "top_warned": [dict(row) for row in top_warned],
            "top_moderators": [dict(row) for row in top_moderators],
            "action_counts": [dict(row) for row in action_counts],
        }

    async def warn_count_all(self, guild_id: int) -> int:
        if self.db is None:
            return 0
        return int(
            await self.db.fetchval(
                """SELECT COUNT(*) FROM moderation_cases
                   WHERE guild_id=$1 AND status='active'
                     AND action_type = ANY($2::text[])""",
                guild_id,
                list(WARN_ACTIONS),
            )
            or 0
        )

    # ── resolution ──────────────────────────────────────────────────────────

    async def resolve_case(
        self,
        guild_id: int,
        case_id: Any,
        *,
        resolved_by: int,
        status: str = "resolved",
    ) -> dict[str, Any] | None:
        """Soft-resolve a case and append an audit entry. Idempotent."""

        if self.db is None:
            return None
        async with self.db.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """UPDATE moderation_cases
                       SET status=$3, resolved_at=NOW()
                       WHERE guild_id=$1 AND case_id=$2 AND status='active'
                       RETURNING *""",
                    guild_id,
                    case_id,
                    status,
                )
                if row is None:
                    return None
                await conn.execute(
                    """INSERT INTO moderation_case_edits
                       (case_id, edited_by, field, old_value, new_value)
                       VALUES ($1, $2, 'status', 'active', $3)""",
                    row["case_id"],
                    resolved_by,
                    status,
                )
                return dict(row)

    async def resolve_warnings(
        self,
        guild_id: int,
        subject_user_id: int,
        *,
        resolved_by: int,
        action_types: Iterable[str] = WARN_ACTIONS,
    ) -> int:
        """Resolve every active warning-like case for a member."""

        cases = await self.list_cases(
            guild_id,
            subject_user_id=subject_user_id,
            action_types=action_types,
            status="active",
            limit=500,
        )
        resolved = 0
        for case in cases:
            if await self.resolve_case(
                guild_id, case["case_id"], resolved_by=resolved_by
            ):
                resolved += 1
        return resolved

    async def resolve_active(
        self,
        guild_id: int,
        subject_user_id: int,
        *,
        resolved_by: int,
        action_types: Iterable[str],
    ) -> int:
        """Resolve active cases of the given action types for a member."""

        cases = await self.list_cases(
            guild_id,
            subject_user_id=subject_user_id,
            action_types=action_types,
            status="active",
            limit=500,
        )
        resolved = 0
        for case in cases:
            if await self.resolve_case(
                guild_id, case["case_id"], resolved_by=resolved_by
            ):
                resolved += 1
        return resolved
