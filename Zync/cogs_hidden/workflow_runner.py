"""Event evaluation and action execution for the unified workflow engine.

Workflows are cached per guild and validated on load, so no PostgreSQL query is
issued per message. Conditions are deterministic; actions run sequentially with
per-workflow locking and HTTP error/rate-limit handling.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

import discord
from discord.ext import tasks

from core.bot import Zync
from core.cog import Cog
from utils.ui import TicketSettings
from utils.workflow_schema import (
    WorkflowValidationError,
    parse_jsonb,
    validate_workflow,
)

logger = logging.getLogger("bot")

LINK_REGEX = re.compile(
    r"https?://|discord\.(gg|io|me|li)/|discordapp\.com|discord\.com/invite/",
    re.IGNORECASE,
)


@dataclass
class WorkflowContext:
    """Normalized event data passed to conditions and actions."""

    guild: discord.Guild
    trigger_type: str
    member: discord.Member | discord.User | None = None
    message: discord.Message | None = None
    channel: discord.abc.Messageable | None = None
    payload: discord.RawReactionActionEvent | None = None
    alert: dict[str, Any] | None = None
    emoji: str | None = None
    reaction_count: int = 0
    role_event: str | None = None
    timezone: str = "UTC"
    extra: dict[str, str] = field(default_factory=dict)


class WorkflowRunner(Cog):
    """Listens for Discord events and runs matching workflows."""

    def __init__(self, bot: Zync):
        self.bot = bot
        self._cache: dict[int, list[dict[str, Any]]] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._cooldowns: dict[tuple[int, int, str, int], float] = {}
        self._schedule_keys: dict[int, str] = {}
        self._scheduled_workflows.start()

    async def cog_unload(self) -> None:
        self._scheduled_workflows.cancel()

    # ── cache ─────────────────────────────────────────────────────────────────

    def clear_cache(self, guild_id: int | None = None) -> None:
        """Invalidate cached workflows after a create/update/delete/toggle."""
        if guild_id is None:
            self._cache.clear()
            self._cooldowns.clear()
            self._schedule_keys.clear()
        else:
            old_ids = {w["id"] for w in self._cache.get(guild_id, [])}
            self._cache.pop(guild_id, None)
            self._cooldowns = {
                key: value
                for key, value in self._cooldowns.items()
                if key[0] != guild_id
            }
            self._schedule_keys = {
                wid: slot
                for wid, slot in self._schedule_keys.items()
                if wid not in old_ids
            }

    async def workflows_for(self, guild_id: int) -> list[dict[str, Any]]:
        """Return validated active workflows for a guild (cached)."""
        if guild_id in self._cache:
            return self._cache[guild_id]

        workflows: list[dict[str, Any]] = []
        if self.bot.db is not None:
            rows = await self.bot.db.fetch(
                "SELECT id, guild_id, name, enabled, trigger_type, trigger_config, "
                "conditions, actions FROM workflows "
                "WHERE guild_id=$1 AND enabled=TRUE ORDER BY id",
                guild_id,
            )
            for row in rows:
                raw = {
                    "id": row["id"],
                    "guild_id": row["guild_id"],
                    "name": row["name"],
                    "enabled": row["enabled"],
                    "trigger_type": row["trigger_type"],
                    "trigger_config": parse_jsonb(row["trigger_config"]),
                    "conditions": parse_jsonb(row["conditions"]),
                    "actions": parse_jsonb(row["actions"]),
                }
                try:
                    workflow = validate_workflow(raw, allow_row_fields=True)
                except WorkflowValidationError as exc:
                    logger.warning("Skipping invalid workflow %s: %s", row["id"], exc)
                    continue
                workflow["id"] = row["id"]
                workflow["guild_id"] = row["guild_id"]
                workflows.append(workflow)
        self._cache[guild_id] = workflows
        return workflows

    def _lock(self, workflow_id: int) -> asyncio.Lock:
        return self._locks.setdefault(workflow_id, asyncio.Lock())

    # ── template variables ────────────────────────────────────────────────────

    @staticmethod
    def _render(text: str, variables: dict[str, str]) -> str:
        for key, value in variables.items():
            text = text.replace(f"{{{key}}}", str(value))
        return text

    def _variables(
        self, ctx: WorkflowContext, config: dict[str, Any]
    ) -> dict[str, str]:
        variables: dict[str, str] = {
            "guild": ctx.guild.name,
            "guild.id": str(ctx.guild.id),
            "timezone": config.get("timezone", ctx.timezone),
        }
        user = ctx.member or (ctx.message.author if ctx.message else None)
        if user is not None:
            variables.update(
                {
                    "user": str(user),
                    "user.mention": user.mention,
                    "user.name": getattr(user, "name", str(user)),
                    "user.id": str(user.id),
                }
            )
        if ctx.channel is not None:
            variables["channel"] = getattr(ctx.channel, "mention", str(ctx.channel))
            variables["channel.id"] = str(getattr(ctx.channel, "id", ""))
        if ctx.message is not None:
            variables["content"] = ctx.message.content
            variables["message_url"] = ctx.message.jump_url
        if ctx.emoji is not None:
            variables["emoji"] = ctx.emoji
        variables["emoji_count"] = str(ctx.reaction_count)
        variables["trigger"] = ctx.trigger_type
        if ctx.alert:
            variables["source"] = str(ctx.alert.get("source", ""))
            variables["module"] = str(ctx.alert.get("module", ""))
        variables.update(ctx.extra)
        return variables

    # ── condition evaluation ──────────────────────────────────────────────────

    @staticmethod
    def _content(ctx: WorkflowContext) -> str:
        if ctx.message is not None:
            return ctx.message.content
        if ctx.alert:
            return str(ctx.alert.get("message", ""))
        return ""

    def _matches_text(self, text: str, expected: str, match: str) -> bool:
        if match == "exact":
            return text.lower() == expected.lower()
        if match == "starts_with":
            return text.lower().startswith(expected.lower())
        if match == "regex":
            try:
                return bool(re.search(expected, text, re.IGNORECASE))
            except re.error:
                return False
        return expected.lower() in text.lower()

    def _passes(
        self,
        workflow_id: int,
        conditions: list[dict[str, Any]],
        ctx: WorkflowContext,
    ) -> bool:
        now = time.monotonic()
        pending_cooldowns: list[tuple[int, int, str, int]] = []
        for condition in conditions:
            kind = condition["type"]
            passed = True

            if kind == "account_age_lt":
                created = getattr(ctx.member, "created_at", None)
                if created is None:
                    passed = False
                else:
                    age = (
                        datetime.datetime.now(datetime.timezone.utc) - created
                    ).total_seconds() / 86400
                    passed = age < condition["days"]

            elif kind == "contains_link":
                passed = bool(LINK_REGEX.search(self._content(ctx)))
                if condition.get("negate"):
                    passed = not passed

            elif kind == "contains_text":
                passed = self._matches_text(
                    self._content(ctx),
                    condition["text"],
                    condition.get("match", "contains"),
                )
                if condition.get("negate"):
                    passed = not passed

            elif kind == "has_role":
                roles = getattr(ctx.member, "roles", [])
                passed = any(r.id == condition["role_id"] for r in roles)
                if condition.get("negate"):
                    passed = not passed

            elif kind == "channel_in":
                channel_id = getattr(ctx.channel, "id", 0)
                passed = channel_id in condition["channel_ids"]
                if condition.get("negate"):
                    passed = not passed

            elif kind == "cooldown_sec":
                scope = condition.get("scope", "user")
                scope_id = {
                    "user": getattr(ctx.member, "id", 0),
                    "guild": ctx.guild.id,
                    "workflow": 0,
                }[scope]
                key = (ctx.guild.id, workflow_id, scope, scope_id)
                last = self._cooldowns.get(key, 0.0)
                passed = now - last >= condition["seconds"]
                if passed:
                    pending_cooldowns.append(key)

            elif kind == "is_bot":
                user = ctx.member or (ctx.message.author if ctx.message else None)
                passed = bool(getattr(user, "bot", False)) == condition["value"]

            elif kind == "emoji_is":
                passed = ctx.emoji == condition["emoji"]

            elif kind == "reaction_count_gte":
                passed = ctx.reaction_count >= condition["count"]

            elif kind == "not_self_react":
                author_id = getattr(
                    ctx.message.author if ctx.message else None, "id", 0
                )
                reactor_id = getattr(ctx.payload, "user_id", 0) if ctx.payload else 0
                passed = author_id != reactor_id

            if not passed:
                return False
        for key in pending_cooldowns:
            self._cooldowns[key] = now
        return True

    # ── trigger filtering ─────────────────────────────────────────────────────

    @staticmethod
    def _trigger_matches(workflow: dict[str, Any], ctx: WorkflowContext) -> bool:
        if workflow["trigger_type"] != ctx.trigger_type:
            return False
        config = workflow["trigger_config"]
        if ctx.trigger_type == "message_create":
            if (
                config.get("ignore_bots", True)
                and ctx.message
                and ctx.message.author.bot
            ):
                return False
            channel_ids = config.get("channel_ids") or []
            if (
                channel_ids
                and ctx.channel is not None
                and getattr(ctx.channel, "id", None) not in channel_ids
            ):
                return False
            if "contains_text" in config and ctx.message is not None:
                text = ctx.message.content
                match = config.get("match", "contains")
                if match == "exact":
                    return text.lower() == config["contains_text"].lower()
                if match == "starts_with":
                    return text.lower().startswith(config["contains_text"].lower())
                if match == "regex":
                    return bool(re.search(config["contains_text"], text, re.IGNORECASE))
                return config["contains_text"].lower() in text.lower()
        elif ctx.trigger_type == "reaction_add":
            channel_ids = config.get("channel_ids") or []
            if (
                channel_ids
                and ctx.channel is not None
                and getattr(ctx.channel, "id", None) not in channel_ids
            ):
                return False
            if ctx.emoji != config.get("emoji"):
                return False
            if ctx.reaction_count < config.get("min_reactions", 1):
                return False
        elif ctx.trigger_type == "role_update":
            if ctx.role_event != config.get("event"):
                return False
            role_id = ctx.extra.get("role_id")
            if role_id is not None and int(role_id) != config.get("role_id"):
                return False
        elif ctx.trigger_type == "safety_alert":
            source = (ctx.alert or {}).get("source", "any")
            if config.get("source", "any") not in ("any", source):
                return False
        return True

    async def _dispatch(self, ctx: WorkflowContext) -> None:
        workflows = await self.workflows_for(ctx.guild.id)
        for workflow in workflows:
            if not self._trigger_matches(workflow, ctx):
                continue
            if not self._passes(workflow["id"], workflow["conditions"], ctx):
                continue
            await self._execute(workflow, ctx)

    async def _execute(self, workflow: dict[str, Any], ctx: WorkflowContext) -> None:
        variables = self._variables(ctx, workflow["trigger_config"])
        async with self._lock(workflow["id"]):
            for index, action in enumerate(workflow["actions"]):
                try:
                    await self._run_action(
                        action, ctx, workflow["trigger_config"], variables
                    )
                except discord.HTTPException as exc:
                    if exc.status == 429:
                        retry = min(float(getattr(exc, "retry_after", 1.0) or 1.0), 5.0)
                        await asyncio.sleep(retry)
                    logger.warning(
                        "Workflow %s action %s failed: %s", workflow["id"], index, exc
                    )
                except Exception as exc:  # keep later actions deterministic
                    logger.warning(
                        "Workflow %s action %s failed: %s", workflow["id"], index, exc
                    )
                await asyncio.sleep(0.2)  # rate-limit safety between actions

    # ── actions ───────────────────────────────────────────────────────────────

    async def _run_action(
        self,
        action: dict[str, Any],
        ctx: WorkflowContext,
        trigger_config: dict[str, Any],
        variables: dict[str, str],
    ) -> None:
        kind = action["type"]

        if kind in ("add_role", "remove_role"):
            member = ctx.member
            if not isinstance(member, discord.Member):
                return
            role = ctx.guild.get_role(action["role_id"])
            me = ctx.guild.me
            if role is None or me is None:
                return
            if not me.guild_permissions.manage_roles or role >= me.top_role:
                return
            if kind == "add_role":
                await member.add_roles(role, reason=f"Workflow: {ctx.trigger_type}")
            else:
                await member.remove_roles(role, reason=f"Workflow: {ctx.trigger_type}")
            return

        if kind == "timeout_member":
            if not isinstance(ctx.member, discord.Member):
                return
            until = discord.utils.utcnow() + datetime.timedelta(
                minutes=action["minutes"]
            )
            await ctx.member.timeout(until, reason=f"Workflow: {ctx.trigger_type}")
            return

        if kind == "send_dm":
            if ctx.member is not None:
                await ctx.member.send(self._render(action["message"], variables))
            return

        if kind in ("send_embed", "send_message", "log_channel", "open_ticket"):
            channel_id = action.get("channel_id")
            channel = (
                ctx.guild.get_channel(channel_id)
                if channel_id
                else (
                    ctx.channel
                    if isinstance(ctx.channel, (discord.TextChannel, discord.Thread))
                    else None
                )
            )
            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                return

            if kind == "send_message":
                await channel.send(self._render(action["message"], variables))
                return

            if kind == "log_channel":
                em = discord.Embed(
                    description=self._render(action["message"], variables),
                    color=0x456DD4,
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                )
                if isinstance(channel, discord.TextChannel):
                    await self.bot.send_log(channel, embed=em)
                else:
                    await channel.send(embed=em)
                return

            if kind == "open_ticket":
                member = ctx.member
                if not isinstance(member, discord.Member) or not isinstance(
                    channel, discord.TextChannel
                ):
                    return
                thread = await channel.create_thread(
                    name=f"ticket-{member}",
                    reason=f"Workflow ticket: {ctx.trigger_type}",
                    invitable=False,
                )
                await thread.add_user(member)
                if self.bot.db is not None:
                    await self.bot.db.execute(
                        "INSERT INTO ticket_logs (guild_id, thread_id, creator_id) "
                        "VALUES ($1, $2, $3) ON CONFLICT (thread_id) DO NOTHING",
                        ctx.guild.id,
                        thread.id,
                        member.id,
                    )
                content = member.mention
                if action.get("support_role_id"):
                    role = ctx.guild.get_role(action["support_role_id"])
                    if role:
                        content += f" {role.mention}"
                em = discord.Embed(
                    title=action.get("panel_name", "Support"),
                    description=(
                        f"Welcome, {member.mention}! A workflow opened this ticket. "
                        "Please describe your issue."
                    ),
                    color=0x57F287,
                )
                await thread.send(
                    content=content, embed=em, view=TicketSettings(thread.id, self.bot)
                )
                return

            # send_embed
            if action.get("from_message") and ctx.message is not None:
                source = ctx.message
                title = action.get("title") or f"Highlighted message by {source.author}"
                description = action.get("description") or (source.content or "")
                em = discord.Embed(
                    title=self._render(title, variables)[:256],
                    description=self._render(description, variables)[:4096],
                    color=action.get("color", 0xFFD700),
                    timestamp=source.created_at,
                )
                em.set_author(
                    name=str(source.author),
                    icon_url=source.author.display_avatar.url,
                )
                em.add_field(
                    name="Source", value=f"[Jump to message]({source.jump_url})"
                )
                if source.attachments:
                    em.set_image(url=source.attachments[0].url)
                em.set_footer(text=f"ID: {source.id}")
            else:
                em = discord.Embed(
                    title=self._render(action.get("title", ""), variables)[:256]
                    or None,
                    description=self._render(action.get("description", ""), variables)[
                        :4096
                    ]
                    or None,
                    color=action.get("color", 0x456DD4),
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                )
            content = self._render(action.get("content", ""), variables) or None

            if (
                action.get("dedupe")
                and ctx.message is not None
                and self.bot.db is not None
            ):
                bot_msg_id = await self.bot.db.fetchval(
                    "SELECT bot_msg_id FROM star_info WHERE guild_id=$1 AND user_msg_id=$2",
                    ctx.guild.id,
                    ctx.message.id,
                )
                if bot_msg_id:
                    try:
                        existing = await channel.fetch_message(bot_msg_id)
                        await existing.edit(content=content, embed=em)
                        return
                    except discord.NotFound:
                        pass
                sent = await channel.send(content=content, embed=em)
                await self.bot.db.execute(
                    "INSERT INTO star_info (guild_id, user_msg_id, bot_msg_id) "
                    "VALUES ($1, $2, $3) ON CONFLICT (user_msg_id) DO NOTHING",
                    ctx.guild.id,
                    ctx.message.id,
                    sent.id,
                )
                return
            await channel.send(content=content, embed=em)

    # ── listeners ─────────────────────────────────────────────────────────────

    @Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None:
            return
        await self._dispatch(
            WorkflowContext(
                guild=message.guild,
                trigger_type="message_create",
                member=message.author
                if isinstance(message.author, discord.Member)
                else None,
                message=message,
                channel=message.channel,
            )
        )

    @Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self._dispatch(
            WorkflowContext(
                guild=member.guild,
                trigger_type="member_join",
                member=member,
                channel=member.guild.system_channel,
            )
        )

    @Cog.listener()
    async def on_raw_reaction_add(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        channel = guild.get_channel(payload.channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return
        emoji = str(payload.emoji)
        reaction = discord.utils.get(message.reactions, emoji=emoji)
        count = reaction.count if reaction else 1
        await self._dispatch(
            WorkflowContext(
                guild=guild,
                trigger_type="reaction_add",
                member=payload.member,
                message=message,
                channel=channel,
                payload=payload,
                emoji=emoji,
                reaction_count=count,
            )
        )

    @Cog.listener()
    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        before_ids = {role.id for role in before.roles}
        after_ids = {role.id for role in after.roles}
        for role_id in after_ids - before_ids:
            await self._dispatch(
                WorkflowContext(
                    guild=after.guild,
                    trigger_type="role_update",
                    member=after,
                    channel=after.guild.system_channel,
                    role_event="added",
                    extra={"role_id": str(role_id)},
                )
            )
        for role_id in before_ids - after_ids:
            await self._dispatch(
                WorkflowContext(
                    guild=after.guild,
                    trigger_type="role_update",
                    member=after,
                    channel=after.guild.system_channel,
                    role_event="removed",
                    extra={"role_id": str(role_id)},
                )
            )

    @Cog.listener()
    async def on_safety_alert(
        self, guild: discord.Guild, alert: dict[str, Any]
    ) -> None:
        """Custom event dispatched by cogs_hidden.safety_hooks."""
        await self._dispatch(
            WorkflowContext(
                guild=guild,
                trigger_type="safety_alert",
                member=guild.get_member(int(alert.get("user_id", 0))),
                channel=guild.system_channel,
                alert=alert,
                extra=alert,
            )
        )

    # ── scheduled workflows ───────────────────────────────────────────────────

    @tasks.loop(minutes=1)
    async def _scheduled_workflows(self) -> None:
        if self.bot.db is not None:
            guild_ids = await self.bot.db.fetch(
                "SELECT DISTINCT guild_id FROM workflows "
                "WHERE enabled=TRUE AND trigger_type='schedule'"
            )
            for row in guild_ids:
                await self.workflows_for(row["guild_id"])

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        for guild_id, workflows in list(self._cache.items()):
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            for workflow in workflows:
                if workflow["trigger_type"] != "schedule":
                    continue
                config = workflow["trigger_config"]
                slot: str | None = None
                if config["frequency"] == "interval":
                    minutes = config["interval_minutes"]
                    slot = str(int(now_utc.timestamp()) // (minutes * 60))
                else:
                    try:
                        local = datetime.datetime.now(datetime.timezone.utc).astimezone(
                            ZoneInfo(config["timezone"])
                        )
                    except Exception:
                        continue
                    if (
                        local.hour == config["hour"]
                        and local.minute == config["minute"]
                    ):
                        slot = local.strftime("%Y-%m-%d")
                if slot is None or self._schedule_keys.get(workflow["id"]) == slot:
                    continue
                self._schedule_keys[workflow["id"]] = slot
                await self._execute(
                    workflow,
                    WorkflowContext(
                        guild=guild,
                        trigger_type="schedule",
                        channel=guild.system_channel,
                        timezone=config["timezone"],
                    ),
                )

    @_scheduled_workflows.before_loop
    async def _before_scheduled(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: Zync) -> None:
    await bot.add_cog(WorkflowRunner(bot))
