import discord
from core.bot import PizzaHat
from core.cog import Cog
from discord.ext import commands
from discord.ext.commands import Context

from .tickets import TicketView


class Admin(Cog, emoji=916988537264570368):
    """Admin configuration commands."""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot

    @commands.group(invoke_without_command=True, aliases=["setup"])
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @commands.cooldown(1, 20, commands.BucketType.user)
    async def set(self, ctx: Context):
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    @set.command(aliases=["modrole"])
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def staffrole(self, ctx: Context, role: discord.Role):
        """Set a staff/mod-role."""

        try:
            await self.bot.db.execute("INSERT INTO staff_role (guild_id, role_id) VALUES ($1, $2)", ctx.guild.id, role.id)  # type: ignore

        except Exception as e:
            print(e)

    @set.command(aliases=["log"])
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def logs(self, ctx: Context, channel: discord.TextChannel):
        """
        Set a mod-log channel.
        To replace a log channel, simply run this command again.
        """

        try:
            await self.bot.db.execute("INSERT INTO modlogs (guild_id, channel_id) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET channel_id=$2", ctx.guild.id, channel.id)  # type: ignore
            await ctx.send(f"{self.bot.yes} Mod-logs channel set to {channel}")

        except Exception as e:
            print(e)

    @set.command(aliases=["ticket"])
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def tickets(self, ctx: Context, channel: discord.TextChannel):
        """
        Set up the Tickets system in the server by
        sending the `Create Ticket` message.
        """

        em = discord.Embed(
            title="Create a ticket!",
            description="Click <:ticket_emoji:1004648922158989404> to create/open a new ticket.",
            color=discord.Color.gold(),
        )
        em.set_thumbnail(url="https://i.imgur.com/mOTlTBy.png")

        await channel.send(embed=em, view=TicketView(self.bot))

    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def enable(self, ctx: Context):
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    @commands.command(aliases=["am"])
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def automod(self, ctx: Context):
        """
        Enables auto-mod in the server.
        """

        try:
            await self.bot.db.execute("INSERT INTO automod (guild_id, enabled) VALUES ($1, $2)", ctx.guild.id, True)  # type: ignore

        except Exception as e:
            print(e)


async def setup(bot):
    await bot.add_cog(Admin(bot))
