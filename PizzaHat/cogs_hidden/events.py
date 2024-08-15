import datetime

import discord

from core.bot import PizzaHat
from core.cog import Cog
from utils.config import LOGS_CHANNEL
from utils.embed import green_embed, red_embed


class Events(Cog):
    """Events cog"""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot
        # bot.loop.create_task(self.update_stats())

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
        if self.bot.db is not None:
            await self.bot.db.execute(
                """CREATE TABLE IF NOT EXISTS afk
                (guild_id BIGINT, user_id BIGINT, reason TEXT)"""
            )

            await self.bot.db.execute(
                """CREATE TABLE IF NOT EXISTS warnlogs
                (id SERIAL PRIMARY KEY, guild_id BIGINT, user_id BIGINT, mod_id BIGINT, reason TEXT)"""
            )

            await self.bot.db.execute(
                """CREATE TABLE IF NOT EXISTS logs_config
                (guild_id BIGINT PRIMARY KEY, module TEXT[] DEFAULT ARRAY['all'])"""
            )

            await self.bot.db.execute(
                """CREATE TABLE IF NOT EXISTS guild_logs
                (guild_id BIGINT PRIMARY KEY, channel_id BIGINT)"""
            )

            await self.bot.db.execute(
                """CREATE TABLE IF NOT EXISTS automod
                (guild_id BIGINT PRIMARY KEY, enabled BOOL DEFAULT false)"""
            )

            await self.bot.db.execute(
                """CREATE TABLE IF NOT EXISTS antialt
                (guild_id BIGINT PRIMARY KEY, enabled BOOL DEFAULT false, min_age INT, restricted_role BIGINT, level INT)"""
            )

            await self.bot.db.execute(
                """CREATE TABLE IF NOT EXISTS tags
                (guild_id BIGINT PRIMARY KEY, tag_name TEXT, content TEXT, creator BIGINT)"""
            )

            await self.bot.db.execute(
                """CREATE TABLE IF NOT EXISTS star_config
                (guild_id BIGINT PRIMARY KEY, channel_id BIGINT, star_count INT DEFAULT 5, self_star BOOL DEFAULT true)"""
            )

            await self.bot.db.execute(
                """CREATE TABLE IF NOT EXISTS star_info
                (guild_id BIGINT, user_msg_id BIGINT PRIMARY KEY, bot_msg_id BIGINT)"""
            )

            # await self.bot.db.execute(
            #     """CREATE TABLE IF NOT EXISTS welcome
            #     (guild_id BIGINT PRIMARY KEY, channel_id BIGINT, title TEXT, description TEXT, thumbnail TEXT, footer TEXT, author TEXT, color INT, welcome_img_enabled BOOL DEFAULT false)"""
            # )

    # ====== BOT PING MSG ======

    @Cog.listener()
    async def on_message(self, msg: discord.Message):
        if self.bot and self.bot.user is not None:
            bot_id = self.bot.user.id

            if msg.author.bot:
                return

            if self.bot.user == msg.author:
                return

            if msg.content in {f"<@{bot_id}>" or f"<@!{bot_id}>"}:
                em = discord.Embed(color=self.bot.color)
                em.add_field(
                    name="Hello! <a:wave_animated:783393435242463324>",
                    value=f"I'm {self.bot.user.name} — Your Ultimate Discord Companion.\nTo get started, my prefix is `p!` or `P!` or <@{bot_id}>",
                )

                await msg.channel.send(embed=em)

    # ====== BOT GUILD JOIN/LEAVE ======

    @Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        # if len([m for m in guild.members if m.bot]) > len(guild.members) / 2:
        #     try:
        #         await guild.text_channels[0].send(
        #             '👋 I have automatically left this server since it has a high bot to member ratio.'
        #         )
        #         await guild.leave()
        #     except:
        #         pass

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
        (
            em.add_field(
                name="Owner", value=f"{guild.owner} ({guild.owner.id})", inline=False
            )
            if guild.owner
            else "N/A"
        )

        channel = self.bot.get_channel(LOGS_CHANNEL)
        await channel.send(embed=em)  # type: ignore

    @Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        em = red_embed(
            title="Guild Left",
            timestamp=True,
        )
        em.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)

        em.add_field(name="Guild Name", value=guild.name, inline=False)
        (
            em.add_field(
                name="Owner", value=f"{guild.owner} ({guild.owner.id})", inline=False
            )
            if guild.owner
            else "N/A"
        )

        channel = self.bot.get_channel(LOGS_CHANNEL)
        await channel.send(embed=em)  # type: ignore

    # ====== MEMBER PING - AFK EVENT ======

    @Cog.listener(name="on_message")
    async def member_ping_in_afk(self, msg: discord.Message):
        if msg.author.bot or not msg.guild:
            return

        data = (
            await self.bot.db.fetch(
                "SELECT reason FROM afk WHERE guild_id=$1 AND user_id=$2",
                msg.guild.id,
                msg.author.id,
            )
            if self.bot.db
            else None
        )

        if data:
            (
                await self.bot.db.execute(
                    "DELETE FROM afk WHERE user_id=$1 AND guild_id=$2",
                    msg.author.id,
                    msg.guild.id,
                )
                if self.bot.db
                else None
            )
            return await msg.channel.send(
                f"Welcome back {msg.author.mention}.\nI have removed your AFK status."
            )

        if msg.mentions:
            for mention in msg.mentions:
                d2 = (
                    await self.bot.db.fetch(
                        "SELECT reason FROM afk WHERE guild_id=$1 AND user_id=$2",
                        msg.guild.id,
                        mention.id,
                    )
                    if self.bot.db
                    else None
                )

                if d2 and mention.id != msg.author.id:
                    em = discord.Embed(
                        title="Member AFK",
                        description=f"{mention.name} is AFK\n**Reason:** {d2[0]['reason']}",
                        color=discord.Color.og_blurple(),
                        timestamp=msg.created_at,
                    )
                    em.set_author(
                        name=mention.name,
                        icon_url=mention.avatar.url if mention.avatar else None,
                    )
                    em.set_footer(
                        text=msg.author,
                        icon_url=msg.author.avatar.url if msg.author.avatar else None,
                    )

                    await msg.channel.send(embed=em)


async def setup(bot):
    await bot.add_cog(Events(bot))
