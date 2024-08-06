import discord
from discord.ext import commands
from discord.ext.commands import Context

from core.bot import PizzaHat
from core.cog import Cog
from utils.ui import TicketView


class Tickets(Cog, emoji=1268867314292625469):
    """Button ticket system for support and help!"""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_threads=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def tsetup(self, ctx: Context, channel: discord.TextChannel):
        """
        Setup the Ticket system.
        This sends the `Create Ticket` message which enables users to open a ticket.
        """

        em = discord.Embed(
            title="Create a ticket!",
            description="Click <:ticketbadge:1268879389324611595> to create/open a new ticket.",
            color=discord.Color.gold(),
        )
        em.set_thumbnail(url="https://i.imgur.com/mOTlTBy.png")

        view = TicketView(self.bot)
        await channel.send(embed=em, view=view)
        await ctx.message.add_reaction(self.bot.yes)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_threads=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def tadd(self, ctx: Context, user: discord.Member):
        """Adds a user to the current ticket thread."""

        if isinstance(ctx.channel, discord.Thread):
            await ctx.channel.add_user(user)
            await ctx.send(f"{self.bot.yes} Added {user.mention} to the ticket.")

        else:
            await ctx.send(f"{self.bot.no} You can only add people to a ticket thread.")

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_threads=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def tremove(self, ctx: Context, user: discord.Member):
        """Removes a user from the current ticket thread."""

        if isinstance(ctx.channel, discord.Thread):
            await ctx.channel.remove_user(user)
            await ctx.send(f"{self.bot.yes} Removed {user.mention} to the ticket.")

        else:
            await ctx.send(
                f"{self.bot.no} You can only remove people from a ticket thread."
            )

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_threads=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def tclose(self, ctx: Context):
        """Archives and locks the current ticket thread."""

        if isinstance(ctx.channel, discord.Thread):
            await ctx.send(f"{self.bot.yes} Closed the ticket.")
            await ctx.channel.edit(archived=True, locked=True)

        else:
            await ctx.send(
                f"{self.bot.no} You can only close tickets from ticket threads."
            )

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_threads=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def trename(self, ctx: Context, name: str):
        """Rename the current ticket thread."""

        if isinstance(ctx.channel, discord.Thread):
            await ctx.channel.edit(name=name)
            await ctx.send(f"{self.bot.yes} Renamed the ticket thread to `{name}`")

        else:
            await ctx.send(f"{self.bot.no} You can only rename ticket threads.")


async def setup(bot):
    await bot.add_cog(Tickets(bot))
