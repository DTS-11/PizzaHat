import datetime
import os
from typing import Union

import discord
from async_lru import alru_cache
from core.bot import PizzaHat
from core.cog import Cog
from dotenv import load_dotenv

load_dotenv()

LOG_CHANNEL = 980151632199299092
DLIST_TOKEN = os.getenv("DLIST_AUTH")


class Events(Cog):
    """Events cog"""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot
        # bot.loop.create_task(self.update_stats())

    @alru_cache()
    async def get_starboard_config(self, guild_id: int) -> Union[dict, None]:
        data = (
            await self.bot.db.fetchrow(
                "SELECT channel_id, star_count, self_star FROM star_config WHERE guild_id=$1",
                guild_id,
            )
            if self.bot.db
            else None
        )

        return (
            {
                "channel_id": data["channel_id"],
                "star_count": data["star_count"],
                "self_star": data["self_star"],
            }
            if data
            else None
        )

    # @tasks.loop(hours=24)
    # async def update_stats(self):
    #     try:
    #         # Top.gg
    #         await self.bot.wait_until_ready()
    #         self.topggpy = topgg.DBLClient(self, os.getenv("DBL_TOKEN"), autopost=True)  # type: ignore
    #         await self.topggpy.post_guild_count()
    #         print(f"Posted server count: {self.topggpy.guild_count}")

    #     except Exception as e:
    #         print(f"Failed to post server count\n{e.__class__.__name__}: {e}")

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

        em = discord.Embed(
            title="Guild Joined",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(),
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

        channel = self.bot.get_channel(LOG_CHANNEL)
        await channel.send(embed=em)  # type: ignore

    @Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        em = discord.Embed(
            title="Guild Left",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(),
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

        channel = self.bot.get_channel(LOG_CHANNEL)
        await channel.send(embed=em)  # type: ignore

    # ====== STARBOARD REACTION EVENTS ======

    @Cog.listener(name="on_raw_reaction_add")
    async def starboard_reaction_add(self, payload: discord.RawReactionActionEvent):
        guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
        channel = guild.get_channel(payload.channel_id) if guild else None

        if not channel:
            return

        message = await channel.fetch_message(payload.message_id)  # type: ignore

        if message.author.bot or payload.emoji.name != "⭐":
            return

        starboard_config = await self.get_starboard_config(guild.id) if guild else None

        if starboard_config is not None:
            star_channel = (
                guild.get_channel(starboard_config["channel_id"]) if guild else None
            )

            if not star_channel:
                return

            star_count = starboard_config["star_count"]
            self_star = starboard_config["self_star"]

            for reaction in message.reactions:
                if reaction.count >= star_count:
                    if not self_star:
                        if message.author == payload.member:
                            return await message.remove_reaction(payload.emoji, payload.member)  # type: ignore

                    em = discord.Embed(
                        description=message.content,
                        color=discord.Color.blurple(),
                        timestamp=datetime.datetime.now(),
                    )
                    em.set_footer(text=f"Message ID: {message.id}")

                    em.add_field(
                        name="Source",
                        value=f"[Jump to message!]({message.jump_url})",
                        inline=False,
                    )

                    for sticker in message.stickers:
                        em.add_field(
                            name=f"Sticker: `{sticker.name}`",
                            value=f"ID: [`{sticker.id}`]({sticker.url})",
                        )
                    if len(message.stickers) == 1:
                        em.set_thumbnail(url=message.stickers[0].url)

                    em.set_author(
                        name=message.author.name,
                        icon_url=(
                            message.author.avatar.url if message.author.avatar else None
                        ),
                    )
                    em.set_image(
                        url=(
                            message.attachments[0].url if message.attachments else None
                        )
                    )

                    try:
                        em_id = (
                            await self.bot.db.fetchval(
                                "SELECT bot_msg_id FROM star_info WHERE guild_id=$1 AND user_msg_id=$2",
                                guild.id,
                                payload.message_id,
                            )
                            if self.bot.db and guild
                            else None
                        )

                        if em_id is not None:
                            star_embed = await star_channel.fetch_message(em_id)  # type: ignore
                            await star_embed.edit(content=f"⭐ **{reaction.count}** | {channel.mention}", embed=em)  # type: ignore

                        else:
                            star_embed = await star_channel.send(content=f"⭐ **{reaction.count}** | {channel.mention}", embed=em)  # type: ignore
                        (
                            await self.bot.db.execute(
                                "INSERT INTO star_info (guild_id, user_msg_id, bot_msg_id) VALUES ($1, $2, $3) ON CONFLICT ON CONSTRAINT star_info_pkey DO NOTHING",
                                guild.id,
                                payload.message_id,
                                star_embed.id,
                            )
                            if guild and self.bot.db
                            else None
                        )

                    except discord.NotFound:
                        pass
                    except discord.Forbidden:
                        pass
                    except Exception as e:
                        print(f"Error in starboard reaction add: {e}")

    @Cog.listener(name="on_raw_reaction_remove")
    async def starboard_reaction_remove(self, payload: discord.RawReactionActionEvent):
        guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
        channel = guild.get_channel(payload.channel_id) if guild else None
        message = await channel.fetch_message(payload.message_id)  # type: ignore
        emoji = discord.utils.get(message.reactions, emoji="⭐")

        em_id = (
            await self.bot.db.fetchval(
                "SELECT bot_msg_id FROM star_info WHERE guild_id=$1 AND user_msg_id=$2",
                guild.id,
                payload.message_id,
            )
            if self.bot.db and guild
            else None
        )

        if message.author.bot:
            return

        starboard_config = await self.get_starboard_config(guild.id) if guild else None

        if starboard_config is not None:
            star_channel = (
                guild.get_channel(starboard_config["channel_id"]) if guild else None
            )

            if not star_channel:
                return

            if not emoji:
                msg = await star_channel.fetch_message(em_id)  # type:ignore
                await msg.delete()
                (
                    await self.bot.db.execute(
                        "DELETE FROM star_info WHERE guild_id=$1 AND bot_msg_id=$2",
                        guild.id,
                        em_id,
                    )
                    if self.bot.db and guild
                    else None
                )
                return

            star_count = starboard_config["star_count"]
            self_star = starboard_config["self_star"]

            try:
                for reaction in message.reactions:
                    if reaction.count < star_count:
                        if not self_star:
                            if message.author == payload.member:
                                return await message.remove_reaction(payload.emoji, payload.member)  # type: ignore

                        star_embed = await star_channel.fetch_message(em_id)  # type: ignore
                        await star_embed.edit(content=f"⭐ **{reaction.count}** | {channel.mention}")  # type: ignore

            # except discord.NotFound:
            #     pass
            # except discord.Forbidden:
            #     pass
            except Exception as e:
                print(f"Error in starboard reaction remove: {e}")

    @Cog.listener(name="on_message_delete")
    async def starred_msg_delete(self, msg: discord.Message):
        if msg.author.bot:
            return

        guild = msg.guild
        starboard_config = await self.get_starboard_config(guild.id) if guild else None
        star_info = (
            await self.bot.db.fetchrow(
                "SELECT user_msg_id, bot_msg_id FROM star_info WHERE guild_id=$1",
                guild.id,
            )
            if self.bot.db and guild
            else None
        )

        if starboard_config is not None:
            star_channel = (
                guild.get_channel(starboard_config["channel_id"]) if guild else None
            )

            if not star_channel:
                return

            if star_info is not None:
                try:
                    em_id = (
                        await self.bot.db.fetchval(
                            "SELECT bot_msg_id FROM star_info WHERE guild_id=$1 AND user_msg_id=$2",
                            guild.id,
                            msg.id,
                        )
                        if self.bot.db and guild
                        else None
                    )

                    star_embed = await star_channel.fetch_message(em_id)  # type: ignore
                    await star_embed.delete()
                    (
                        await self.bot.db.execute(
                            "DELETE FROM star_info WHERE guild_id=$1 AND bot_msg_id=$2",
                            guild.id,
                            em_id,
                        )
                        if self.bot.db and guild
                        else None
                    )

                except discord.NotFound:
                    pass
                except discord.Forbidden:
                    pass
                except Exception as e:
                    print(f"Error in starboard msg delete event: {e}")

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
