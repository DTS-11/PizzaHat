import datetime
import re
from typing import Union
from urllib import parse

import discord
import emojis
from async_lru import alru_cache
from core.bot import PizzaHat
from core.cog import Cog
from discord.ext import commands
from utils.bad_words import BANNED_WORDS
from utils.embed import red_embed


class AutoModConfig(Cog):
    """AutoMod config/logic cog."""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot
        self.mentions = bot.allowed_mentions
        self.invite_regex = re.compile(
            r"((http(s|):\/\/|)(discord)(\.(gg|io|me)\/|app\.com\/invite\/)([0-z]+))"
        )
        self.zalgo_regex = re.compile(r"%CC%", re.MULTILINE)

    def clear_config_cache(self, guild_id: int | None = None) -> None:
        self.get_logs_channel.cache_clear()
        self.check_if_am_is_enabled.cache_clear()
        self.get_automod_modules.cache_clear()
        self.get_warn_config.cache_clear()

    def mod_perms(self, m: discord.Message) -> bool:
        p: discord.Permissions = m.author.guild_permissions  # type: ignore
        return (
            True
            if (
                p.kick_members
                or p.ban_members
                or p.manage_guild
                or p.administrator
                or m.author == m.guild.owner  # type: ignore
            )
            else False
        )

    @alru_cache()
    async def get_logs_channel(self, guild_id: int) -> Union[discord.TextChannel, None]:
        if self.bot.db is not None:
            data = await self.bot.db.fetchval(
                "SELECT channel_id FROM guild_logs WHERE guild_id=$1", guild_id
            )
            guild = self.bot.get_guild(guild_id)

            if not guild or not data:
                return

            channel = guild.get_channel(data) or await guild.fetch_channel(data)
            assert isinstance(channel, discord.TextChannel), (
                "channel will always be a textchannel"
            )
            return channel

    @alru_cache()
    async def check_if_am_is_enabled(self, guild_id: int) -> bool:
        data: bool = (
            await self.bot.db.fetchval(
                "SELECT enabled FROM automod WHERE guild_id=$1", guild_id
            )
            if self.bot.db
            else False
        )
        return data

    @alru_cache()
    async def get_automod_modules(self, guild_id: int) -> list:
        if self.bot.db is None:
            return []

        modules = await self.bot.db.fetchval(
            "SELECT modules FROM automod WHERE guild_id=$1", guild_id
        )
        return modules or []

    @alru_cache()
    async def get_warn_config(self, guild_id: int) -> dict:
        if self.bot.db is None:
            return {"warn_action": "none", "warn_threshold": 0}

        row = await self.bot.db.fetchrow(
            "SELECT warn_action, warn_threshold FROM automod WHERE guild_id=$1",
            guild_id,
        )

        if not row:
            return {"warn_action": "none", "warn_threshold": 0}

        return {
            "warn_action": row["warn_action"] or "none",
            "warn_threshold": row["warn_threshold"] or 0,
        }

    async def check_warn_threshold(self, user_id: int, guild_id: int):
        """Check if user has reached warn threshold and take action."""
        if not self.bot.db:
            return

        warn_config = await self.get_warn_config(guild_id)
        threshold = warn_config["warn_threshold"]
        action = warn_config["warn_action"]

        if threshold <= 0 or action == "none":
            return

        warn_count = await self.bot.db.fetchval(
            "SELECT COUNT(*) FROM warnlogs WHERE user_id=$1 AND guild_id=$2",
            user_id,
            guild_id,
        )

        if warn_count and warn_count >= threshold:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return

            member = guild.get_member(user_id)
            if not member:
                return

            reason = f"AutoMod: Reached {threshold} warns"

            try:
                if action == "timeout":
                    await member.timeout(
                        discord.utils.utcnow() + datetime.timedelta(hours=1),
                        reason=reason,
                    )
                elif action == "kick":
                    if guild.me.guild_permissions.kick_members:
                        await member.kick(reason=reason)
                elif action == "ban":
                    if guild.me.guild_permissions.ban_members:
                        await member.ban(reason=reason)
            except discord.HTTPException:
                pass

    @Cog.listener()
    async def on_automod_trigger(self, msg: discord.Message, module: str):
        if not msg.guild:
            return

        logs_channel = await self.get_logs_channel(msg.guild.id)
        am_enabled_guild = await self.check_if_am_is_enabled(msg.guild.id)

        if not logs_channel or not am_enabled_guild:
            return

        em = red_embed(
            title="<:danger:1268855303768903733> Auto-Mod Triggered",
            description=msg.content,
        )
        em.set_author(
            name=msg.author,
            icon_url=msg.author.avatar.url if msg.author.avatar else None,
        )
        em.set_footer(text=f"Message ID: {msg.id} | User ID: {msg.author.id}")
        em.add_field(name="Module", value=module)

        await self.bot.send_log(logs_channel, embed=em)

    @Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot or msg.content == "" or not msg.guild or self.mod_perms(msg):
            return

        am_enabled_guild = await self.check_if_am_is_enabled(msg.guild.id)

        if not am_enabled_guild:
            return

        active_modules = await self.get_automod_modules(msg.guild.id)

        if "banned_words" in active_modules:
            triggered = await self.banned_words(msg)
            if triggered:
                await self.on_automod_trigger(msg, "banned_words")
                return

        if "all_caps" in active_modules:
            triggered = await self.all_caps(msg)
            if triggered:
                await self.on_automod_trigger(msg, "all_caps")
                return

        if "message_spam" in active_modules:
            triggered = await self.message_spam(msg)
            if triggered:
                await self.on_automod_trigger(msg, "message_spam")
                return

        if "invites" in active_modules:
            triggered = await self.invites(msg)
            if triggered:
                await self.on_automod_trigger(msg, "invites")
                return

        if "mass_mentions" in active_modules:
            triggered = await self.mass_mentions(msg)
            if triggered:
                await self.on_automod_trigger(msg, "mass_mentions")
                return

        if "emoji_spam" in active_modules:
            triggered = await self.emoji_spam(msg)
            if triggered:
                await self.on_automod_trigger(msg, "emoji_spam")
                return

        if "zalgo_text" in active_modules:
            triggered = await self.zalgo_text(msg)
            if triggered:
                await self.on_automod_trigger(msg, "zalgo_text")
                return

    async def banned_words(self, msg: discord.Message) -> bool:
        banned_words = BANNED_WORDS.copy()

        for word in banned_words:
            if word in msg.content.lower():
                try:
                    await msg.delete()
                except Exception:
                    pass

                await msg.channel.send(
                    f"{msg.author.mention}, Watch your language.",
                    delete_after=5,
                    allowed_mentions=self.mentions,  # type: ignore
                )
                return True
        return False

    async def all_caps(self, msg: discord.Message) -> bool:
        if len(msg.content) <= 7:
            return False

        if msg.content.isupper():
            try:
                await msg.delete()
            except Exception:
                pass

            await msg.channel.send(
                f"{msg.author.mention}, Too many caps.",
                delete_after=5,
                allowed_mentions=self.mentions,  # type: ignore
            )
            return True

        upper_count = 0

        for h in msg.content:
            if h.isupper():
                upper_count += 1

        if (upper_count / len(msg.content)) * 100 > 70:
            await msg.delete()
            await msg.channel.send(
                f"{msg.author.mention}, Too many caps.",
                delete_after=5,
                allowed_mentions=self.mentions,  # type: ignore
            )
            return True
        return False

    async def message_spam(self, msg: discord.Message) -> bool:
        def _check(m: discord.Message) -> bool:
            return (
                m.author == msg.author
                and (
                    datetime.datetime.now(datetime.timezone.utc)
                    - m.created_at.replace(tzinfo=None)
                ).seconds
                < 7
            )

        h = list(filter(lambda m: _check(m), self.bot.cached_messages))

        if len(h) >= 5:
            if isinstance(
                msg.channel,
                Union[
                    discord.TextChannel,
                    discord.Thread,
                    discord.VoiceChannel,
                    discord.StageChannel,
                ],
            ):
                await msg.channel.purge(limit=5, check=_check)
                await msg.channel.send(
                    f"{msg.author.mention}, Stop spamming.",
                    delete_after=5,
                    allowed_mentions=self.mentions,  # type: ignore
                )
            return True
        return False

    async def invites(self, msg: discord.Message) -> bool:
        invite_match = self.invite_regex.findall(msg.content)

        if invite_match and msg.guild is not None:
            for e in invite_match:
                try:
                    invite = await self.bot.fetch_invite(e[-1])

                except discord.NotFound:
                    pass

                else:
                    if invite.guild is not None:
                        if not invite.guild.id == msg.guild.id:
                            await msg.delete()
                            await msg.channel.send(
                                f"{msg.author.mention}, No invite links.",
                                delete_after=5,
                                allowed_mentions=self.mentions,  # type: ignore
                            )
                            return True
        return False

    async def mass_mentions(self, msg: discord.Message) -> bool:
        if len(msg.mentions) >= 3:
            await msg.delete()
            await msg.channel.send(
                f"{msg.author.mention}, Don't spam mentions.",
                delete_after=5,
                allowed_mentions=self.mentions,  # type: ignore
            )
            return True
        return False

    async def emoji_spam(self, msg: discord.Message) -> bool:
        converter = commands.PartialEmojiConverter()
        stuff = msg.content.split()
        emoji_count = emojis.count(msg.content)
        ctx = await self.bot.get_context(msg)

        for thing in stuff:
            try:
                await converter.convert(ctx, thing)
                emoji_count += 1
            except commands.PartialEmojiConversionFailure:
                pass

        if emoji_count > 10:
            await msg.delete()
            await msg.channel.send(
                f"{msg.author.mention}, Don't spam emojis.",
                delete_after=5,
                allowed_mentions=self.mentions,  # type: ignore
            )
            return True
        return False

    async def zalgo_text(self, msg: discord.Message) -> bool:
        x = self.zalgo_regex.search(parse.quote(msg.content.encode("utf-8")))
        if x:
            await msg.delete()
            await msg.channel.send(
                f"{msg.author.mention}, No zalgo allowed.",
                delete_after=5,
                allowed_mentions=self.mentions,  # type: ignore
            )
            return True
        return False


async def setup(bot):
    await bot.add_cog(AutoModConfig(bot))
