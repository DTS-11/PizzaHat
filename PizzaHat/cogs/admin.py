import discord
from core.cog import Cog
from discord.ext import commands


class Admin(Cog, emoji=916988537264570368):
    """Admin configuration commands."""
    def __init__(self, bot):
        self.bot = bot   

    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def set(self, ctx):
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    @set.command(aliases=['log'])
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def logs(self, ctx, channel: discord.TextChannel):
        """
        Set a mod-log channel.
        To replace a log channel, simply run this command again.
        """

        try:
            await self.bot.db.execute("INSERT INTO modlogs (guild_id, channel_id) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET channel_id=$2", ctx.guild.id, channel.id)
            await ctx.send(f"{self.bot.yes} Mod-logs channel set to {channel}")

        except Exception as e:
            print(e)


async def setup(bot):
    await bot.add_cog(Admin(bot))
