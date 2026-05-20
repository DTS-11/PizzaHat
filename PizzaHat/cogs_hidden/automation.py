from __future__ import annotations

import datetime
import time

import discord
from async_lru import alru_cache
from discord.ext import tasks

from core.bot import PizzaHat
from core.cog import Cog

# Per-user cooldown tracking: (guild_id, responder_id, user_id) → last-fired monotonic
_cooldown_map: dict[tuple[int, int, int], float] = {}


def _render(text: str, **kwargs: str) -> str:
    for k, v in kwargs.items():
        text = text.replace(f"{{{k}}}", v)
    return text


def _tvars(
    guild: discord.Guild,
    member: discord.Member | discord.User | None = None,
) -> dict[str, str]:
    out: dict[str, str] = {"guild": guild.name, "guild.id": str(guild.id)}
    if member:
        out.update(
            {
                "user": str(member),
                "user.mention": member.mention,
                "user.name": getattr(member, "name", str(member)),
                "user.id": str(member.id),
            }
        )
    return out


class AutomationEvents(Cog):
    """Background listeners and tasks for the automation system."""

    def __init__(self, bot: PizzaHat):
        self.bot = bot
        self._schedule_task.start()

    def cog_unload(self) -> None:
        self._schedule_task.cancel()

    # ── Cache management ──────────────────────────────────────────────────────

    def clear_cache(self, guild_id: int | None = None) -> None:
        # guild_id parameter is accepted but alru_cache only supports full clear
        self._fetch_responders.cache_clear()
        self._fetch_join_config.cache_clear()
        self._fetch_event_actions.cache_clear()

    @alru_cache()
    async def _fetch_responders(self, guild_id: int) -> list[dict]:
        if not self.bot.db:
            return []
        rows = await self.bot.db.fetch(
            "SELECT id, trigger_text, trigger_type, response, template_id, "
            "channel_ids, role_ids, cooldown_seconds "
            "FROM auto_responders WHERE guild_id=$1 AND enabled=TRUE ORDER BY id",
            guild_id,
        )
        return [dict(r) for r in rows]

    @alru_cache()
    async def _fetch_join_config(self, guild_id: int) -> dict | None:
        if not self.bot.db:
            return None
        row = await self.bot.db.fetchrow(
            "SELECT auto_role_ids, welcome_channel_id, welcome_message, "
            "welcome_template_id, welcome_dm, welcome_dm_template_id "
            "FROM join_automation WHERE guild_id=$1 AND enabled=TRUE",
            guild_id,
        )
        return dict(row) if row else None

    @alru_cache()
    async def _fetch_event_actions(self, guild_id: int) -> list[dict]:
        if not self.bot.db:
            return []
        rows = await self.bot.db.fetch(
            "SELECT id, event_type, actions, template_id "
            "FROM event_actions WHERE guild_id=$1 AND enabled=TRUE",
            guild_id,
        )
        return [dict(r) for r in rows]

    # ── Auto Responders ───────────────────────────────────────────────────────

    @Cog.listener()
    async def on_message(self, msg: discord.Message) -> None:
        if msg.author.bot or not msg.guild or not msg.content:
            return

        responders = await self._fetch_responders(msg.guild.id)
        if not responders:
            return

        content_lower = msg.content.lower()
        now = time.monotonic()

        for r in responders:
            trigger: str = r["trigger_text"]
            ttype: str = r["trigger_type"]

            # Trigger match
            if ttype == "exact":
                if content_lower != trigger:
                    continue
            else:
                if trigger not in content_lower:
                    continue

            # Channel restriction (Basic+)
            channel_ids: list[int] = list(r.get("channel_ids") or [])
            if channel_ids and msg.channel.id not in channel_ids:
                continue

            # Role restriction (Basic+)
            role_ids: list[int] = list(r.get("role_ids") or [])
            if role_ids:
                member_roles = {role.id for role in getattr(msg.author, "roles", [])}
                if not member_roles.intersection(set(role_ids)):
                    continue

            # Cooldown (Basic+)
            cooldown: int = r.get("cooldown_seconds") or 0
            if cooldown > 0:
                key = (msg.guild.id, r["id"], msg.author.id)
                last = _cooldown_map.get(key, 0.0)
                if now - last < cooldown:
                    continue
                _cooldown_map[key] = now

            try:
                template_id: int | None = r.get("template_id")
                if template_id:
                    from utils.embed import resolve_template

                    tvars = _tvars(msg.guild, msg.author)
                    fallback = discord.Embed(description=r["response"], color=0x456DD4)
                    em = await resolve_template(
                        self.bot.db, template_id, fallback, **tvars
                    )
                    await msg.channel.send(embed=em)
                else:
                    await msg.channel.send(r["response"])
                if self.bot.db:
                    await self.bot.db.execute(
                        "UPDATE auto_responders SET use_count = use_count + 1 WHERE id=$1",
                        r["id"],
                    )
            except discord.HTTPException:
                pass
            break  # only fire first match per message

    # ── Join Automation ───────────────────────────────────────────────────────

    @Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return

        guild = member.guild
        tvars = _tvars(guild, member)

        config = await self._fetch_join_config(guild.id)
        if config:
            for role_id in list(config.get("auto_role_ids") or []):
                role = guild.get_role(role_id)
                if role:
                    try:
                        await member.add_roles(role, reason="Join automation")
                    except discord.HTTPException:
                        pass

            ch_id = config.get("welcome_channel_id")
            msg_text = config.get("welcome_message")
            welcome_tmpl = config.get("welcome_template_id")
            if ch_id and (msg_text or welcome_tmpl):
                ch = guild.get_channel(ch_id)
                if isinstance(ch, discord.TextChannel):
                    try:
                        if welcome_tmpl:
                            from utils.embed import resolve_template

                            fallback = discord.Embed(
                                description=_render(msg_text or "", **tvars),
                                color=0x456DD4,
                            )
                            em = await resolve_template(
                                self.bot.db, welcome_tmpl, fallback, **tvars
                            )
                            await ch.send(embed=em)
                        else:
                            await ch.send(_render(msg_text, **tvars))
                    except discord.HTTPException:
                        pass

            dm_text = config.get("welcome_dm")
            dm_tmpl = config.get("welcome_dm_template_id")
            if dm_text or dm_tmpl:
                try:
                    if dm_tmpl:
                        from utils.embed import resolve_template

                        fallback = discord.Embed(
                            description=_render(dm_text or "", **tvars),
                            color=0x456DD4,
                        )
                        em = await resolve_template(
                            self.bot.db, dm_tmpl, fallback, **tvars
                        )
                        await member.send(embed=em)
                    else:
                        await member.send(_render(dm_text, **tvars))
                except discord.HTTPException:
                    pass

        await self._fire_event_actions(guild, "member_join", member=member)

    @Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if member.bot:
            return
        await self._fire_event_actions(member.guild, "member_leave", member=member)

    # ── Event Actions ─────────────────────────────────────────────────────────

    async def _fire_event_actions(
        self,
        guild: discord.Guild,
        event_type: str,
        *,
        member: discord.Member | discord.User | None = None,
    ) -> None:
        event_actions = await self._fetch_event_actions(guild.id)
        for ea in event_actions:
            if ea["event_type"] != event_type:
                continue
            for action in list(ea["actions"] or []):
                try:
                    await self._execute_action(
                        guild,
                        action["type"],
                        action.get("config", {}),
                        member=member,
                        template_id=ea.get("template_id"),
                    )
                except Exception:
                    pass
            if self.bot.db:
                await self.bot.db.execute(
                    "UPDATE event_actions SET run_count = run_count + 1 WHERE id=$1",
                    ea["id"],
                )

    async def _execute_action(
        self,
        guild: discord.Guild,
        action_type: str,
        config: dict,
        *,
        member: discord.Member | discord.User | None = None,
        template_id: int | None = None,
    ) -> None:
        tvars = _tvars(guild, member)

        if action_type == "send_message":
            ch = guild.get_channel(config.get("channel_id", 0))
            if isinstance(ch, discord.TextChannel):
                text = _render(config.get("message", ""), **tvars)
                if template_id:
                    from utils.embed import resolve_template

                    fallback = discord.Embed(description=text, color=0x456DD4)
                    em = await resolve_template(
                        self.bot.db, template_id, fallback, **tvars
                    )
                    await ch.send(embed=em)
                else:
                    await ch.send(text)

        elif action_type == "give_role":
            if isinstance(member, discord.Member):
                role = guild.get_role(config.get("role_id", 0))
                if role:
                    await member.add_roles(role, reason="Event action")

        elif action_type == "remove_role":
            if isinstance(member, discord.Member):
                role = guild.get_role(config.get("role_id", 0))
                if role:
                    await member.remove_roles(role, reason="Event action")

        elif action_type == "dm_user":
            if member:
                try:
                    text = _render(config.get("message", ""), **tvars)
                    if template_id:
                        from utils.embed import resolve_template

                        fallback = discord.Embed(description=text, color=0x456DD4)
                        em = await resolve_template(
                            self.bot.db, template_id, fallback, **tvars
                        )
                        await member.send(embed=em)
                    else:
                        await member.send(text)
                except discord.HTTPException:
                    pass

        elif action_type == "log":
            ch = guild.get_channel(config.get("channel_id", 0))
            if isinstance(ch, discord.TextChannel):
                text = _render(
                    config.get("message", "{user} triggered an event."), **tvars
                )
                fallback = discord.Embed(
                    description=text,
                    color=0x456DD4,
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                )
                if member:
                    fallback.set_author(
                        name=str(member), icon_url=member.display_avatar.url
                    )
                if template_id:
                    from utils.embed import resolve_template

                    em = await resolve_template(
                        self.bot.db, template_id, fallback, **tvars
                    )
                else:
                    em = fallback
                await self.bot.send_log(ch, embed=em)

    # ── External dispatch hooks ───────────────────────────────────────────────
    # Other cogs can call bot.dispatch("automation_event", guild, event_type, member=...)
    # to trigger event actions programmatically (e.g. from tickets/mod cogs).

    @Cog.listener()
    async def on_automation_event(
        self,
        guild: discord.Guild,
        event_type: str,
        member: discord.Member | discord.User | None = None,
    ) -> None:
        await self._fire_event_actions(guild, event_type, member=member)

    # ── Scheduled Messages ────────────────────────────────────────────────────

    @tasks.loop(minutes=1)
    async def _schedule_task(self) -> None:
        if not self.bot.db:
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        rows = await self.bot.db.fetch(
            "SELECT id, guild_id, channel_id, message, schedule_type, interval_type, template_id "
            "FROM scheduled_messages WHERE enabled=TRUE AND next_run <= $1",
            now,
        )

        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            if guild:
                ch = guild.get_channel(row["channel_id"])
                if isinstance(ch, discord.TextChannel):
                    try:
                        template_id = row.get("template_id")
                        if template_id:
                            from utils.embed import resolve_template

                            tvars = _tvars(guild)
                            fallback = discord.Embed(
                                description=row["message"], color=0x456DD4
                            )
                            em = await resolve_template(
                                self.bot.db, template_id, fallback, **tvars
                            )
                            await ch.send(embed=em)
                        else:
                            await ch.send(row["message"])
                    except discord.HTTPException:
                        pass

            if row["schedule_type"] == "recurring":
                interval = row["interval_type"]
                if interval == "daily":
                    next_run = now + datetime.timedelta(days=1)
                elif interval == "weekly":
                    next_run = now + datetime.timedelta(weeks=1)
                elif interval == "monthly":
                    next_run = now + datetime.timedelta(days=30)
                else:
                    next_run = now + datetime.timedelta(days=1)

                await self.bot.db.execute(
                    "UPDATE scheduled_messages "
                    "SET next_run=$1, last_run=$2, run_count=run_count+1 WHERE id=$3",
                    next_run,
                    now,
                    row["id"],
                )
            else:
                await self.bot.db.execute(
                    "UPDATE scheduled_messages "
                    "SET enabled=FALSE, last_run=$1, run_count=run_count+1 WHERE id=$2",
                    now,
                    row["id"],
                )

    @_schedule_task.before_loop
    async def _before_schedule(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: PizzaHat) -> None:
    await bot.add_cog(AutomationEvents(bot))
