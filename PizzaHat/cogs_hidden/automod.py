import datetime
import re
from typing import Union
from urllib import parse

import discord
import emojis
from async_lru import alru_cache
from discord.ext import commands

from core.bot import PizzaHat
from core.cog import Cog
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

            channel = await guild.fetch_channel(data)
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

        await logs_channel.send(embed=em)

    @Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot or msg.content == "" or not msg.guild or self.mod_perms(msg):
            return

        am_enabled_guild = await self.check_if_am_is_enabled(msg.guild.id)

        if not am_enabled_guild:
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

    async def invites(self, msg: discord.Message, m: dict) -> bool:
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
