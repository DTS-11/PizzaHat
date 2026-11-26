"""Durable scheduled work: timed unbans and raid lockdown restoration.

Every job is a row in ``scheduled_tasks`` first; the background loop only
claims persisted, due rows. Restarts reconcile the queue automatically and
in-memory handles are cancelled when the owning cog unloads.
"""

from __future__ import annotations

import datetime
import json
import uuid
from typing import Any

import discord
from discord.ext import tasks

from core.logging import get_logger
from services.moderation import SOURCES, ModerationService

logger = get_logger("scheduler")

# Other kinds belong to the workflow engine; leave those rows to its runner.
HANDLED_KINDS = ("unban", "restore_verification")
MAX_ATTEMPTS = 3


class SchedulerService:
    """Claim and execute due scheduled tasks with no fire-and-forget jobs."""

    def __init__(self, bot: Any) -> None:
        self.bot = bot
        self.db = getattr(bot, "db", None)
        self.moderation = ModerationService(self.db)
        self._running = False

    # ── lifecycle ───────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the reconciling loop; safe to call more than once."""

        task = getattr(self._due_loop, "_task", None)
        if task is not None and not task.done():
            if task.cancelled():
                # A previous cog unload cancelled the handle; queue a fresh one.
                self._due_loop.restart()
            return
        self._due_loop.start()
        self._running = True

    def stop(self) -> None:
        """Cancel the background handle. Pending rows survive for reconciliation."""

        if self._due_loop.is_running():
            self._due_loop.cancel()
        self._running = False

    @tasks.loop(seconds=15)
    async def _due_loop(self) -> None:
        await self.process_due()

    @_due_loop.before_loop
    async def _before_due_loop(self) -> None:
        await self.bot.wait_until_ready()

    # ── scheduling ──────────────────────────────────────────────────────────

    async def schedule_unban(
        self,
        guild_id: int,
        user_id: int,
        run_at: datetime.datetime,
        *,
        reason: str = "Temporary ban expired",
        source: str = "automod",
        moderator_user_id: int | None = None,
    ) -> uuid.UUID | None:
        """Persist an unban job and return its cancellation handle."""

        if self.db is None:
            return None
        task_id = uuid.uuid4()
        payload = {
            "guild_id": guild_id,
            "user_id": user_id,
            "reason": reason,
            "source": source if source in SOURCES else "automod",
            "moderator_user_id": moderator_user_id or getattr(self.bot.user, "id", 0),
        }
        await self.db.execute(
            """INSERT INTO scheduled_tasks
               (task_id, guild_id, kind, payload, run_at, status)
               VALUES ($1, $2, 'unban', $3::jsonb, $4, 'pending')""",
            task_id,
            guild_id,
            json.dumps(payload, default=str),
            run_at,
        )
        return task_id

    async def schedule_verification_restore(
        self,
        guild_id: int,
        verification_level: discord.VerificationLevel | int,
        run_at: datetime.datetime,
        *,
        reason: str = "AutoMod: Raid lockdown expired",
    ) -> uuid.UUID | None:
        """Persist restoration of a guild's original verification level."""

        if self.db is None:
            return None
        task_id = uuid.uuid4()
        level = int(
            verification_level.value
            if isinstance(verification_level, discord.VerificationLevel)
            else verification_level
        )
        payload = {
            "guild_id": guild_id,
            "verification_level": level,
            "reason": reason,
        }
        await self.db.execute(
            """INSERT INTO scheduled_tasks
               (task_id, guild_id, kind, payload, run_at, status)
               VALUES ($1, $2, 'restore_verification', $3::jsonb, $4, 'pending')""",
            task_id,
            guild_id,
            json.dumps(payload, default=str),
            run_at,
        )
        return task_id

    async def cancel_task(self, task_id: uuid.UUID | str) -> bool:
        """Cancel a pending task; in-flight jobs finish atomically."""

        if self.db is None:
            return False
        result = await self.db.execute(
            """UPDATE scheduled_tasks SET status='cancelled', updated_at=NOW()
               WHERE task_id=$1 AND status='pending'""",
            task_id,
        )
        return result.endswith("1")

    async def cancel_guild_tasks(
        self, guild_id: int, kinds: tuple[str, ...] | None = None
    ) -> int:
        if self.db is None:
            return 0
        kinds = kinds or HANDLED_KINDS
        result = await self.db.execute(
            """UPDATE scheduled_tasks SET status='cancelled', updated_at=NOW()
               WHERE guild_id=$1 AND status='pending' AND kind = ANY($2::text[])""",
            guild_id,
            list(kinds),
        )
        return int(result.rsplit(" ", 1)[-1] or 0)

    # ── reconciliation ──────────────────────────────────────────────────────

    async def process_due(self) -> int:
        """Claim due jobs with ``FOR UPDATE SKIP LOCKED`` and execute them."""

        if self.db is None:
            return 0

        rows = await self.db.fetch(
            """WITH due AS (
                   SELECT task_id FROM scheduled_tasks
                   WHERE status='pending' AND run_at <= NOW()
                     AND kind = ANY($1::text[])
                   ORDER BY run_at
                   LIMIT 25
                   FOR UPDATE SKIP LOCKED
               )
               UPDATE scheduled_tasks AS t
               SET status='running', updated_at=NOW()
               FROM due
               WHERE t.task_id=due.task_id
               RETURNING t.*""",
            list(HANDLED_KINDS),
        )

        for row in rows:
            await self._run_claimed(dict(row))
        return len(rows)

    async def _run_claimed(self, row: dict[str, Any]) -> None:
        task_id = row["task_id"]
        payload = dict(row["payload"] or {})
        payload["task_id"] = str(task_id)
        try:
            success = await self._execute(row["kind"], payload)
        except Exception:
            logger.exception("Scheduled task %s (%s) failed", task_id, row["kind"])
            success = False

        if success:
            await self.db.execute(
                "UPDATE scheduled_tasks SET status='done', updated_at=NOW() "
                "WHERE task_id=$1",
                task_id,
            )
            return

        attempts = int(payload.pop("_attempts", 0)) + 1
        if attempts < MAX_ATTEMPTS:
            payload["_attempts"] = attempts
            await self.db.execute(
                """UPDATE scheduled_tasks
                   SET status='pending', payload=$2::jsonb,
                       run_at=NOW() + INTERVAL '1 minute', updated_at=NOW()
                   WHERE task_id=$1""",
                task_id,
                json.dumps(payload, default=str),
            )
        else:
            await self.db.execute(
                "UPDATE scheduled_tasks SET status='failed', updated_at=NOW() "
                "WHERE task_id=$1",
                task_id,
            )

    async def _execute(self, kind: str, payload: dict[str, Any]) -> bool:
        guild_id = int(payload.get("guild_id", 0))
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            # Keep the row pending: a restart or cache fill may make it runnable.
            return False

        if kind == "unban":
            user_id = int(payload.get("user_id", 0))
            reason = payload.get("reason") or "Temporary ban expired"
            try:
                await guild.unban(discord.Object(id=user_id), reason=reason)
            except discord.NotFound:
                pass  # Already unbanned by staff — still resolve the task.
            except discord.HTTPException:
                return False

            await self.moderation.create_case(
                guild_id,
                user_id,
                int(payload.get("moderator_user_id") or getattr(self.bot.user, "id", 0)),
                "unban",
                source=payload.get("source") if payload.get("source") in SOURCES else "automod",
                reason=reason,
                metadata={"scheduled": True},
                idempotency_key=f"scheduled:unban:{payload.get('task_id')}",
            )
            return True

        if kind == "restore_verification":
            level = int(payload.get("verification_level", 0))
            try:
                await guild.edit(
                    verification_level=discord.VerificationLevel(level),
                    reason=payload.get("reason") or "AutoMod: Raid lockdown expired",
                )
            except discord.HTTPException:
                return False
            return True

        return False
