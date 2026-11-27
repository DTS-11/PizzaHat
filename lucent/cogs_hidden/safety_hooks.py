"""Safety event hooks.

Detection logic lives here; persistence, thresholds and scheduled work are
delegated to services. Every alert is dispatched as the custom ``safety_alert``
event with a structured payload for the workflow runner.
"""

from __future__ import annotations

import datetime
import re
import time
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any
from urllib import parse

import discord
import emojis

from core.bot import Lucent
from core.cog import Cog
from services import get_logs, get_moderation, get_protection, get_scheduler
from services.protection import (
    ALL_MODULES,
    CONTENT_MODULES,
    DEFAULT_ANTIALT,
    DEFAULT_THRESHOLD_SETTINGS,
    ProtectionService,
    module_defaults,
)
from utils.bad_words import BANNED_WORDS
from utils.embed import green_embed, orange_embed, red_embed


def _datetime_to_unix(t: datetime.datetime) -> int:
    current_time = datetime.datetime.fromtimestamp(time.time())
    return round(
        round(time.time()) + (current_time - t.replace(tzinfo=None)).total_seconds()
    )


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


def _setting(module: str, settings: dict[str, Any], key: str) -> Any:
    """Read a detector setting, falling back to the service-level default."""

    value = settings.get(key)
    return value if value is not None else module_defaults(module).get(key)


class AntiAltsConfig(Cog):
    """Anti-Alt enforcement listener."""

    def __init__(self, bot: Lucent):
        self.bot = bot
        self.protection: ProtectionService = get_protection(bot)
        self.logs = get_logs(bot)
        self.moderation = get_moderation(bot)
        self.scheduler = get_scheduler(bot)
        self.scheduler.start()

    async def cog_unload(self) -> None:
        """Cancel the in-memory loop; pending rows remain for reconciliation."""

        self.scheduler.stop()

    def clear_config_cache(self, guild_id: int | None = None) -> None:
        self.protection.invalidate(guild_id)
        self.logs.invalidate(guild_id)

    async def _get_logs_channel(self, guild_id: int) -> discord.TextChannel | None:
        channel_id = await self.logs.get_channel_id(guild_id)
        if not channel_id:
            return None
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return None
        try:
            channel = guild.get_channel(channel_id) or await guild.fetch_channel(
                channel_id
            )
        except (discord.Forbidden, discord.HTTPException, discord.NotFound):
            return None
        return channel if isinstance(channel, discord.TextChannel) else None

    async def _is_enabled(self, guild_id: int) -> bool:
        return await self.protection.antialt_enabled(guild_id)

    async def _get_config(self, guild_id: int) -> dict[str, Any]:
        return await self.protection.antialt(guild_id)

    async def _alert(self, guild: discord.Guild, payload: dict[str, Any]) -> None:
        self.bot.dispatch("safety_alert", guild, payload)

    @Cog.listener(name="on_member_join")
    async def antialt_member_join(self, member: discord.Member) -> None:
        if member.bot or not await self._is_enabled(member.guild.id):
            return

        config = await self._get_config(member.guild.id)
        age_days = _account_age_days(member)
        min_age = int(config.get("min_age") or DEFAULT_ANTIALT["min_age"])
        if age_days >= min_age:
            return

        level = int(config.get("level") or DEFAULT_ANTIALT["level"])
        role_id = config.get("restricted_role")
        logs_channel = await self._get_logs_channel(member.guild.id)
        restricted_role = member.guild.get_role(role_id) if role_id else None

        account_created_unix = _datetime_to_unix(member.created_at)
        em = (
            orange_embed(
                title="<:raidreport:1268857575919714376>  Alt Account Detected",
                description=(
                    f"{member.mention} — {discord.utils.escape_markdown(str(member))}\n\n"
                    f"**Account Created:** <t:{account_created_unix}:F> "
                    f"(<t:{account_created_unix}:R>)\n"
                    f"**Account Age:** `{age_days:.1f}` days  (minimum: `{min_age}` days)\n"
                    f"**Protection Level:** `{level}`"
                ),
                timestamp=True,
            )
            .set_author(name=str(member), icon_url=member.display_avatar.url)
            .set_footer(text=f"User ID: {member.id}")
        )

        action_label = "Unknown"
        outcome = "failed"
        try:
            if level == 1:
                if restricted_role:
                    await member.add_roles(
                        restricted_role, reason="Lucent Anti-Alt: Account too new"
                    )
                    action_label = f"RESTRICTED (role: {restricted_role.name})"
                    outcome = "restrict"
                else:
                    until = discord.utils.utcnow() + datetime.timedelta(hours=24)
                    await member.timeout(
                        until,
                        reason="Lucent Anti-Alt: Account too new — no restricted role set",
                    )
                    action_label = "TIMED OUT 24h (no restricted role configured)"
                    outcome = "timeout"
            elif level == 2:
                if member.guild.me.guild_permissions.kick_members:
                    await member.kick(reason="Lucent Anti-Alt: Account too new")
                    action_label = "KICKED"
                    outcome = "kick"
            elif level >= 3:
                if member.guild.me.guild_permissions.ban_members:
                    await member.ban(
                        reason="Lucent Anti-Alt: Account too new", delete_message_days=0
                    )
                    action_label = "BANNED"
                    outcome = "ban"
        except discord.HTTPException as exc:
            action_label = f"FAILED ({exc})"

        await self.moderation.record_antialt(
            member.guild.id,
            member.id,
            getattr(self.bot.user, "id", 0),
            reason=f"Account age {age_days:.1f}d is below the {min_age}d minimum",
            metadata={
                "action": outcome,
                "level": level,
                "account_age_days": round(age_days, 2),
                "min_age_days": min_age,
            },
        )

        em.add_field(name="Action Taken", value=f"`{action_label}`", inline=False)
        await self._alert(
            member.guild,
            {
                "source": "antialt",
                "module": "account_age",
                "user_id": member.id,
                "action": outcome,
                "level": level,
                "account_age_days": round(age_days, 2),
            },
        )
        if logs_channel:
            await self.bot.send_log(logs_channel, embed=em)

    @Cog.listener(name="on_member_join")
    async def antialt_ban_on_rejoin(self, member: discord.Member) -> None:
        """Escalate a Level 2 anti-alt kick when the user rejoins within 24h."""

        if member.bot or not await self._is_enabled(member.guild.id):
            return
        config = await self._get_config(member.guild.id)
        if int(config.get("level") or 0) != 2:
            return

        recent_kick = await self.moderation.recent_antialt_kick(
            member.guild.id, member.id, hours=24
        )
        if not recent_kick:
            return

        try:
            await member.ban(
                reason="Lucent Anti-Alt: Rejoined after Level 2 kick",
                delete_message_days=0,
            )
        except discord.HTTPException:
            return

        await self.moderation.record_antialt(
            member.guild.id,
            member.id,
            getattr(self.bot.user, "id", 0),
            reason="Rejoined within 24 hours of an Anti-Alt kick",
            metadata={
                "action": "ban",
                "level": 2,
                "rejoin_ban": True,
                "previous_case_id": str(recent_kick["case_id"]),
            },
        )
        await self._alert(
            member.guild,
            {
                "source": "antialt",
                "module": "rejoin_ban",
                "user_id": member.id,
                "action": "ban",
                "level": 2,
            },
        )

        logs_channel = await self._get_logs_channel(member.guild.id)
        if logs_channel:
            em = red_embed(
                title="<:ban:1268874381648465920>  Rejoin Ban — Anti-Alt",
                description=(
                    f"{member.mention} was previously **kicked** by Anti-Alt and attempted to rejoin.\n"
                    f"They have been **permanently banned**."
                ),
                timestamp=True,
            )
            em.set_author(name=str(member), icon_url=member.display_avatar.url)
            em.set_footer(text=f"User ID: {member.id}")
            await self.bot.send_log(logs_channel, embed=em)


class AutoModConfig(Cog):
    """AutoMod event listener and enforcement engine."""

    _spam_buckets: dict[int, dict[int, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    _join_buckets: dict[int, list[float]] = defaultdict(list)
    _raid_locked: dict[int, bool] = {}

    def __init__(self, bot: Lucent):
        self.bot = bot
        self.protection: ProtectionService = get_protection(bot)
        self.logs = get_logs(bot)
        self.moderation = get_moderation(bot)
        self.scheduler = get_scheduler(bot)
        self._mentions = bot.allowed_mentions
        self.scheduler.start()

    async def cog_unload(self) -> None:
        self.scheduler.stop()

    def clear_config_cache(self, guild_id: int | None = None) -> None:
        self.protection.invalidate(guild_id)
        self.logs.invalidate(guild_id)

    # Compatibility wrappers: other cogs still call these by name.
    async def _get_logs_channel(self, guild_id: int) -> discord.TextChannel | None:
        channel_id = await self.logs.get_channel_id(guild_id)
        if not channel_id:
            return None
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return None
        try:
            channel = guild.get_channel(channel_id) or await guild.fetch_channel(
                channel_id
            )
        except (discord.Forbidden, discord.HTTPException, discord.NotFound):
            return None
        return channel if isinstance(channel, discord.TextChannel) else None

    async def _is_enabled(self, guild_id: int) -> bool:
        return await self.protection.automod_enabled(guild_id)

    async def _get_config(self, guild_id: int) -> dict[str, Any]:
        return await self.protection.automod(guild_id)

    async def _get_thresholds(self, guild_id: int) -> list[dict[str, Any]]:
        return await self.protection.thresholds(guild_id)

    @staticmethod
    def _mod_enabled(cfg: dict[str, Any], module: str) -> bool:
        value = cfg.get(module, {})
        if isinstance(value, bool):
            return value
        if isinstance(value, dict):
            return bool(value.get("enabled", False))
        return False

    @staticmethod
    def _mod_cfg(cfg: dict[str, Any], module: str) -> dict[str, Any]:
        value = cfg.get(module, {})
        return value if isinstance(value, dict) else {}

    async def _log(
        self,
        guild_id: int,
        *,
        title: str,
        description: str,
        color: discord.Color | int = 0xFAA61A,
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

    async def check_warn_threshold(
        self, user_id: int, guild_id: int, *, warn_count: int | None = None
    ) -> None:
        """Execute the highest crossed warn threshold and record a case."""

        thresholds = await self._get_thresholds(guild_id)
        if not thresholds:
            return
        if warn_count is None:
            warn_count = await self.moderation.warn_count(
                guild_id,
                user_id,
                decay_days=await self.protection.warn_decay_days(guild_id),
            )

        action_cfg: dict[str, Any] | None = None
        for threshold in thresholds:
            if warn_count >= int(threshold.get("warns", 0)):
                action_cfg = threshold
        if action_cfg is None:
            return

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        member = guild.get_member(user_id)
        if member is None:
            return

        action = action_cfg.get("action", "none")
        warns_needed = int(action_cfg.get("warns", 0))
        duration_secs = int(
            action_cfg.get("duration") or DEFAULT_THRESHOLD_SETTINGS["duration"]
        )
        reason = f"AutoMod: {warns_needed} warn threshold — automatic {action}"
        action_type = "automod"
        duration: int | None = None
        executed = False
        metadata: dict[str, Any] = {
            "module": "warn_threshold",
            "threshold": warns_needed,
            "warn_count": warn_count,
        }

        try:
            if action == "timeout":
                until = discord.utils.utcnow() + datetime.timedelta(
                    seconds=duration_secs
                )
                await member.timeout(until, reason=reason)
                action_type, duration, executed = "timeout", duration_secs, True
            elif action == "kick":
                if guild.me.guild_permissions.kick_members:
                    await member.kick(reason=reason)
                    action_type, executed = "kick", True
            elif action == "ban":
                if guild.me.guild_permissions.ban_members:
                    await member.ban(reason=reason, delete_message_days=0)
                    action_type, executed = "ban", True
            elif action == "tempban":
                unban_days = max(
                    1,
                    int(
                        action_cfg.get("unban_days")
                        or DEFAULT_THRESHOLD_SETTINGS["unban_days"]
                    ),
                )
                if guild.me.guild_permissions.ban_members:
                    await member.ban(reason=reason, delete_message_days=0)
                    action_type, duration, executed = (
                        "autoban",
                        unban_days * 86400,
                        True,
                    )
                    await self.scheduler.schedule_unban(
                        guild_id,
                        user_id,
                        discord.utils.utcnow() + datetime.timedelta(days=unban_days),
                        reason="AutoMod: Temp-ban expired",
                        source="automod",
                    )
            elif action in ("role_add", "role_remove"):
                role = guild.get_role(int(action_cfg.get("role_id") or 0))
                if role is not None:
                    if action == "role_add":
                        await member.add_roles(role, reason=reason)
                    else:
                        await member.remove_roles(role, reason=reason)
                    metadata["role_id"] = role.id
                    executed = True
        except discord.HTTPException:
            pass

        if not executed:
            return

        await self.moderation.record_automod(
            guild_id,
            user_id,
            getattr(self.bot.user, "id", 0),
            action_type=action_type,
            reason=reason,
            duration_seconds=duration,
            metadata=metadata,
        )
        await self._alert(
            guild,
            {
                "source": "automod",
                "module": "warn_threshold",
                "user_id": user_id,
                "action": action,
                "threshold": warns_needed,
            },
        )

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
            color=0xED4245,
            member=member,
            fields=[
                ("Action", human_action, True),
                ("Threshold", str(warns_needed), True),
                ("Total Warns", str(warn_count), True),
            ],
        )

    @Cog.listener()
    async def on_message(self, msg: discord.Message) -> None:
        if msg.author.bot or not msg.guild or _has_mod_perms(msg):
            return
        if not await self._is_enabled(msg.guild.id):
            return

        handlers: dict[str, Any] = {
            "banned_words": self._banned_words,
            "scam_links": self._scam_links,
            "all_caps": self._all_caps,
            "message_spam": self._message_spam,
            "invites": self._invites,
            "mass_mentions": self._mass_mentions,
            "emoji_spam": self._emoji_spam,
            "zalgo_text": self._zalgo_text,
            "newline_spam": self._newline_spam,
            "repeated_chars": self._repeated_chars,
        }
        content_enabled = bool(getattr(self.bot, "can_read_message_content", False))
        for module, settings in await self.protection.detect_rules(
            msg.guild.id, msg.channel.id
        ):
            if module in CONTENT_MODULES and not content_enabled:
                continue
            handler = handlers.get(module)
            if handler is None:
                continue
            if module in CONTENT_MODULES and not getattr(msg, "content", ""):
                continue
            if await handler(msg, settings):
                await self._issue_automod_warn(msg, module)
                return

    async def _issue_automod_warn(self, msg: discord.Message, module: str) -> None:
        """Create an automod case, log it and re-check warn thresholds."""

        if not msg.guild:
            return
        reason = f"AutoMod: {module.replace('_', ' ').title()}"
        await self.moderation.record_automod(
            msg.guild.id,
            msg.author.id,
            getattr(self.bot.user, "id", 0),
            reason=reason,
            metadata={"module": module, "channel_id": msg.channel.id},
        )
        warn_count = await self.moderation.warn_count(
            msg.guild.id,
            msg.author.id,
            decay_days=await self.protection.warn_decay_days(msg.guild.id),
        )
        preview = msg.content[:300] + "…" if len(msg.content) > 300 else msg.content
        await self._log(
            msg.guild.id,
            title="AutoMod Triggered",
            description=f"**Message:**\n{discord.utils.escape_markdown(preview)}",
            color=0xFAA61A,
            member=msg.author,  # type: ignore[arg-type]
            fields=[
                ("Module", f"`{module.replace('_', ' ').title()}`", True),
                ("Channel", msg.channel.mention, True),  # type: ignore[attr-defined]
                ("Warn Count", f"`{warn_count}`", True),
            ],
            warn_count=warn_count,
        )
        await self._alert(
            msg.guild,
            {
                "source": "automod",
                "module": module,
                "user_id": msg.author.id,
                "action": "warn",
                "channel_id": msg.channel.id,
                "message": msg.content,
            },
        )
        await self.check_warn_threshold(
            msg.author.id, msg.guild.id, warn_count=warn_count
        )

    async def _send(self, ch: Any, text: str) -> None:
        try:
            await ch.send(text, delete_after=5, allowed_mentions=self._mentions)
        except discord.HTTPException:
            pass

    async def _delete(self, msg: discord.Message) -> None:
        try:
            await msg.delete()
        except discord.HTTPException:
            pass

    async def _banned_words(self, msg: discord.Message, cfg: dict[str, Any]) -> bool:
        content = msg.content.lower()
        for word in BANNED_WORDS:
            if word in content:
                await self._delete(msg)
                await self._send(
                    msg.channel, f"{msg.author.mention} Watch your language."
                )
                return True
        return False

    async def _scam_links(self, msg: discord.Message, cfg: dict[str, Any]) -> bool:
        if SCAM_PATTERNS.search(msg.content):
            await self._delete(msg)
            await self._send(
                msg.channel,
                f"{msg.author.mention} Scam/phishing links are not allowed.",
            )
            return True
        return False

    async def _all_caps(self, msg: discord.Message, cfg: dict[str, Any]) -> bool:
        threshold = int(_setting("all_caps", cfg, "threshold"))
        min_length = int(_setting("all_caps", cfg, "min_length"))
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

    async def _message_spam(self, msg: discord.Message, cfg: dict[str, Any]) -> bool:
        threshold = int(_setting("message_spam", cfg, "threshold"))
        window = int(_setting("message_spam", cfg, "window_seconds"))
        bucket = self._spam_buckets[msg.guild.id][msg.author.id]  # type: ignore[index]
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

    async def _invites(self, msg: discord.Message, cfg: dict[str, Any]) -> bool:
        whitelist: list[str] = list(cfg.get("whitelist") or [])
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

    async def _mass_mentions(self, msg: discord.Message, cfg: dict[str, Any]) -> bool:
        threshold = int(_setting("mass_mentions", cfg, "threshold"))
        if len(msg.mentions) + len(msg.role_mentions) >= threshold:
            await self._delete(msg)
            await self._send(msg.channel, f"{msg.author.mention} Don't spam mentions.")
            return True
        return False

    async def _emoji_spam(self, msg: discord.Message, cfg: dict[str, Any]) -> bool:
        threshold = int(_setting("emoji_spam", cfg, "threshold"))
        emoji_count = emojis.count(msg.content) + len(
            CUSTOM_EMOJI_REGEX.findall(msg.content)
        )
        if emoji_count > threshold:
            await self._delete(msg)
            await self._send(msg.channel, f"{msg.author.mention} Don't spam emojis.")
            return True
        return False

    async def _zalgo_text(self, msg: discord.Message, cfg: dict[str, Any]) -> bool:
        if ZALGO_REGEX.search(parse.quote(msg.content.encode("utf-8"))):
            await self._delete(msg)
            await self._send(
                msg.channel,
                f"{msg.author.mention} Zalgo/corrupted text is not allowed.",
            )
            return True
        return False

    async def _newline_spam(self, msg: discord.Message, cfg: dict[str, Any]) -> bool:
        threshold = int(_setting("newline_spam", cfg, "threshold"))
        if msg.content.count("\n") >= threshold:
            await self._delete(msg)
            await self._send(
                msg.channel,
                f"{msg.author.mention} Excessive line breaks are not allowed.",
            )
            return True
        return False

    async def _repeated_chars(self, msg: discord.Message, cfg: dict[str, Any]) -> bool:
        threshold = int(_setting("repeated_chars", cfg, "threshold"))
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
        if member.bot or not await self._is_enabled(member.guild.id):
            return
        cfg = await self._get_config(member.guild.id)
        await self.protection.detect_rules(member.guild.id)
        await self._check_username_filter(member, cfg)
        await self._check_default_avatar(member, cfg)
        await self._track_join_rate(member, cfg)

    async def _check_username_filter(
        self, member: discord.Member, cfg: dict[str, Any]
    ) -> None:
        if not self._mod_enabled(cfg, "username_filter"):
            return
        settings = cfg.get("username_filter") or {}
        name = (member.display_name or member.name).lower()

        for word in BANNED_WORDS:
            if word in name:
                reason = "AutoMod: Banned word in username"
                try:
                    await member.kick(reason=reason)
                except discord.HTTPException:
                    return
                await self._record_join_action(
                    member, "kick", reason, "username_filter", {"matched_word": word}
                )
                await self._log(
                    member.guild.id,
                    title="Username Filter — Kicked",
                    description=f"{member.mention} was kicked for having a banned word in their username.",
                    member=member,
                    color=0xED4245,
                    fields=[
                        ("Username", discord.utils.escape_markdown(str(member)), False)
                    ],
                )
                return

        if not _setting("username_filter", settings, "impersonation_check"):
            return
        similarity_limit = float(_setting("username_filter", settings, "similarity"))
        for other in member.guild.members:
            if other == member:
                continue
            if not any(
                r.permissions.kick_members or r.permissions.manage_guild
                for r in other.roles
            ):
                continue
            similarity = SequenceMatcher(
                None, member.display_name.lower(), other.display_name.lower()
            ).ratio()
            if similarity >= similarity_limit:
                reason = "AutoMod: Possible staff impersonation"
                try:
                    await member.kick(reason=reason)
                except discord.HTTPException:
                    return
                await self._record_join_action(
                    member,
                    "kick",
                    reason,
                    "username_filter",
                    {"similarity": round(similarity, 3)},
                )
                await self._log(
                    member.guild.id,
                    title="Impersonation Detected — Kicked",
                    description=(
                        f"{member.mention} has a suspiciously similar name to "
                        f"staff member **{discord.utils.escape_markdown(str(other))}** "
                        f"(similarity `{similarity:.0%}`)."
                    ),
                    member=member,
                    color=0xED4245,
                )
                return

    async def _check_default_avatar(
        self, member: discord.Member, cfg: dict[str, Any]
    ) -> None:
        if not self._mod_enabled(cfg, "default_avatar"):
            return
        if member.avatar is not None:
            return

        settings = self._mod_cfg(cfg, "default_avatar")
        action = str(_setting("default_avatar", settings, "action"))
        reason = "AutoMod: Default avatar"
        action_type = "automod"
        try:
            if action == "kick":
                await member.kick(reason=reason)
                action_type = "kick"
            elif action == "ban":
                await member.ban(reason=reason, delete_message_days=0)
                action_type = "ban"
            else:
                antialt = await self.protection.antialt(member.guild.id)
                role_id = antialt.get("restricted_role")
                role = member.guild.get_role(role_id) if role_id else None
                if role is not None:
                    await member.add_roles(role, reason=reason)
        except discord.HTTPException:
            return

        await self._record_join_action(
            member, action_type, reason, "default_avatar", {"action": action}
        )
        await self._log(
            member.guild.id,
            title="Default Avatar Detected",
            description=f"{member.mention} joined with no avatar. Action: **{action.title()}**.",
            member=member,
            color=0xFFD700,
        )

    async def _record_join_action(
        self,
        member: discord.Member,
        action_type: str,
        reason: str,
        module: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a join filter punishment and emit its workflow alert."""

        payload = {"module": module, **(metadata or {})}
        await self.moderation.record_automod(
            member.guild.id,
            member.id,
            getattr(self.bot.user, "id", 0),
            action_type=action_type,
            reason=reason,
            metadata=payload,
        )
        await self._alert(
            member.guild,
            {
                "source": "automod",
                "module": module,
                "user_id": member.id,
                "action": action_type,
                **(metadata or {}),
            },
        )

    async def _track_join_rate(
        self, member: discord.Member, cfg: dict[str, Any]
    ) -> None:
        if not self._mod_enabled(cfg, "join_rate"):
            return
        guild_id = member.guild.id
        if self._raid_locked.get(guild_id):
            return

        settings = self._mod_cfg(cfg, "join_rate")
        threshold = int(_setting("join_rate", settings, "threshold"))
        window = int(_setting("join_rate", settings, "window_seconds"))
        lockdown_minutes = int(_setting("join_rate", settings, "lockdown_minutes"))

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
            self._raid_locked[guild_id] = False
            return

        restore_at = discord.utils.utcnow() + datetime.timedelta(
            minutes=lockdown_minutes
        )
        await self.scheduler.schedule_verification_restore(
            guild_id,
            original_level,
            restore_at,
            reason="AutoMod: Raid lockdown expired",
        )

        ch = await self._get_logs_channel(guild_id)
        if ch:
            em = discord.Embed(
                title="🚨  Raid Detected — Lockdown Active",
                description=(
                    f"**{threshold}+ members** joined within `{window}s`.\n\n"
                    f"Verification level raised to **High**.\n"
                    f"Lockdown lifts in `{lockdown_minutes}` minute(s)."
                ),
                color=0xED4245,
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
            em.set_footer(text=guild.name)
            await self.bot.send_log(ch, embed=em)

        await self._alert(
            guild,
            {
                "source": "automod",
                "module": "join_rate",
                "user_id": member.id,
                "action": "lockdown",
                "threshold": threshold,
                "lockdown_minutes": lockdown_minutes,
            },
        )


async def setup(bot: Lucent) -> None:
    await bot.add_cog(AntiAltsConfig(bot))
    await bot.add_cog(AutoModConfig(bot))
