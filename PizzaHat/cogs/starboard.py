import discord
from core.bot import PizzaHat
from core.cog import Cog
from discord.ext import commands
from discord.ext.commands import Context


class Starboard(Cog, emoji=1220673915576389692):
    """A starboard system to upvote messages."""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot

    @commands.group()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def star(self, ctx: Context):
        """Starboard commands."""

        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    @star.command(name="channel")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def star_channel(self, ctx: Context, channel: discord.TextChannel):
        """
        Set the starboard channel.
        To replace this channel, simply run this command again.
        """

        (
            await self.bot.db.execute(
                "INSERT INTO star_config (guild_id, channel_id) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET channel_id=$2",
                ctx.guild.id,
                channel.id,
            )
            if self.bot.db and ctx.guild
            else None
        )
        await ctx.send(f"{self.bot.yes} Starboard channel set to {channel.mention}.")

    @star.command(name="count", aliases=["limit"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def star_count(self, ctx: Context, count: int):
        """
        Set the starboard star count.
        Default count is set to 5. Maximum limit is 100.
        """

        if count > 100:
            return await ctx.send(f"{self.bot.no} Maximum limit is 100.")

        if count == 0:
            return await ctx.send(f"{self.bot.no} Star count cannot be 0.")

        (
            await self.bot.db.execute(
                "INSERT INTO star_config (guild_id, star_count) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET star_count=$2",
                ctx.guild.id,
                count,
            )
            if self.bot.db and ctx.guild
            else None
        )
        await ctx.send(f"{self.bot.yes} Starboard star count set to `{count}`.")

    @star.command(name="self")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def star_self(self, ctx: Context, enable: bool):
        """
        Toggle self star.
        Accepts true/false values. Defaults to True.
        """

        if enable not in (True, False):
            return await ctx.send(
                f"{self.bot.no} Please enter a valid value. Accepts `true` or `false`."
            )

        (
            await self.bot.db.execute(
                "INSERT INTO star_config (guild_id, self_star) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET self_star=$2",
                ctx.guild.id,
                enable,
            )
            if self.bot.db and ctx.guild
            else None
        )
        await ctx.send(
            f"{self.bot.yes} Starboard self-star set to `{'true' if enable else 'false'}`."
        )


async def setup(bot):
    await bot.add_cog(Starboard(bot))
