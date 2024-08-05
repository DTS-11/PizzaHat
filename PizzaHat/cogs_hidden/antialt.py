import datetime
import time
from typing import Optional, Union

import discord
from async_lru import alru_cache
from asyncpg import Record
from core.bot import PizzaHat
from core.cog import Cog
from discord.ext import commands


def datetime_to_sec(t: datetime.datetime):
    current_time = datetime.datetime.fromtimestamp(time.time())
    return round(
        round(time.time()) + (current_time - t.replace(tzinfo=None)).total_seconds()
    )


class AntiAltsConfig(Cog):
    """Anti alt config/logic cog."""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot

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
            assert isinstance(
                channel, discord.TextChannel
            ), "channel will always be a textchannel"
            return channel

    @alru_cache()
    async def check_if_aa_is_enabled(self, guild_id: int) -> Union[bool, None]:
        data = (
            await self.bot.db.fetchval(
                "SELECT enabled FROM antialt WHERE guild_id=$1", guild_id
            )
            if self.bot.db
            else None
        )
        if data is not None:
            return data

    @Cog.listener("on_member_join")
    async def antialt_member_join(self, member: discord.Member):
        aa_enabled_guild = await self.check_if_aa_is_enabled(member.guild.id)
        logs_channel = await self.get_logs_channel(member.guild.id)
        data = None

        if self.bot.db is not None and aa_enabled_guild:
            data: Optional[Record] = await self.bot.db.fetchrow(
                "SELECT min_age, restricted_role, level FROM antialt WHERE guild_id=$1",
                member.guild.id,
            )

        if member.bot or not data:
            return

        delv = (
            (
                datetime.datetime.now(datetime.timezone.utc)
                - member.created_at.replace(tzinfo=None)
            ).total_seconds()
        ) / (60 * 60 * 24)
        if delv >= data["min_age"]:
            return

        restricted_role = member.guild.get_role(data["restricted_role"])
        level = data["level"]

        if logs_channel is None or restricted_role is None:
            return

        account_age = (
            f"<t:{round(2 * time.time() - datetime_to_sec(member.created_at))}:F>"
        )

        embed = (
            discord.Embed(
                title="Alt Account Detected.",
                description=f"{member.mention} {discord.utils.escape_markdown(str(member))}\n\n**Account Age:** {account_age}",
                color=discord.Color.orange(),
                timestamp=datetime.datetime.now(),
            )
            .set_author(name=member, icon_url=member.display_avatar.url)
            .set_footer(text=f"ID: {member.id}")
        )

        if level == 1:
            await member.add_roles(restricted_role, reason="PizzaHat Anti-Alt System.")
            action_value = "RESTRICTED"
        elif level == 2:
            await member.kick(reason="PizzaHat Anti-Alt System.")
            action_value = "KICKED"
        else:
            await member.ban(reason="PizzaHat Anti-Alt System.")
            action_value = "BANNED"

        embed.add_field(name="Action:", value=action_value, inline=False)
        await logs_channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(AntiAltsConfig(bot))
