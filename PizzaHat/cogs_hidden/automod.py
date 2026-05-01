from __future__ import annotations

import asyncio
import datetime
import re
import time
from collections import defaultdict
from difflib import SequenceMatcher
from urllib import parse

import discord
import emojis
from async_lru import alru_cache

from core.bot import PizzaHat
from core.cog import Cog
from utils.bad_words import BANNED_WORDS
from utils.embed import green_embed, red_embed

SCAM_PATTERNS = re.compile(
    r"(discord[\-\.]gift|nitro[\-\.]free|free[\-\.]nitro|"
    r"discord[\-\.]com[\-\.]gift|steamcommunity\.ru|"
    r"discordapp\.io|discord[\-\.]giveaway)",
    re.IGNORECASE,
)
INVITE_REGEX = re.compile(
    r"((http(s|):\/\/|)(discord)(\.(gg|io|me)\/|app\.com\/invite\/)([0-z]+))"
)
ZALGO_REGEX = re.compile(r"%CC%", re.MULTILINE)
CUSTOM_EMOJI_REGEX = re.compile(r"<a?:[^:]+:\d+>")


def _has_mod_perms(m: discord.Message) -> bool:
    if not isinstance(m.author, discord.Member):
        return False
    p = m.author.guild_permissions
    return bool(
        p.kick_members
        or p.ban_members
        or p.manage_guild
        or p.administrator
        or m.author == m.guild.owner  # type: ignore
    )


def _account_age_days(member: discord.Member) -> float:
    return (
        datetime.datetime.now(datetime.timezone.utc) - member.created_at
    ).total_seconds() / 86400


class AutoModConfig(Cog):
    """AutoMod event listener and enforcement engine."""

    _spam_buckets: dict[int, dict[int, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    _join_buckets: dict[int, list[float]] = defaultdict(list)
    _raid_locked: dict[int, bool] = {}

    def __init__(self, bot: PizzaHat):
        self.bot = bot
        self._mentions = bot.allowed_mentions

    def clear_config_cache(self, guild_id: int | None = None) -> None:
        self._get_logs_channel.cache_clear()
        self._is_enabled.cache_clear()
        self._get_config.cache_clear()
        self._get_thresholds.cache_clear()

    @alru_cache()
    async def _get_logs_channel(self, guild_id: int) -> discord.TextChannel | None:
        if not self.bot.db:
            return None

        channel_id = await self.bot.db.fetchval(
            "SELECT channel_id FROM guild_logs WHERE guild_id=$1", guild_id
        )
        if not channel_id:
            return None

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return None

        ch = guild.get_channel(channel_id) or await guild.fetch_channel(channel_id)
        return ch if isinstance(ch, discord.TextChannel) else None

    @alru_cache()
    async def _is_enabled(self, guild_id: int) -> bool:
        if not self.bot.db:
            return False
        return bool(
            await self.bot.db.fetchval(
                "SELECT enabled FROM automod WHERE guild_id=$1", guild_id
            )
        )

    @alru_cache()
    async def _get_config(self, guild_id: int) -> dict:
        """
        Returns merged JSONB config. Falls back to legacy TEXT[] modules column
        and legacy warn_action / warn_threshold columns gracefully.
        """

        if not self.bot.db:
            return {}

        row = await self.bot.db.fetchrow(
            "SELECT config, modules, warn_action, warn_threshold "
            "FROM automod WHERE guild_id=$1",
            guild_id,
        )
        if not row:
            return {}

        cfg: dict = dict(row["config"]) if row["config"] else {}

        if not cfg and row["modules"]:
            for mod in row["modules"]:
                cfg[mod] = {"enabled": True}

        if "thresholds" not in cfg:
            wa = row["warn_action"]
            wt = row["warn_threshold"]
            if wa and wa != "none" and wt and wt > 0:
                cfg["thresholds"] = [{"warns": wt, "action": wa}]

        return cfg

    @alru_cache()
    async def _get_thresholds(self, guild_id: int) -> list[dict]:
        cfg = await self._get_config(guild_id)
        return sorted(cfg.get("thresholds", []), key=lambda t: t["warns"])

    def _mod_enabled(self, cfg: dict, module: str) -> bool:
        val = cfg.get(module, {})
        if isinstance(val, bool):
            return val
        if isinstance(val, dict):
            return bool(val.get("enabled", False))
        return False

    def _mod_cfg(self, cfg: dict, module: str) -> dict:
        val = cfg.get(module, {})
        return val if isinstance(val, dict) else {}

    async def _log(
        self,
        guild_id: int,
        *,
        title: str,
        description: str,
        color: discord.Color = discord.Color.orange(),
        member: discord.Member | discord.User | None = None,
        fields: list[tuple[str, str, bool]] | None = None,
        warn_count: int | None = None,
    ) -> None:
        ch = await self._get_logs_channel(guild_id)
        if not ch:
            return

        em = discord.Embed(
            title=f"<:danger:1268855303768903733>  {title}",
            description=description,
            color=color,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

        if member:
            em.set_author(name=str(member), icon_url=member.display_avatar.url)
            if isinstance(member, discord.Member):
                age = _account_age_days(member)
                joined = (
                    (
                        datetime.datetime.now(datetime.timezone.utc) - member.joined_at
                    ).total_seconds()
                    / 86400
                    if member.joined_at
                    else 0
                )
                em.add_field(
                    name="Account",
                    value=f"Age: **{age:.0f}d**\nJoined: **{joined:.0f}d** ago\nID: `{member.id}`",
                    inline=True,
                )

        if warn_count is not None:
            em.add_field(name="Total Warns", value=f"`{warn_count}`", inline=True)

        for name, value, inline in fields or []:
            em.add_field(name=name, value=value, inline=inline)

        await self.bot.send_log(ch, embed=em)

    async def check_warn_threshold(self, user_id: int, guild_id: int) -> None:
        """
        Called after every warn (manual or automod-issued).
        Finds the highest crossed threshold and executes the configured action.
        """

        if not self.bot.db:
            return

        thresholds = await self._get_thresholds(guild_id)
        if not thresholds:
            return

        warn_count: int = (
            await self.bot.db.fetchval(
                "SELECT COUNT(*) FROM warnlogs WHERE user_id=$1 AND guild_id=$2",
                user_id,
                guild_id,
            )
            or 0
        )

        action_cfg: dict | None = None
        for t in thresholds:
            if warn_count >= t["warns"]:
                action_cfg = t

        if not action_cfg:
            return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        member = guild.get_member(user_id)
        if not member:
            return

        action = action_cfg.get("action", "none")
        warns_needed = action_cfg["warns"]
        duration_secs = action_cfg.get("duration", 3600)
        reason = f"AutoMod: {warns_needed} warn threshold — automatic {action}"

        executed = False
        try:
            if action == "timeout":
                until = discord.utils.utcnow() + datetime.timedelta(
                    seconds=duration_secs
                )
                await member.timeout(until, reason=reason)
                executed = True

            elif action == "kick":
                if guild.me.guild_permissions.kick_members:
                    await member.kick(reason=reason)
                    executed = True

            elif action == "tempban":
                unban_days = action_cfg.get("unban_days", 1)
                if guild.me.guild_permissions.ban_members:
                    await member.ban(reason=reason, delete_message_days=0)
                    executed = True

                    async def _unban():
                        await asyncio.sleep(unban_days * 86400)
                        try:
                            await guild.unban(
                                discord.Object(id=user_id),
                                reason="AutoMod: Temp-ban expired",
                            )
                        except discord.HTTPException:
                            pass

                    asyncio.create_task(_unban())

            elif action == "ban":
                if guild.me.guild_permissions.ban_members:
                    await member.ban(reason=reason, delete_message_days=0)
                    executed = True

            elif action == "role_add":
                role = guild.get_role(action_cfg.get("role_id", 0))
                if role:
                    await member.add_roles(role, reason=reason)
                    executed = True

            elif action == "role_remove":
                role = guild.get_role(action_cfg.get("role_id", 0))
                if role:
                    await member.remove_roles(role, reason=reason)
                    executed = True

        except discord.HTTPException:
            pass

        if not executed:
            return

        # DM the user
        try:
            dm_em = red_embed(
                title=f"Action taken in {guild.name}",
                description=(
                    f"You have reached **{warns_needed} warn(s)** and received an automatic "
                    f"**{action.replace('_', ' ').title()}**.\n\n"
                    f"**Reason:** {reason}"
                ),
                timestamp=True,
            )
            await member.send(embed=dm_em)
        except discord.HTTPException:
            pass

        human_action = action.replace("_", " ").title()
        await self._log(
            guild_id,
            title="Warn Threshold — Action Taken",
            description=(
                f"{member.mention} triggered the **{warns_needed}-warn threshold** "
                f"and received an automatic **{human_action}**."
            ),
            color=discord.Color.dark_red(),
            member=member,
            fields=[
                ("Action", human_action, True),
                ("Threshold", str(warns_needed), True),
                ("Total Warns", str(warn_count), True),
            ],
        )

    @Cog.listener()
    async def on_message(self, msg: discord.Message) -> None:
        if msg.author.bot or not msg.guild or not msg.content or _has_mod_perms(msg):
            return
        if not await self._is_enabled(msg.guild.id):
            return

        cfg = await self._get_config(msg.guild.id)
        overrides: dict = cfg.get("overrides", {})
        ch_override: dict = overrides.get(str(msg.channel.id), {})

        def _active(module: str) -> bool:
            """Channel override wins; fall back to global cfg."""
            if module in ch_override:
                v = ch_override[module]
                return bool(v) if isinstance(v, bool) else bool(v.get("enabled", False))
            return self._mod_enabled(cfg, module)

        # Ordered checks — first match wins and issues a warn
        checks = [
            ("banned_words", self._banned_words),
            ("scam_links", self._scam_links),
            ("all_caps", self._all_caps),
            ("message_spam", self._message_spam),
            ("invites", self._invites),
            ("mass_mentions", self._mass_mentions),
            ("emoji_spam", self._emoji_spam),
            ("zalgo_text", self._zalgo_text),
            ("newline_spam", self._newline_spam),
            ("repeated_chars", self._repeated_chars),
        ]

        for mod_name, handler in checks:
            if not _active(mod_name):
                continue
            mod_cfg = self._mod_cfg(cfg, mod_name)
            if await handler(msg, mod_cfg):
                await self._issue_automod_warn(msg, mod_name)
                return

    async def _issue_automod_warn(self, msg: discord.Message, module: str) -> None:
        """Insert an automatic warn row, log it, then check thresholds."""

        if not msg.guild or not self.bot.db:
            return

        reason = f"AutoMod: {module.replace('_', ' ').title()}"
        await self.bot.db.execute(
            "INSERT INTO warnlogs (guild_id, user_id, mod_id, reason) VALUES ($1,$2,$3,$4)",
            msg.guild.id,
            msg.author.id,
            self.bot.user.id,  # type: ignore
            reason,
        )

        warn_count: int = (
            await self.bot.db.fetchval(
                "SELECT COUNT(*) FROM warnlogs WHERE user_id=$1 AND guild_id=$2",
                msg.author.id,
                msg.guild.id,
            )
            or 0
        )

        preview = (msg.content[:300] + "…") if len(msg.content) > 300 else msg.content

        await self._log(
            msg.guild.id,
            title="AutoMod Triggered",
            description=f"**Message:**\n{discord.utils.escape_markdown(preview)}",
            color=discord.Color.orange(),
            member=msg.author,  # type: ignore
            fields=[
                ("Module", f"`{module.replace('_', ' ').title()}`", True),
                ("Channel", msg.channel.mention, True),  # type: ignore
                ("Warn Count", f"`{warn_count}`", True),
            ],
            warn_count=warn_count,
        )

        await self.check_warn_threshold(msg.author.id, msg.guild.id)

    async def _send(self, ch, text: str) -> None:
        try:
            await ch.send(text, delete_after=5, allowed_mentions=self._mentions)  # type: ignore
        except discord.HTTPException:
            pass

    async def _delete(self, msg: discord.Message) -> None:
        try:
            await msg.delete()
        except discord.HTTPException:
            pass

    async def _banned_words(self, msg: discord.Message, cfg: dict) -> bool:
        content = msg.content.lower()
        for word in BANNED_WORDS:
            if word in content:
                await self._delete(msg)
                await self._send(
                    msg.channel, f"{msg.author.mention} Watch your language."
                )
                return True
        return False

    async def _scam_links(self, msg: discord.Message, cfg: dict) -> bool:
        if SCAM_PATTERNS.search(msg.content):
            await self._delete(msg)
            await self._send(
                msg.channel,
                f"{msg.author.mention} Scam/phishing links are not allowed.",
            )
            return True
        return False

    async def _all_caps(self, msg: discord.Message, cfg: dict) -> bool:
        threshold = cfg.get("threshold", 70)
        min_length = cfg.get("min_length", 8)
        content = msg.content

        if len(content) < min_length:
            return False

        alpha = sum(1 for c in content if c.isalpha())
        if not alpha:
            return False

        if (sum(1 for c in content if c.isupper()) / alpha) * 100 >= threshold:
            await self._delete(msg)
            await self._send(
                msg.channel, f"{msg.author.mention} Please don't use excessive caps."
            )
            return True
        return False

    async def _message_spam(self, msg: discord.Message, cfg: dict) -> bool:
        threshold = cfg.get("threshold", 5)
        window = cfg.get("window_seconds", 6)

        bucket = self._spam_buckets[msg.guild.id][msg.author.id]  # type: ignore
        now = time.monotonic()
        bucket[:] = [t for t in bucket if now - t < window]
        bucket.append(now)

        if len(bucket) >= threshold:
            bucket.clear()

            def _check(m: discord.Message) -> bool:
                return m.author.id == msg.author.id

            try:
                if isinstance(
                    msg.channel,
                    (
                        discord.TextChannel,
                        discord.Thread,
                        discord.VoiceChannel,
                        discord.StageChannel,
                    ),
                ):
                    await msg.channel.purge(limit=threshold + 2, check=_check)
                    await self._send(
                        msg.channel, f"{msg.author.mention} Stop spamming."
                    )
            except discord.HTTPException:
                pass
            return True
        return False

    async def _invites(self, msg: discord.Message, cfg: dict) -> bool:
        whitelist: list[str] = cfg.get("whitelist", [])
        matches = INVITE_REGEX.findall(msg.content)
        if not matches or not msg.guild:
            return False

        for match in matches:
            code = match[-1]
            if any(code in w or w in code for w in whitelist):
                continue
            try:
                invite = await self.bot.fetch_invite(code)
            except discord.NotFound:
                continue
            if invite.guild and invite.guild.id != msg.guild.id:
                await self._delete(msg)
                await self._send(
                    msg.channel,
                    f"{msg.author.mention} External invite links are not allowed.",
                )
                return True
        return False

    async def _mass_mentions(self, msg: discord.Message, cfg: dict) -> bool:
        threshold = cfg.get("threshold", 4)
        if len(msg.mentions) + len(msg.role_mentions) >= threshold:
            await self._delete(msg)
            await self._send(msg.channel, f"{msg.author.mention} Don't spam mentions.")
            return True
        return False

    async def _emoji_spam(self, msg: discord.Message, cfg: dict) -> bool:
        threshold = cfg.get("threshold", 10)
        emoji_count = emojis.count(msg.content) + len(
            CUSTOM_EMOJI_REGEX.findall(msg.content)
        )
        if emoji_count > threshold:
            await self._delete(msg)
            await self._send(msg.channel, f"{msg.author.mention} Don't spam emojis.")
            return True
        return False

    async def _zalgo_text(self, msg: discord.Message, cfg: dict) -> bool:
        if ZALGO_REGEX.search(parse.quote(msg.content.encode("utf-8"))):
            await self._delete(msg)
            await self._send(
                msg.channel,
                f"{msg.author.mention} Zalgo/corrupted text is not allowed.",
            )
            return True
        return False

    async def _newline_spam(self, msg: discord.Message, cfg: dict) -> bool:
        threshold = cfg.get("threshold", 10)
        if msg.content.count("\n") >= threshold:
            await self._delete(msg)
            await self._send(
                msg.channel,
                f"{msg.author.mention} Excessive line breaks are not allowed.",
            )
            return True
        return False

    async def _repeated_chars(self, msg: discord.Message, cfg: dict) -> bool:
        threshold = cfg.get("threshold", 15)
        pattern = re.compile(r"(.)\1{" + str(threshold - 1) + r",}", re.UNICODE)
        if pattern.search(msg.content):
            await self._delete(msg)
            await self._send(
                msg.channel,
                f"{msg.author.mention} Please don't repeat characters excessively.",
            )
            return True
        return False

    @Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        if not await self._is_enabled(member.guild.id):
            return

        cfg = await self._get_config(member.guild.id)
        await asyncio.gather(
            self._check_username_filter(member, cfg),
            self._check_default_avatar(member, cfg),
            self._track_join_rate(member, cfg),
        )

    async def _check_username_filter(self, member: discord.Member, cfg: dict) -> None:
        if not self._mod_enabled(cfg, "username_filter"):
            return

        name = (member.display_name or member.name).lower()

        # Banned word in display name
        for word in BANNED_WORDS:
            if word in name:
                try:
                    await member.kick(reason="AutoMod: Banned word in username")
                    await self._log(
                        member.guild.id,
                        title="Username Filter — Kicked",
                        description=f"{member.mention} was kicked for having a banned word in their username.",
                        member=member,
                        color=discord.Color.red(),
                        fields=[
                            (
                                "Username",
                                discord.utils.escape_markdown(str(member)),
                                False,
                            )
                        ],
                    )
                except discord.HTTPException:
                    pass
                return

        # Staff impersonation
        mod_cfg = self._mod_cfg(cfg, "username_filter")
        if not mod_cfg.get("impersonation_check", True):
            return

        for m in member.guild.members:
            if m == member:
                continue
            if not any(
                r.permissions.kick_members or r.permissions.manage_guild
                for r in m.roles
            ):
                continue
            similarity = SequenceMatcher(
                None, member.display_name.lower(), m.display_name.lower()
            ).ratio()
            if similarity >= 0.85:
                try:
                    await member.kick(reason="AutoMod: Possible staff impersonation")
                    await self._log(
                        member.guild.id,
                        title="Impersonation Detected — Kicked",
                        description=(
                            f"{member.mention} has a suspiciously similar name to "
                            f"staff member **{discord.utils.escape_markdown(str(m))}** "
                            f"(similarity `{similarity:.0%}`)."
                        ),
                        member=member,
                        color=discord.Color.dark_red(),
                    )
                except discord.HTTPException:
                    pass
                return

    async def _check_default_avatar(self, member: discord.Member, cfg: dict) -> None:
        if not self._mod_enabled(cfg, "default_avatar"):
            return
        if member.avatar is not None:
            return

        mod_cfg = self._mod_cfg(cfg, "default_avatar")
        action = mod_cfg.get("action", "restrict")
        reason = "AutoMod: Default avatar"

        try:
            if action == "kick":
                await member.kick(reason=reason)
            elif action == "ban":
                await member.ban(reason=reason)
            else:
                if self.bot.db:
                    rid = await self.bot.db.fetchval(
                        "SELECT restricted_role FROM antialt WHERE guild_id=$1",
                        member.guild.id,
                    )
                    if rid:
                        role = member.guild.get_role(rid)
                        if role:
                            await member.add_roles(role, reason=reason)
        except discord.HTTPException:
            pass

        await self._log(
            member.guild.id,
            title="Default Avatar Detected",
            description=f"{member.mention} joined with no avatar. Action: **{action.title()}**.",
            member=member,
            color=discord.Color.gold(),
        )

    async def _track_join_rate(self, member: discord.Member, cfg: dict) -> None:
        if not self._mod_enabled(cfg, "join_rate"):
            return

        guild_id = member.guild.id
        if self._raid_locked.get(guild_id):
            return

        mod_cfg = self._mod_cfg(cfg, "join_rate")
        threshold = mod_cfg.get("threshold", 10)
        window = mod_cfg.get("window_seconds", 30)
        lockdown_minutes = mod_cfg.get("lockdown_minutes", 15)

        bucket = self._join_buckets[guild_id]
        now = time.monotonic()
        bucket[:] = [t for t in bucket if now - t < window]
        bucket.append(now)

        if len(bucket) < threshold:
            return

        self._raid_locked[guild_id] = True
        bucket.clear()
        guild = member.guild

        original_level: discord.VerificationLevel | None = None
        try:
            original_level = guild.verification_level
            await guild.edit(
                verification_level=discord.VerificationLevel.high,
                reason="AutoMod: Raid detected",
            )
        except discord.HTTPException:
            pass

        ch = await self._get_logs_channel(guild_id)
        if ch:
            em = discord.Embed(
                title="🚨  Raid Detected — Lockdown Active",
                description=(
                    f"**{threshold}+ members** joined within `{window}s`.\n\n"
                    f"Verification level raised to **High**.\n"
                    f"Lockdown lifts in `{lockdown_minutes}` minute(s)."
                ),
                color=discord.Color.dark_red(),
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
            em.set_footer(text=guild.name)
            await self.bot.send_log(ch, embed=em)

        # Schedule restore
        async def _restore() -> None:
            await asyncio.sleep(lockdown_minutes * 60)
            try:
                if original_level is not None:
                    await guild.edit(
                        verification_level=original_level,
                        reason="AutoMod: Raid lockdown expired",
                    )
                self._raid_locked[guild_id] = False
                if ch:
                    await self.bot.send_log(
                        ch,
                        embed=green_embed(
                            title="Lockdown Lifted",
                            description="Verification level has been restored to its original setting.",
                            timestamp=True,
                        ),
                    )
            except discord.HTTPException:
                pass

        asyncio.create_task(_restore())


async def setup(bot: PizzaHat) -> None:
    await bot.add_cog(AutoModConfig(bot))
