import discord
from core.bot import PizzaHat
from core.cog import Cog
from discord.ext import commands
from discord.ext.commands import Context


class Stars(Cog, emoji="⭐"):
    """A starboard system to upvote messages."""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot

    @commands.group(aliases=["star"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def starboard(self, ctx: Context):
        """
        Starboard commands.

        To use this command, you need Manage Server permission.
        """

        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    @starboard.command(name="channel")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def starboard_channel(self, ctx: Context, channel: discord.TextChannel):
        """
        Set the starboard channel.
        To replace this channel, simply run this command again.

        To use this command, you need Manage Server permission.
        """

        try:
            await self.bot.db.execute("INSERT INTO starboard (guild_id, channel_id) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET channel_id=$2", ctx.guild.id, channel.id)  # type: ignore
            await ctx.send(
                f"{self.bot.yes} Starboard channel set to {channel.mention}."
            )

        except Exception as e:
            await ctx.send(f"{self.bot.no} Something went wrong...")
            print(e)

    @starboard.command(name="count", aliases=["limit"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def starboard_count(self, ctx: Context, count: int):
        """
        Set the starboard star count. 
        Default count is set to 5.
        Minimum limit is 3 and maximum limit is 100.

        To use this command, you need Manage Server permission.
        """

        try:
            # if count < 3:
            #     return await ctx.send(f"{self.bot.no} Minimum limit is 3.")

            # elif count > 100:
            #     return await ctx.send(f"{self.bot.no} Maximum limit is 100.")

            await self.bot.db.execute("INSERT INTO starboard (guild_id, star_count) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET star_count=$2", ctx.guild.id, count)  # type: ignore
            await ctx.send(f"{self.bot.yes} Starboard star count set to `{count}`.")

        except Exception as e:
            await ctx.send(f"{self.bot.no} Something went wrong...")
            print(e)

    @starboard.command(name="self")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def starboard_self(self, ctx: Context, enable: bool):
        """
        Toggle self star. 
        Defaults to True.

        To use this command, you need Manage Server permission.
        """

        try:
            await self.bot.db.execute("INSERT INTO starboard (guild_id, self_star) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET self_star=$2", ctx.guild.id, enable)  # type: ignore
            await ctx.send(
                f"{self.bot.yes} Starboard self-star set to `{'true' if enable else 'false'}`."
            )

        except Exception as e:
            await ctx.send(f"{self.bot.no} Something went wrong...")
            print(e)


async def setup(bot):
    await bot.add_cog(Stars(bot))
