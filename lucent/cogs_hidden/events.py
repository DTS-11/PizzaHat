"""Core guild and mention event listeners.

This internal cog owns no commands. It handles bot mentions, optional global
event logging, and cache cleanup when the bot leaves a guild.
"""

from __future__ import annotations

import discord

from core.bot import Lucent
from core.cog import Cog
from services import get_logs, get_protection
from utils.config import LOG_CHANNEL_ID
from utils.embed import green_embed, guild_embed, red_embed


class Events(Cog):
    """Events cog"""

    def __init__(self, bot: Lucent):
        self.bot: Lucent = bot

    async def _get_bot_logs_channel(self) -> discord.TextChannel | None:
        """Resolve the optional deployment-wide log channel, if configured."""

        if not LOG_CHANNEL_ID:
            return None
        channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(LOG_CHANNEL_ID)
            except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                return None
        return channel if isinstance(channel, discord.TextChannel) else None

    async def _send_bot_logs_embed(self, embed: discord.Embed) -> None:
        channel = await self._get_bot_logs_channel()
        if channel is not None:
            await self.bot.send_log(channel, embed=embed)

    @Cog.listener()
    async def on_message(self, msg: discord.Message) -> None:
        if self.bot.user is None or msg.author.bot or msg.author == self.bot.user:
            return

        bot_id = self.bot.user.id
        if msg.content not in {f"<@{bot_id}>", f"<@!{bot_id}>"}:
            return

        em = await guild_embed(
            self.bot.db,
            msg.guild.id if msg.guild else 0,
            "Hello! <a:wave_animated:783393435242463324>",
            (
                f"I'm {self.bot.user.name} — a deterministic Discord operations "
                "engine. Use `/help` to get started, or mention me for text commands."
            ),
        )
        await msg.channel.send(embed=em)

    @Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        em = green_embed(title="Guild Joined", timestamp=True)
        em.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)
        em.add_field(name="Guild Name", value=guild.name, inline=False)
        em.add_field(
            name="Members", value=guild.member_count or len(guild.members), inline=False
        )
        if guild.owner:
            em.add_field(
                name="Owner", value=f"{guild.owner} ({guild.owner.id})", inline=False
            )
        await self._send_bot_logs_embed(em)

    @Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        # Service caches are guild-scoped; drop them as soon as the bot leaves.
        entitlements = getattr(self.bot, "entitlements", None)
        if entitlements is not None:
            entitlements.invalidate(guild.id)
        get_protection(self.bot).invalidate(guild.id)
        get_logs(self.bot).invalidate(guild.id)

        for cog_name in (
            "AntiAlts",
            "AntiAltsConfig",
            "WorkflowRunner",
            "AutoModeration",
            "AutoModConfig",
            "GuildLogs",
            "Mod",
        ):
            cog = self.bot.get_cog(cog_name)
            if cog is None:
                continue
            for attr in (
                "clear_config_cache",
                "clear_cache",
                "clear_log_config_cache",
                "invalidate",
            ):
                clear_cache = getattr(cog, attr, None)
                if callable(clear_cache):
                    try:
                        result = clear_cache(guild.id)
                        if hasattr(result, "__await__"):
                            await result
                    except TypeError:
                        clear_cache()

        em = red_embed(title="Guild Left", timestamp=True)
        em.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)
        em.add_field(name="Guild Name", value=guild.name, inline=False)
        em.add_field(
            name="Members", value=guild.member_count or len(guild.members), inline=False
        )
        if guild.owner:
            em.add_field(
                name="Owner", value=f"{guild.owner} ({guild.owner.id})", inline=False
            )
        em.add_field(name="Leave Type", value="Removed / left", inline=False)
        await self._send_bot_logs_embed(em)


async def setup(bot: Lucent) -> None:
    await bot.add_cog(Events(bot))
