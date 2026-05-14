from __future__ import annotations

import datetime
import re

import discord
from discord.ext import commands
from discord.ext.commands import Context

from core.bot import PizzaHat, Tier
from core.cog import Cog
from utils.custom_checks import _tier_cache, premium
from utils.embed import ctx_embed, green_embed, orange_embed, red_embed

TIER_LIMITS: dict[Tier, dict[str, int]] = {
    Tier.FREE: {"responders": 3, "schedules": 2, "join_roles": 1, "events": 2},
    Tier.BASIC: {"responders": 15, "schedules": 15, "join_roles": 5, "events": 10},
    Tier.PRO: {"responders": 100, "schedules": 50, "join_roles": 20, "events": 50},
}

EVENT_TRIGGERS: dict[str, str] = {
    "member_join": "A member joins the server",
    "member_leave": "A member leaves the server",
}

BASIC_EVENT_TRIGGERS: dict[str, str] = {
    "automod_triggered": "Automod fires on a message (Basic+)",
    "ticket_close": "A support ticket is closed (Basic+)",
}

EVENT_ACTIONS: dict[str, str] = {
    "send_message": "Send a message to a channel",
    "dm_user": "Send a DM to the user",
    "give_role": "Assign a role to the user",
    "remove_role": "Remove a role from the user",
    "log": "Embed-log an event to a channel",
}

_DELAY_RE = re.compile(r"^(\d+)(m|h|d|w)$", re.IGNORECASE)

_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _parse_delay(text: str) -> datetime.timedelta | None:
    m = _DELAY_RE.match(text.strip())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    return {
        "m": datetime.timedelta(minutes=n),
        "h": datetime.timedelta(hours=n),
        "d": datetime.timedelta(days=n),
        "w": datetime.timedelta(weeks=n),
    }.get(unit)


async def _guild_tier(bot: PizzaHat, guild_id: int) -> Tier:
    cached = _tier_cache.get(guild_id)
    if cached is not None:
        return cached
    if bot.db is None:
        return Tier.FREE
    row = await bot.db.fetchrow("SELECT tier FROM premium WHERE guild_id=$1", guild_id)
    tier = Tier(row["tier"]) if row else Tier.FREE
    _tier_cache[guild_id] = tier
    return tier


def _event_action_line(action: dict) -> str:
    t = action.get("type", "?")
    cfg = action.get("config", {})
    if t == "send_message":
        return f"send to <#{cfg.get('channel_id', '?')}>"
    if t == "give_role":
        return f"add <@&{cfg.get('role_id', '?')}>"
    if t == "remove_role":
        return f"remove <@&{cfg.get('role_id', '?')}>"
    if t == "dm_user":
        return f"DM: `{cfg.get('message', '')[:40]}`"
    if t == "log":
        return f"log in <#{cfg.get('channel_id', '?')}>"
    return t


class Automation(Cog, emoji=1504381117174644867):
    """⚡ Server automation — responders, schedules, join rules, and event actions."""

    def __init__(self, bot: PizzaHat):
        self.bot = bot

    def _bust_cache(self, guild_id: int) -> None:
        cog = self.bot.get_cog("AutomationEvents")
        if cog and hasattr(cog, "clear_cache"):
            cog.clear_cache(guild_id)  # type: ignore

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HUB
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @commands.group(name="automation", aliases=["auto"], invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automation(self, ctx: Context):
        """⚡ Automation hub — overview of all active automations."""
        if not ctx.guild or not self.bot.db:
            return

        tier = await _guild_tier(self.bot, ctx.guild.id)
        limits = TIER_LIMITS[tier]

        responder_count = (
            await self.bot.db.fetchval(
                "SELECT COUNT(*) FROM auto_responders WHERE guild_id=$1", ctx.guild.id
            )
            or 0
        )
        schedule_count = (
            await self.bot.db.fetchval(
                "SELECT COUNT(*) FROM scheduled_messages WHERE guild_id=$1 AND enabled=TRUE",
                ctx.guild.id,
            )
            or 0
        )
        join_row = await self.bot.db.fetchrow(
            "SELECT enabled FROM join_automation WHERE guild_id=$1", ctx.guild.id
        )
        event_count = (
            await self.bot.db.fetchval(
                "SELECT COUNT(*) FROM event_actions WHERE guild_id=$1 AND enabled=TRUE",
                ctx.guild.id,
            )
            or 0
        )

        join_status = (
            "✅ Active" if join_row and join_row["enabled"] else "❌ Not configured"
        )

        p = ctx.prefix
        em = await ctx_embed(
            ctx,
            title="⚡  Automation",
            description=f"**{ctx.guild.name}** · Tier: **{tier.name}**",
        )
        em.add_field(
            name="📣  Auto Responders",
            value=f"`{responder_count}` / `{limits['responders']}` configured\n`{p}automation responder`",
            inline=True,
        )
        em.add_field(
            name="🕐  Scheduled Messages",
            value=f"`{schedule_count}` / `{limits['schedules']}` active\n`{p}automation schedule`",
            inline=True,
        )
        em.add_field(
            name="👋  Join Automation",
            value=f"{join_status}\n`{p}automation join`",
            inline=True,
        )
        em.add_field(
            name="⚙️  Event Actions",
            value=f"`{event_count}` / `{limits['events']}` active\n`{p}automation event`",
            inline=True,
        )
        em.add_field(
            name="Quick start",
            value=(
                f"`{p}automation responder create <trigger> <response>`\n"
                f"`{p}automation schedule create #channel 1h <message>`\n"
                f"`{p}automation join autorole @role`\n"
                f"`{p}automation event add <name> member_join give_role @role`"
            ),
            inline=False,
        )
        await ctx.send(embed=em)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # AUTO RESPONDERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @automation.group(
        name="responder", aliases=["responders", "ar"], invoke_without_command=True
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def responder(self, ctx: Context):
        """📣 Auto responder management."""
        if not ctx.guild or not self.bot.db:
            return

        rows = await self.bot.db.fetch(
            "SELECT id, trigger_text, trigger_type, enabled, use_count, "
            "cooldown_seconds, channel_ids "
            "FROM auto_responders WHERE guild_id=$1 ORDER BY id",
            ctx.guild.id,
        )
        tier = await _guild_tier(self.bot, ctx.guild.id)
        limit = TIER_LIMITS[tier]["responders"]

        if not rows:
            return await ctx.send(
                embed=orange_embed(
                    description=(
                        f"No auto responders yet.\n\n"
                        f"**Create one:**\n"
                        f"`{ctx.prefix}automation responder create <trigger> <response>`\n\n"
                        f"Example: `{ctx.prefix}automation responder create ip play.myserver.net`"
                    )
                )
            )

        lines: list[str] = []
        for r in rows:
            status = "✅" if r["enabled"] else "❌"
            extras: list[str] = []
            if r["cooldown_seconds"]:
                extras.append(f"{r['cooldown_seconds']}s cd")
            if r["channel_ids"]:
                extras.append(f"{len(r['channel_ids'])} ch")
            extra_str = f" · {', '.join(extras)}" if extras else ""
            lines.append(
                f"{status} `#{r['id']}` **{r['trigger_text']}** "
                f"(`{r['trigger_type']}`){extra_str} · {r['use_count']} uses"
            )

        em = await ctx_embed(
            ctx,
            title="📣  Auto Responders",
            description=(
                f"**{len(rows)}** / **{limit}** · {tier.name} tier\n\n"
                + "\n".join(lines)
            ),
        )
        await ctx.send(embed=em)

    @responder.command(name="create", aliases=["add"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def responder_create(self, ctx: Context, trigger: str, *, response: str):
        """Create a new auto responder. Wrap multi-word triggers in quotes."""
        if not ctx.guild or not self.bot.db:
            return

        tier = await _guild_tier(self.bot, ctx.guild.id)
        limit = TIER_LIMITS[tier]["responders"]
        count = (
            await self.bot.db.fetchval(
                "SELECT COUNT(*) FROM auto_responders WHERE guild_id=$1", ctx.guild.id
            )
            or 0
        )

        if count >= limit:
            return await ctx.send(
                embed=red_embed(
                    description=(
                        f"{self.bot.no} **{tier.name}** tier limit reached "
                        f"(**{limit}** responders).\n"
                        f"[Upgrade to unlock more](https://pizzahat.vercel.app/premium)"
                    )
                )
            )

        trigger_lower = trigger.lower()
        dupe = await self.bot.db.fetchval(
            "SELECT id FROM auto_responders WHERE guild_id=$1 AND trigger_text=$2",
            ctx.guild.id,
            trigger_lower,
        )
        if dupe:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} A responder for `{trigger}` already exists (`#{dupe}`)."
                )
            )

        row = await self.bot.db.fetchrow(
            "INSERT INTO auto_responders (guild_id, trigger_text, response, created_by) "
            "VALUES ($1,$2,$3,$4) RETURNING id",
            ctx.guild.id,
            trigger_lower,
            response,
            ctx.author.id,
        )
        self._bust_cache(ctx.guild.id)
        await ctx.send(
            embed=green_embed(
                description=(
                    f"{self.bot.yes} Responder `#{row['id']}` created!\n"
                    f"**Trigger:** `{trigger}`\n"
                    f"**Response:** {response[:120]}"
                )
            )
        )

    @responder.command(name="delete", aliases=["remove", "del"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def responder_delete(self, ctx: Context, responder_id: int):
        """Delete an auto responder."""
        if not ctx.guild or not self.bot.db:
            return

        row = await self.bot.db.fetchrow(
            "DELETE FROM auto_responders WHERE id=$1 AND guild_id=$2 RETURNING trigger_text",
            responder_id,
            ctx.guild.id,
        )
        if not row:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Responder `#{responder_id}` not found."
                )
            )
        self._bust_cache(ctx.guild.id)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Responder `#{responder_id}` (`{row['trigger_text']}`) deleted."
            )
        )

    @responder.command(name="toggle", aliases=["enable", "disable"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def responder_toggle(self, ctx: Context, responder_id: int):
        """Toggle a responder on or off."""
        if not ctx.guild or not self.bot.db:
            return

        row = await self.bot.db.fetchrow(
            "UPDATE auto_responders SET enabled = NOT enabled "
            "WHERE id=$1 AND guild_id=$2 RETURNING trigger_text, enabled",
            responder_id,
            ctx.guild.id,
        )
        if not row:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Responder `#{responder_id}` not found."
                )
            )
        self._bust_cache(ctx.guild.id)
        status = "✅ enabled" if row["enabled"] else "❌ disabled"
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Responder `#{responder_id}` (`{row['trigger_text']}`) {status}."
            )
        )

    @responder.command(name="cooldown")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @premium(tier=Tier.BASIC)
    async def responder_cooldown(self, ctx: Context, responder_id: int, seconds: int):
        """Set a per-user cooldown on a responder in seconds. Use 0 to disable. (Basic+)"""
        if not ctx.guild or not self.bot.db:
            return

        if seconds < 0:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Cooldown must be `0` or a positive number of seconds."
                )
            )

        row = await self.bot.db.fetchrow(
            "UPDATE auto_responders SET cooldown_seconds=$1 "
            "WHERE id=$2 AND guild_id=$3 RETURNING trigger_text",
            seconds,
            responder_id,
            ctx.guild.id,
        )
        if not row:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Responder `#{responder_id}` not found."
                )
            )
        self._bust_cache(ctx.guild.id)
        msg = (
            f"Cooldown for `{row['trigger_text']}` set to `{seconds}s`."
            if seconds
            else f"Cooldown removed from `{row['trigger_text']}`."
        )
        await ctx.send(embed=green_embed(description=f"{self.bot.yes} {msg}"))

    @responder.command(name="channel")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @premium(tier=Tier.BASIC)
    async def responder_channel(
        self, ctx: Context, responder_id: int, channel: discord.TextChannel
    ):
        """Toggle a channel restriction on a responder (Basic+). Run again to remove."""
        if not ctx.guild or not self.bot.db:
            return

        row = await self.bot.db.fetchrow(
            "SELECT channel_ids, trigger_text FROM auto_responders WHERE id=$1 AND guild_id=$2",
            responder_id,
            ctx.guild.id,
        )
        if not row:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Responder `#{responder_id}` not found."
                )
            )

        ids: list[int] = list(row["channel_ids"] or [])
        if channel.id in ids:
            ids.remove(channel.id)
            action = f"removed {channel.mention} from"
        else:
            ids.append(channel.id)
            action = f"added {channel.mention} to"

        await self.bot.db.execute(
            "UPDATE auto_responders SET channel_ids=$1 WHERE id=$2",
            ids,
            responder_id,
        )
        self._bust_cache(ctx.guild.id)
        ch_list = ", ".join(f"<#{c}>" for c in ids) if ids else "all channels"
        await ctx.send(
            embed=green_embed(
                description=(
                    f"{self.bot.yes} {action.capitalize()} responder `#{responder_id}` restrictions.\n"
                    f"Active in: {ch_list}"
                )
            )
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SCHEDULED MESSAGES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @automation.group(
        name="schedule", aliases=["schedules", "sched"], invoke_without_command=True
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def schedule(self, ctx: Context):
        """🕐 Scheduled message management."""
        if not ctx.guild or not self.bot.db:
            return

        rows = await self.bot.db.fetch(
            "SELECT id, channel_id, message, schedule_type, interval_type, "
            "next_run, enabled, run_count "
            "FROM scheduled_messages WHERE guild_id=$1 ORDER BY next_run",
            ctx.guild.id,
        )
        tier = await _guild_tier(self.bot, ctx.guild.id)
        limit = TIER_LIMITS[tier]["schedules"]
        p = ctx.prefix

        if not rows:
            return await ctx.send(
                embed=orange_embed(
                    description=(
                        f"No scheduled messages yet.\n\n"
                        f"**One-time:** `{p}automation schedule create #channel 1h <message>`\n"
                        f"**Daily (Basic+):** `{p}automation schedule daily #channel 09:00 <message>`\n"
                        f"**Weekly (Basic+):** `{p}automation schedule weekly #channel monday 09:00 <message>`"
                    )
                )
            )

        active = sum(1 for r in rows if r["enabled"])
        lines: list[str] = []
        for r in rows:
            status = "✅" if r["enabled"] else "❌"
            ch = f"<#{r['channel_id']}>"
            stype = r["interval_type"] or "once"
            next_run: datetime.datetime = r["next_run"]
            if next_run.tzinfo is None:
                next_run = next_run.replace(tzinfo=datetime.timezone.utc)
            ts = discord.utils.format_dt(next_run, "R")
            preview = r["message"][:50].replace("\n", " ")
            lines.append(
                f"{status} `#{r['id']}` {ch} · **{stype}** · next {ts} · {r['run_count']} sent\n"
                f"   `{preview}`"
            )

        em = await ctx_embed(
            ctx,
            title="🕐  Scheduled Messages",
            description=f"**{active}** / **{limit}** active · {tier.name}\n\n"
            + "\n".join(lines),
        )
        await ctx.send(embed=em)

    @schedule.command(name="create", aliases=["add"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def schedule_create(
        self,
        ctx: Context,
        channel: discord.TextChannel,
        delay: str,
        *,
        message: str,
    ):
        """Schedule a one-time message. Delay examples: 10m, 2h, 1d, 1w."""
        if not ctx.guild or not self.bot.db:
            return

        tier = await _guild_tier(self.bot, ctx.guild.id)
        limit = TIER_LIMITS[tier]["schedules"]
        count = (
            await self.bot.db.fetchval(
                "SELECT COUNT(*) FROM scheduled_messages WHERE guild_id=$1 AND enabled=TRUE",
                ctx.guild.id,
            )
            or 0
        )
        if count >= limit:
            return await ctx.send(
                embed=red_embed(
                    description=(
                        f"{self.bot.no} **{tier.name}** limit reached (**{limit}** active schedules).\n"
                        f"[Upgrade to unlock more](https://pizzahat.vercel.app/premium)"
                    )
                )
            )

        td = _parse_delay(delay)
        if td is None:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Invalid delay `{delay}`. Use `10m`, `2h`, `1d`, or `1w`."
                )
            )

        next_run = datetime.datetime.now(datetime.timezone.utc) + td
        row = await self.bot.db.fetchrow(
            "INSERT INTO scheduled_messages "
            "(guild_id, channel_id, message, schedule_type, next_run, created_by) "
            "VALUES ($1,$2,$3,'once',$4,$5) RETURNING id",
            ctx.guild.id,
            channel.id,
            message,
            next_run,
            ctx.author.id,
        )
        await ctx.send(
            embed=green_embed(
                description=(
                    f"{self.bot.yes} Message `#{row['id']}` scheduled "
                    f"for {discord.utils.format_dt(next_run, 'F')}!\n"
                    f"Channel: {channel.mention} · Preview: `{message[:80]}`"
                )
            )
        )

    @schedule.command(name="daily")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @premium(tier=Tier.BASIC)
    async def schedule_daily(
        self,
        ctx: Context,
        channel: discord.TextChannel,
        time_str: str,
        *,
        message: str,
    ):
        """Schedule a daily recurring message at HH:MM UTC. (Basic+)"""
        if not ctx.guild or not self.bot.db:
            return

        try:
            t = datetime.time.fromisoformat(time_str)
        except ValueError:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Invalid time `{time_str}`. Use 24h HH:MM format (e.g. `09:00`)."
                )
            )

        tier = await _guild_tier(self.bot, ctx.guild.id)
        limit = TIER_LIMITS[tier]["schedules"]
        count = (
            await self.bot.db.fetchval(
                "SELECT COUNT(*) FROM scheduled_messages WHERE guild_id=$1 AND enabled=TRUE",
                ctx.guild.id,
            )
            or 0
        )
        if count >= limit:
            return await ctx.send(
                embed=red_embed(
                    description=(
                        f"{self.bot.no} **{tier.name}** limit reached (**{limit}** active schedules).\n"
                        f"[Upgrade to unlock more](https://pizzahat.vercel.app/premium)"
                    )
                )
            )

        now = datetime.datetime.now(datetime.timezone.utc)
        next_run = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += datetime.timedelta(days=1)

        row = await self.bot.db.fetchrow(
            "INSERT INTO scheduled_messages "
            "(guild_id, channel_id, message, schedule_type, interval_type, next_run, created_by) "
            "VALUES ($1,$2,$3,'recurring','daily',$4,$5) RETURNING id",
            ctx.guild.id,
            channel.id,
            message,
            next_run,
            ctx.author.id,
        )
        await ctx.send(
            embed=green_embed(
                description=(
                    f"{self.bot.yes} Daily message `#{row['id']}` set for `{time_str} UTC` every day!\n"
                    f"Channel: {channel.mention} · First run: {discord.utils.format_dt(next_run, 'R')}"
                )
            )
        )

    @schedule.command(name="weekly")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @premium(tier=Tier.BASIC)
    async def schedule_weekly(
        self,
        ctx: Context,
        channel: discord.TextChannel,
        weekday: str,
        time_str: str,
        *,
        message: str,
    ):
        """Schedule a weekly recurring message. Example: weekly #ch monday 09:00 <message> (Basic+)"""
        if not ctx.guild or not self.bot.db:
            return

        day_num = _WEEKDAYS.get(weekday.lower())
        if day_num is None:
            return await ctx.send(
                embed=red_embed(
                    description=(
                        f"{self.bot.no} Unknown weekday `{weekday}`.\n"
                        f"Valid: `monday` `tuesday` `wednesday` `thursday` `friday` `saturday` `sunday`"
                    )
                )
            )

        try:
            t = datetime.time.fromisoformat(time_str)
        except ValueError:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Invalid time `{time_str}`. Use HH:MM (e.g. `09:00`)."
                )
            )

        tier = await _guild_tier(self.bot, ctx.guild.id)
        limit = TIER_LIMITS[tier]["schedules"]
        count = (
            await self.bot.db.fetchval(
                "SELECT COUNT(*) FROM scheduled_messages WHERE guild_id=$1 AND enabled=TRUE",
                ctx.guild.id,
            )
            or 0
        )
        if count >= limit:
            return await ctx.send(
                embed=red_embed(
                    description=(
                        f"{self.bot.no} **{tier.name}** limit reached (**{limit}** active schedules).\n"
                        f"[Upgrade to unlock more](https://pizzahat.vercel.app/premium)"
                    )
                )
            )

        now = datetime.datetime.now(datetime.timezone.utc)
        days_ahead = (day_num - now.weekday()) % 7
        next_run = (now + datetime.timedelta(days=days_ahead)).replace(
            hour=t.hour, minute=t.minute, second=0, microsecond=0
        )
        if next_run <= now:
            next_run += datetime.timedelta(weeks=1)

        row = await self.bot.db.fetchrow(
            "INSERT INTO scheduled_messages "
            "(guild_id, channel_id, message, schedule_type, interval_type, next_run, created_by) "
            "VALUES ($1,$2,$3,'recurring','weekly',$4,$5) RETURNING id",
            ctx.guild.id,
            channel.id,
            message,
            next_run,
            ctx.author.id,
        )
        await ctx.send(
            embed=green_embed(
                description=(
                    f"{self.bot.yes} Weekly message `#{row['id']}` set for every "
                    f"**{weekday.capitalize()}** at `{time_str} UTC`!\n"
                    f"Channel: {channel.mention} · First run: {discord.utils.format_dt(next_run, 'R')}"
                )
            )
        )

    @schedule.command(name="delete", aliases=["remove", "del"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def schedule_delete(self, ctx: Context, schedule_id: int):
        """Delete a scheduled message."""
        if not ctx.guild or not self.bot.db:
            return

        row = await self.bot.db.fetchrow(
            "DELETE FROM scheduled_messages WHERE id=$1 AND guild_id=$2 RETURNING message",
            schedule_id,
            ctx.guild.id,
        )
        if not row:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Schedule `#{schedule_id}` not found."
                )
            )
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Schedule `#{schedule_id}` deleted."
            )
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # JOIN AUTOMATION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @automation.group(name="join", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def join_group(self, ctx: Context):
        """👋 Join automation configuration."""
        if not ctx.guild or not self.bot.db:
            return

        row = await self.bot.db.fetchrow(
            "SELECT * FROM join_automation WHERE guild_id=$1", ctx.guild.id
        )
        p = ctx.prefix

        if not row:
            return await ctx.send(
                embed=orange_embed(
                    description=(
                        f"Join automation is not configured yet.\n\n"
                        f"`{p}automation join autorole @role` — auto-assign a role on join\n"
                        f"`{p}automation join welcome #channel` — set welcome channel\n"
                        f"`{p}automation join message <text>` — set welcome message\n"
                        f"`{p}automation join dm <text>` — send a DM to new members\n\n"
                        f"Template vars: `{{user}}` `{{user.mention}}` `{{user.name}}` `{{user.id}}` `{{guild}}`"
                    )
                )
            )

        status = "✅ Active" if row["enabled"] else "❌ Disabled"
        role_ids: list[int] = list(row["auto_role_ids"] or [])
        roles_str = " ".join(f"<@&{r}>" for r in role_ids) if role_ids else "None"
        welcome_ch = (
            f"<#{row['welcome_channel_id']}>"
            if row["welcome_channel_id"]
            else "Not set"
        )
        welcome_msg = row["welcome_message"] or "Not set"
        welcome_dm = row["welcome_dm"] or "Not set"

        em = await ctx_embed(ctx, title="👋  Join Automation", description=status)
        em.add_field(name="Auto Roles", value=roles_str, inline=False)
        em.add_field(name="Welcome Channel", value=welcome_ch, inline=True)
        em.add_field(
            name="Welcome Message",
            value=f"`{welcome_msg[:100]}`" if welcome_msg != "Not set" else "Not set",
            inline=False,
        )
        em.add_field(
            name="Welcome DM",
            value=f"`{welcome_dm[:100]}`" if welcome_dm != "Not set" else "Not set",
            inline=False,
        )
        em.add_field(
            name="Variables",
            value="`{user}` `{user.mention}` `{user.name}` `{user.id}` `{guild}`",
            inline=False,
        )
        await ctx.send(embed=em)

    @join_group.command(name="autorole")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def join_autorole(self, ctx: Context, role: discord.Role):
        """Add or remove an auto-assign role. Run again to toggle it off."""
        if not ctx.guild or not self.bot.db:
            return

        tier = await _guild_tier(self.bot, ctx.guild.id)
        limit = TIER_LIMITS[tier]["join_roles"]

        row = await self.bot.db.fetchrow(
            "SELECT auto_role_ids FROM join_automation WHERE guild_id=$1", ctx.guild.id
        )
        role_ids: list[int] = list(row["auto_role_ids"] or []) if row else []

        if role.id in role_ids:
            role_ids.remove(role.id)
            verb = f"Removed {role.mention} from auto-roles."
        else:
            if len(role_ids) >= limit:
                return await ctx.send(
                    embed=red_embed(
                        description=(
                            f"{self.bot.no} **{tier.name}** limit reached (**{limit}** auto-roles).\n"
                            f"[Upgrade to unlock more](https://pizzahat.vercel.app/premium)"
                        )
                    )
                )
            role_ids.append(role.id)
            verb = f"Added {role.mention} to auto-roles."

        await self.bot.db.execute(
            "INSERT INTO join_automation (guild_id, auto_role_ids) VALUES ($1,$2) "
            "ON CONFLICT (guild_id) DO UPDATE SET auto_role_ids=$2",
            ctx.guild.id,
            role_ids,
        )
        self._bust_cache(ctx.guild.id)
        await ctx.send(embed=green_embed(description=f"{self.bot.yes} {verb}"))

    @join_group.command(name="welcome")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def join_welcome(self, ctx: Context, channel: discord.TextChannel):
        """Set the welcome message channel. Use with `automation join message`."""
        if not ctx.guild or not self.bot.db:
            return

        await self.bot.db.execute(
            "INSERT INTO join_automation (guild_id, welcome_channel_id) VALUES ($1,$2) "
            "ON CONFLICT (guild_id) DO UPDATE SET welcome_channel_id=$2",
            ctx.guild.id,
            channel.id,
        )
        self._bust_cache(ctx.guild.id)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Welcome channel set to {channel.mention}."
            )
        )

    @join_group.command(name="message", aliases=["msg"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def join_message(self, ctx: Context, *, message: str):
        """Set the welcome message text. Supports {user}, {user.mention}, {guild}."""
        if not ctx.guild or not self.bot.db:
            return

        await self.bot.db.execute(
            "INSERT INTO join_automation (guild_id, welcome_message) VALUES ($1,$2) "
            "ON CONFLICT (guild_id) DO UPDATE SET welcome_message=$2",
            ctx.guild.id,
            message,
        )
        self._bust_cache(ctx.guild.id)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Welcome message set!\n`{message[:200]}`"
            )
        )

    @join_group.command(name="dm")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def join_dm(self, ctx: Context, *, message: str):
        """Set the DM message sent to every new member. Supports template vars."""
        if not ctx.guild or not self.bot.db:
            return

        await self.bot.db.execute(
            "INSERT INTO join_automation (guild_id, welcome_dm) VALUES ($1,$2) "
            "ON CONFLICT (guild_id) DO UPDATE SET welcome_dm=$2",
            ctx.guild.id,
            message,
        )
        self._bust_cache(ctx.guild.id)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Welcome DM set!\n`{message[:200]}`"
            )
        )

    @join_group.command(name="enable")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def join_enable(self, ctx: Context):
        """Re-enable join automation."""
        if not ctx.guild or not self.bot.db:
            return

        result = await self.bot.db.execute(
            "UPDATE join_automation SET enabled=TRUE WHERE guild_id=$1", ctx.guild.id
        )
        if result == "UPDATE 0":
            return await ctx.send(
                embed=orange_embed(description="No join automation is configured yet.")
            )
        self._bust_cache(ctx.guild.id)
        await ctx.send(
            embed=green_embed(description=f"{self.bot.yes} Join automation enabled.")
        )

    @join_group.command(name="disable")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def join_disable(self, ctx: Context):
        """Pause all join automation without deleting the configuration."""
        if not ctx.guild or not self.bot.db:
            return

        result = await self.bot.db.execute(
            "UPDATE join_automation SET enabled=FALSE WHERE guild_id=$1", ctx.guild.id
        )
        if result == "UPDATE 0":
            return await ctx.send(
                embed=orange_embed(description="No join automation is configured yet.")
            )
        self._bust_cache(ctx.guild.id)
        await ctx.send(
            embed=green_embed(description=f"{self.bot.yes} Join automation paused.")
        )

    @join_group.command(name="clear")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def join_clear(self, ctx: Context):
        """Remove all join automation configuration for this server."""
        if not ctx.guild or not self.bot.db:
            return

        await self.bot.db.execute(
            "DELETE FROM join_automation WHERE guild_id=$1", ctx.guild.id
        )
        self._bust_cache(ctx.guild.id)
        await ctx.send(
            embed=green_embed(description=f"{self.bot.yes} Join automation cleared.")
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # EVENT ACTIONS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @automation.group(name="event", aliases=["events"], invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def event_group(self, ctx: Context):
        """⚙️ Event action management."""
        if not ctx.guild or not self.bot.db:
            return

        rows = await self.bot.db.fetch(
            "SELECT id, name, event_type, enabled, run_count, "
            "COALESCE(jsonb_array_length(actions), 0) AS action_count "
            "FROM event_actions WHERE guild_id=$1 ORDER BY id",
            ctx.guild.id,
        )
        tier = await _guild_tier(self.bot, ctx.guild.id)
        limit = TIER_LIMITS[tier]["events"]
        p = ctx.prefix

        all_triggers = {**EVENT_TRIGGERS, **BASIC_EVENT_TRIGGERS}

        if not rows:
            trigger_list = "\n".join(f"`{t}` — {d}" for t, d in EVENT_TRIGGERS.items())
            return await ctx.send(
                embed=orange_embed(
                    description=(
                        f"No event actions yet.\n\n"
                        f"**Example:**\n"
                        f'`{p}automation event add "Welcome Role" member_join give_role @Members`\n'
                        f'`{p}automation event add "Goodbye Log" member_leave send_message #logs Goodbye {{user}}!`\n\n'
                        f"**Triggers:**\n{trigger_list}"
                    )
                )
            )

        lines = [
            f"{'✅' if r['enabled'] else '❌'} `#{r['id']}` **{r['name']}** "
            f"· `{r['event_type']}` · {r['action_count']} action(s) · {r['run_count']} runs"
            for r in rows
        ]
        em = await ctx_embed(
            ctx,
            title="⚙️  Event Actions",
            description=f"**{len(rows)}** / **{limit}** · {tier.name}\n\n"
            + "\n".join(lines),
        )
        await ctx.send(embed=em)

    @event_group.command(name="add", aliases=["create"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def event_add(
        self,
        ctx: Context,
        name: str,
        event_type: str,
        action_type: str,
        *,
        args: str = "",
    ):
        """Add an event action. Example: event add "Log Join" member_join send_message #logs {user.mention} joined!"""
        if not ctx.guild or not self.bot.db:
            return

        tier = await _guild_tier(self.bot, ctx.guild.id)
        limit = TIER_LIMITS[tier]["events"]
        count = (
            await self.bot.db.fetchval(
                "SELECT COUNT(*) FROM event_actions WHERE guild_id=$1", ctx.guild.id
            )
            or 0
        )
        if count >= limit:
            return await ctx.send(
                embed=red_embed(
                    description=(
                        f"{self.bot.no} **{tier.name}** limit reached (**{limit}** event actions).\n"
                        f"[Upgrade to unlock more](https://pizzahat.vercel.app/premium)"
                    )
                )
            )

        event_type = event_type.lower()
        all_triggers = {**EVENT_TRIGGERS, **BASIC_EVENT_TRIGGERS}
        if event_type not in all_triggers:
            return await ctx.send(
                embed=red_embed(
                    description=(
                        f"{self.bot.no} Unknown trigger `{event_type}`.\n"
                        f"Available: {', '.join(f'`{t}`' for t in EVENT_TRIGGERS)}"
                    )
                )
            )

        if event_type in BASIC_EVENT_TRIGGERS and tier < Tier.BASIC:
            return await ctx.send(
                embed=red_embed(
                    description=(
                        f"{self.bot.no} Trigger `{event_type}` requires **Basic** tier.\n"
                        f"[Upgrade](https://pizzahat.vercel.app/premium)"
                    )
                )
            )

        action_type = action_type.lower()
        if action_type not in EVENT_ACTIONS:
            return await ctx.send(
                embed=red_embed(
                    description=(
                        f"{self.bot.no} Unknown action `{action_type}`.\n"
                        f"Available: {', '.join(f'`{a}`' for a in EVENT_ACTIONS)}"
                    )
                )
            )

        config, error = await _parse_event_action(ctx, action_type, args)
        if error:
            return await ctx.send(embed=red_embed(description=f"{self.bot.no} {error}"))

        actions = [{"type": action_type, "config": config}]
        row = await self.bot.db.fetchrow(
            "INSERT INTO event_actions (guild_id, name, event_type, actions, created_by) "
            "VALUES ($1,$2,$3,$4,$5) RETURNING id",
            ctx.guild.id,
            name,
            event_type,
            actions,
            ctx.author.id,
        )
        self._bust_cache(ctx.guild.id)
        await ctx.send(
            embed=green_embed(
                description=(
                    f"{self.bot.yes} Event action `#{row['id']}` **{name}** created!\n"
                    f"**When** `{event_type}` → **{action_type}**"
                )
            )
        )

    @event_group.command(name="show")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def event_show(self, ctx: Context, event_id: int):
        """Show full details of an event action."""
        if not ctx.guild or not self.bot.db:
            return

        row = await self.bot.db.fetchrow(
            "SELECT * FROM event_actions WHERE id=$1 AND guild_id=$2",
            event_id,
            ctx.guild.id,
        )
        if not row:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Event action `#{event_id}` not found."
                )
            )

        actions: list[dict] = list(row["actions"] or [])
        action_lines = [
            f"`{i}.` {_event_action_line(a)}" for i, a in enumerate(actions, 1)
        ]

        em = await ctx_embed(ctx, title=f"⚙️  Event Action: {row['name']}")
        em.add_field(
            name="Status",
            value="✅ Enabled" if row["enabled"] else "❌ Disabled",
            inline=True,
        )
        em.add_field(name="Trigger", value=f"`{row['event_type']}`", inline=True)
        em.add_field(name="Total runs", value=str(row["run_count"]), inline=True)
        em.add_field(
            name=f"Actions ({len(actions)})",
            value="\n".join(action_lines) or "None",
            inline=False,
        )
        await ctx.send(embed=em)

    @event_group.command(name="delete", aliases=["remove", "del"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def event_delete(self, ctx: Context, event_id: int):
        """Delete an event action."""
        if not ctx.guild or not self.bot.db:
            return

        row = await self.bot.db.fetchrow(
            "DELETE FROM event_actions WHERE id=$1 AND guild_id=$2 RETURNING name",
            event_id,
            ctx.guild.id,
        )
        if not row:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Event action `#{event_id}` not found."
                )
            )
        self._bust_cache(ctx.guild.id)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Event action `#{event_id}` (`{row['name']}`) deleted."
            )
        )

    @event_group.command(name="toggle", aliases=["enable", "disable"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def event_toggle(self, ctx: Context, event_id: int):
        """Toggle an event action on or off."""
        if not ctx.guild or not self.bot.db:
            return

        row = await self.bot.db.fetchrow(
            "UPDATE event_actions SET enabled = NOT enabled "
            "WHERE id=$1 AND guild_id=$2 RETURNING name, enabled",
            event_id,
            ctx.guild.id,
        )
        if not row:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Event action `#{event_id}` not found."
                )
            )
        self._bust_cache(ctx.guild.id)
        status = "✅ enabled" if row["enabled"] else "❌ disabled"
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Event action `#{event_id}` (`{row['name']}`) {status}."
            )
        )


async def _parse_event_action(
    ctx: Context, action_type: str, args: str
) -> tuple[dict, str | None]:
    args = args.strip()

    if action_type == "send_message":
        parts = args.split(" ", 1)
        if len(parts) < 2 or not parts[1].strip():
            return {}, "Usage: `send_message #channel <message>`"
        raw = parts[0].strip().lstrip("<#").rstrip(">")
        try:
            ch = ctx.guild.get_channel(int(raw))  # type: ignore
            if not isinstance(ch, discord.TextChannel):
                raise ValueError
        except (ValueError, TypeError):
            return {}, f"Channel `{parts[0]}` not found."
        return {"channel_id": ch.id, "message": parts[1].strip()}, None

    if action_type in ("give_role", "remove_role"):
        if not args:
            return {}, f"Usage: `{action_type} @role`"
        raw = args.strip().lstrip("<@&").rstrip(">")
        try:
            role = ctx.guild.get_role(int(raw))  # type: ignore
            if not role:
                raise ValueError
        except (ValueError, TypeError):
            return {}, f"Role `{args}` not found."
        return {"role_id": role.id}, None

    if action_type == "dm_user":
        if not args:
            return {}, "Usage: `dm_user <message>`"
        return {"message": args}, None

    if action_type == "log":
        parts = args.split(" ", 1)
        if not parts[0]:
            return {}, "Usage: `log #channel [message]`"
        raw = parts[0].strip().lstrip("<#").rstrip(">")
        try:
            ch = ctx.guild.get_channel(int(raw))  # type: ignore
            if not isinstance(ch, discord.TextChannel):
                raise ValueError
        except (ValueError, TypeError):
            return {}, f"Channel `{parts[0]}` not found."
        msg = parts[1].strip() if len(parts) > 1 else "{user} triggered an event."
        return {"channel_id": ch.id, "message": msg}, None

    return {}, f"Unknown action `{action_type}`."


async def setup(bot: PizzaHat) -> None:
    await bot.add_cog(Automation(bot))
