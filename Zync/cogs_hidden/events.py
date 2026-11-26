"""Core guild and member event listeners.

Handles bot/guild lifecycle logging, member join/leave notices, and shared
guild-state cleanup. This cog is internal and exposes no public commands.
"""

import asyncio

import discord

from core.bot import Zync
from core.cog import Cog
from utils.config import LOGS_CHANNEL
from utils.embed import green_embed, guild_embed, red_embed


class Events(Cog):
    """Events cog"""

    def __init__(self, bot: Zync):
        self.bot: Zync = bot
        self._auto_left: set[int] = set()
        # bot.loop.create_task(self.update_stats())

    async def _get_bot_logs_channel(self) -> discord.TextChannel | None:
        channel = self.bot.get_channel(LOGS_CHANNEL)

        if channel is None:
            try:
                channel = await self.bot.fetch_channel(LOGS_CHANNEL)
            except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                return None

        return channel if isinstance(channel, discord.TextChannel) else None

    async def _send_bot_logs_embed(self, embed: discord.Embed) -> None:
        channel = await self._get_bot_logs_channel()
        if channel is None:
            return

        await self.bot.send_log(channel, embed=embed)

    def _get_leave_reason(self, guild: discord.Guild) -> tuple[str, bool]:
        if guild.id in self._auto_left:
            self._auto_left.discard(guild.id)
            return "Left due to higher bot ratio or too few human members", True

        return "Manually removed", False

    # @tasks.loop(hours=24)
    # async def update_stats(self):
    #     try:
    #         # Top.gg
    #         await self.bot.wait_until_ready()
    #         self.topggpy = topgg.DBLClient(self, TOPGG_TOKEN, autopost=True)  # type: ignore
    #         await self.topggpy.post_guild_count()
    #         print(f"Posted server count: {self.topggpy.guild_count}")

    #     except Exception as e:
    #         print(e)

    #     try:
    #         # DList.gg
    #         url = f"https://api.discordlist.gg/v0/bots/860889936914677770/guilds?count={len(self.bot.guilds)}"
    #         headers = {'Authorization': f"Bearer {DLIST_TOKEN}", "Content-Type": "application/json"}
    #         r = requests.put(url, headers=headers)
    #         print(r.json())

    #     except Exception as e:
    #         print(e)

    @Cog.listener()
    async def on_ready(self):
        return

    # ====== BOT PING MSG ======

    @Cog.listener()
    async def on_message(self, msg: discord.Message):
        if self.bot and self.bot.user is not None:
            bot_id = self.bot.user.id

            if msg.author.bot:
                return

            if self.bot.user == msg.author:
                return

            if msg.content in {f"<@{bot_id}>", f"<@!{bot_id}>"}:
                em = await guild_embed(
                    self.bot.db,
                    msg.guild.id if msg.guild else 0,
                    "Hello! <a:wave_animated:783393435242463324>",
                    f"I'm {self.bot.user.name} — Your Ultimate Discord Companion.\nUse `/help` to get started, or mention me for text commands.",
                )

                await msg.channel.send(embed=em)

    # ====== BOT GUILD JOIN/LEAVE ======

    @Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        em = green_embed(
            title="Guild Joined",
            timestamp=True,
        )
        em.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)

        em.add_field(name="Guild Name", value=guild.name, inline=False)
        em.add_field(
            name="Members",
            value=len([m for m in guild.members if not m.bot]),
            inline=False,
        )
        em.add_field(
            name="Bots", value=sum(member.bot for member in guild.members), inline=False
        )
        if guild.owner:
            em.add_field(
                name="Owner", value=f"{guild.owner} ({guild.owner.id})", inline=False
            )

        await self._send_bot_logs_embed(em)

        try:
            await asyncio.wait_for(guild.chunk(), timeout=5)
        except Exception:
            return

        if guild.member_count is not None and len(guild.members) < guild.member_count:
            return

        bots = sum(1 for m in guild.members if m.bot)
        humans = sum(1 for m in guild.members if not m.bot)
        total = bots + humans

        if (total > 0 and bots / total >= 0.70) or humans <= 3:
            self._auto_left.add(guild.id)
            try:
                ch = guild.system_channel or next(
                    (
                        c
                        for c in guild.text_channels
                        if c.permissions_for(guild.me).send_messages
                    ),
                    None,
                )
                if ch:
                    await ch.send(
                        "👋 I've automatically left this server due to a higher bot-to-member ratio or too few human members. Bye!"
                    )
                await guild.leave()
            except Exception:
                self._auto_left.discard(guild.id)
            return

    @Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        for cog_name in (
            "AntiAlts",
            "AntiAltsConfig",
            "WorkflowRunner",
            "AutoModeration",
            "AutoModConfig",
            "GuildLogs",
        ):
            cog = self.bot.get_cog(cog_name)
            clear_cache = getattr(cog, "clear_config_cache", None) or getattr(
                cog, "clear_cache", None
            )
            if callable(clear_cache):
                clear_cache(guild.id)

        leave_reason, was_auto_left = self._get_leave_reason(guild)

        em = red_embed(
            title="Guild Left",
            timestamp=True,
        )
        em.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)

        em.add_field(name="Guild Name", value=guild.name, inline=False)
        em.add_field(
            name="Members",
            value=guild.member_count or len(guild.members),
            inline=False,
        )
        if guild.owner:
            em.add_field(
                name="Owner", value=f"{guild.owner} ({guild.owner.id})", inline=False
            )
        em.add_field(
            name="Leave Type",
            value="Auto-left" if was_auto_left else "Removed / left",
            inline=False,
        )
        em.add_field(name="Reason", value=leave_reason, inline=False)

        await self._send_bot_logs_embed(em)


async def setup(bot: Zync) -> None:
    await bot.add_cog(Events(bot))
