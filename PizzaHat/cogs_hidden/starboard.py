import datetime
from typing import Union

import discord
from async_lru import alru_cache
from core.bot import PizzaHat
from core.cog import Cog


def create_starboard_embed(message: discord.Message) -> discord.Embed:
    em = discord.Embed(
        description=message.content or "",
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
        icon_url=(message.author.avatar.url if message.author.avatar else None),
    )
    em.set_image(url=(message.attachments[0].url if message.attachments else None))
    return em


class StarboardEvents(Cog):
    """Starboard events cog"""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot

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

    @Cog.listener(name="on_raw_reaction_add")
    async def starboard_reaction_add(self, payload: discord.RawReactionActionEvent):
        guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
        channel = guild.get_channel(payload.channel_id) if guild else None

        if not channel or not guild:
            return

        message = await channel.fetch_message(payload.message_id)  # type: ignore

        if message.author.bot or payload.emoji.name != "⭐":
            return

        starboard_config = await self.get_starboard_config(guild.id)

        if starboard_config is not None:
            star_channel = guild.get_channel(starboard_config["channel_id"])

            if not star_channel:
                return

            star_count = starboard_config["star_count"]
            self_star = starboard_config["self_star"]

            for reaction in message.reactions:
                if reaction.count >= star_count:
                    if not self_star:
                        if message.author == payload.member:
                            return await message.remove_reaction(payload.emoji, payload.member)  # type: ignore
                    em = create_starboard_embed(message)

                    try:
                        em_id = (
                            await self.bot.db.fetchval(
                                "SELECT bot_msg_id FROM star_info WHERE guild_id=$1 AND user_msg_id=$2",
                                guild.id,
                                payload.message_id,
                            )
                            if self.bot.db
                            else None
                        )

                        if em_id is not None:
                            star_embed = await star_channel.fetch_message(em_id)  # type: ignore
                            await star_embed.edit(
                                content=f"⭐ **{reaction.count}** | {channel.mention}",
                                embed=em,
                            )

                        else:
                            star_embed = await star_channel.send(content=f"⭐ **{reaction.count}** | {channel.mention}", embed=em)  # type: ignore
                        (
                            await self.bot.db.execute(
                                "INSERT INTO star_info (guild_id, user_msg_id, bot_msg_id) VALUES ($1, $2, $3) ON CONFLICT ON CONSTRAINT star_info_pkey DO NOTHING",
                                guild.id,
                                payload.message_id,
                                star_embed.id,
                            )
                            if self.bot.db
                            else None
                        )

                    except discord.NotFound:
                        pass
                    except discord.Forbidden as e:
                        print(f"Error details in starboard reaction add: {e}")
                    except Exception as e:
                        print(f"Error in starboard reaction add: {e}")

    @Cog.listener(name="on_raw_reaction_remove")
    async def starboard_reaction_remove(self, payload: discord.RawReactionActionEvent):
        guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
        channel = guild.get_channel(payload.channel_id) if guild else None
        message = await channel.fetch_message(payload.message_id)  # type: ignore
        emoji = discord.utils.get(message.reactions, emoji="⭐")

        if message.author.bot:
            return

        if not channel or not guild:
            return

        em_id = (
            await self.bot.db.fetchval(
                "SELECT bot_msg_id FROM star_info WHERE guild_id=$1 AND user_msg_id=$2",
                guild.id,
                payload.message_id,
            )
            if self.bot.db
            else None
        )

        starboard_config = await self.get_starboard_config(guild.id)

        if starboard_config is not None:
            star_channel = guild.get_channel(starboard_config["channel_id"])

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
                    if self.bot.db
                    else None
                )
                return

            try:
                if emoji:
                    star_count = emoji.count

                    if star_count >= starboard_config["star_count"]:
                        em = create_starboard_embed(message)

                        star_embed = await star_channel.fetch_message(em_id)  # type: ignore
                        await star_embed.edit(
                            content=f"⭐ **{star_count}** | {channel.mention}", embed=em
                        )

            except discord.NotFound:
                pass
            except discord.Forbidden as e:
                print(f"Error details in starboard reaction remove: {e}")
            except Exception as e:
                print(f"Error in starboard reaction remove: {e}")

    @Cog.listener(name="on_message_delete")
    async def starred_msg_delete(self, msg: discord.Message):
        guild = msg.guild
        emoji = discord.utils.get(msg.reactions, emoji="⭐")

        if msg.author.bot or not guild or not emoji:
            return

        starboard_config = await self.get_starboard_config(guild.id)
        star_info = (
            await self.bot.db.fetchrow(
                "SELECT user_msg_id, bot_msg_id FROM star_info WHERE guild_id=$1",
                guild.id,
            )
            if self.bot.db
            else None
        )

        if starboard_config is not None:
            star_channel = guild.get_channel(starboard_config["channel_id"])

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
                        if self.bot.db
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
                        if self.bot.db
                        else None
                    )

                except discord.NotFound:
                    pass
                except discord.Forbidden:
                    pass
                except Exception as e:
                    print(f"Error in starboard msg delete event: {e}")


async def setup(bot):
    await bot.add_cog(StarboardEvents(bot))
