from async_lru import alru_cache
from discord.ext import commands
from discord.ext.commands import Context

from core.bot import PizzaHat
from core.cog import Cog


class AutoModeration(Cog, emoji=1268880500248936491):
    """Configure Auto-Moderation in the server."""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot

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

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def automod(self, ctx: Context):
        """Automod config commands."""

        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    @automod.command(name="enable")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def automod_enable(self, ctx: Context):
        """Enables automod in the server."""

        (
            await self.bot.db.execute(
                "INSERT INTO automod (guild_id, enabled) VALUES ($1, $2)",
                ctx.guild.id,
                True,
            )
            if self.bot.db and ctx.guild
            else None
        )
        await ctx.send(f"{self.bot.yes} Auto-mod enabled.")

    @automod.command(name="disable")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def automod_disable(self, ctx: Context):
        """Disables automod in the server."""

        (
            await self.bot.db.execute(
                "DELETE FROM automod WHERE guild_id=$1", ctx.guild.id
            )
            if self.bot.db and ctx.guild
            else None
        )
        await ctx.send(f"{self.bot.yes} Auto-mod disabled.")


async def setup(bot):
    await bot.add_cog(AutoModeration(bot))
