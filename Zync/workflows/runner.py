"""Discord Cog adapter that feeds events into :class:`WorkflowEngine`.

The adapter owns listeners and the schedule loop; all evaluation and execution
lives in the engine. Persistent views are registered elsewhere and are not
touched here.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord
from discord.ext import tasks

from core.bot import Zync
from core.cog import Cog
from workflows.engine import WorkflowEngine, active_context
from workflows.triggers import TRIGGERS, WorkflowContext

logger = logging.getLogger("bot")


class WorkflowRunner(Cog):
    """Bridge Discord gateway events into the workflow engine."""

    def __init__(self, bot: Zync):
        self.bot = bot
        self.engine = WorkflowEngine(bot)
        self._schedules_ready = False
        self._scheduled_workflows.start()

    async def cog_unload(self) -> None:
        self._scheduled_workflows.cancel()

    def clear_cache(self, guild_id: int | None = None) -> None:
        """Invalidate cached workflows (called by management commands)."""

        self.engine.clear_cache(guild_id)
        self._schedules_ready = False

    def engine_for(self) -> WorkflowEngine:
        return self.engine

    async def _dispatch(self, ctx: WorkflowContext) -> None:
        try:
            await self.engine.dispatch(ctx, parent=active_context())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Workflow dispatch failed for %s: %s", ctx.trigger_type, exc)

    # ── gateway listeners ────────────────────────────────────────────────────

    @Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None:
            return
        await self._dispatch(TRIGGERS.from_message(message, "message_create"))

    @Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is None:
            return
        await self._dispatch(TRIGGERS.from_message(message, "message_delete"))

    @Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self._dispatch(TRIGGERS.from_member(member, "member_join"))

    @Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        await self._dispatch(TRIGGERS.from_member(member, "member_leave"))

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        channel = guild.get_channel(payload.channel_id) or guild.get_thread(payload.channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            message = None
        emoji = str(payload.emoji)
        count = 1
        if message is not None:
            reaction = discord.utils.get(message.reactions, emoji=emoji)
            count = reaction.count if reaction else 1
        member = payload.member or guild.get_member(payload.user_id)
        ctx = TRIGGERS.from_reaction(
            guild, payload, message=message, channel=channel, count=count
        )
        ctx.member = member
        await self._dispatch(ctx)

    @Cog.listener()
    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        before_ids = {role.id for role in before.roles}
        after_ids = {role.id for role in after.roles}
        for role_id in after_ids - before_ids:
            await self._dispatch(
                TRIGGERS.from_role_update(after, role_id, "added")
            )
        for role_id in before_ids - after_ids:
            await self._dispatch(
                TRIGGERS.from_role_update(after, role_id, "removed")
            )

    @Cog.listener()
    async def on_safety_alert(self, *args: Any) -> None:
        """Custom event emitted by ``cogs_hidden.safety_hooks``."""

        ctx = self._event_context("safety_alert", args)
        if ctx is not None:
            await self._dispatch(ctx)

    @Cog.listener()
    async def on_moderation_event(self, *args: Any) -> None:
        """Custom event emitted by moderation services."""

        ctx = self._event_context("moderation_event", args)
        if ctx is not None:
            await self._dispatch(ctx)

    @Cog.listener()
    async def on_ticket_created(self, *args: Any) -> None:
        """Custom event emitted when a ticket thread is opened."""

        ctx = self._event_context("ticket_created", args)
        if ctx is not None:
            await self._dispatch(ctx)

    @Cog.listener(name="on_workflow_event")
    async def on_workflow_event(self, name: str, *args: Any) -> None:
        """Generic entry point for registered custom triggers."""

        guild = self._coerce_guild(args[0] if args else None)
        if guild is None:
            return
        payload = args[1] if len(args) > 1 else None
        await self.engine.dispatch_custom(name, guild, payload)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _coerce_guild(self, value: Any) -> discord.Guild | None:
        if isinstance(value, discord.Guild):
            return value
        if isinstance(value, (discord.Member, discord.Thread, discord.TextChannel)):
            guild = getattr(value, "guild", None)
            return guild if isinstance(guild, discord.Guild) else None
        if isinstance(value, dict):
            guild = value.get("guild")
            if isinstance(guild, discord.Guild):
                return guild
            guild_id = value.get("guild_id")
            if guild_id:
                try:
                    return self.bot.get_guild(int(guild_id))
                except (TypeError, ValueError):
                    return None
        return None

    def _event_context(
        self, trigger: str, args: tuple[Any, ...]
    ) -> WorkflowContext | None:
        if not args:
            return None
        first = args[0]
        guild = self._coerce_guild(first)
        if guild is None:
            return None
        data: dict[str, Any]
        if isinstance(first, dict):
            data = dict(first)
        elif len(args) > 1 and isinstance(args[1], dict):
            data = dict(args[1])
        elif isinstance(first, (discord.Member, discord.User)):
            data = {"user_id": first.id}
            if len(args) > 1 and isinstance(args[1], str):
                data["action"] = args[1]
        elif isinstance(first, (discord.Thread, discord.TextChannel)):
            data = {"thread_id": first.id, "channel_id": first.id}
            if len(args) > 1 and isinstance(args[1], dict):
                data.update(args[1])
        else:
            data = {"value": first}
        if trigger == "moderation_event":
            data.setdefault("action_type", data.get("action", ""))
        if trigger == "ticket_created":
            data.setdefault("creator_id", data.get("user_id", ""))
        for key in ("user_id", "subject_user_id", "creator_id", "thread_id"):
            if data.get(key) == "":
                data.pop(key, None)
        return TRIGGERS.from_event(guild, trigger, data)

    # ── schedule loop ────────────────────────────────────────────────────────

    @tasks.loop(minutes=1)
    async def _scheduled_workflows(self) -> None:
        if not self._schedules_ready:
            for guild in list(self.bot.guilds):
                await self.engine.ensure_schedules(guild.id)
            self._schedules_ready = True
        await self.engine.tick_schedules()

    @_scheduled_workflows.before_loop
    async def _before_scheduled(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: Zync) -> None:
    await bot.add_cog(WorkflowRunner(bot))
