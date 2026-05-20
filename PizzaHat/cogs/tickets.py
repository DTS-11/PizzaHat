from typing import Optional

import discord
from discord.ext import commands
from discord.ext.commands import Context

from core.bot import PizzaHat
from core.cog import Cog
from utils.embed import green_embed, red_embed
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
    async def tsetup(
        self,
        ctx: Context,
        channel: discord.TextChannel,
        name: str,
        support_role: Optional[discord.Role] = None,
    ):
        """
        Setup a Ticket panel in a channel.

        `name` is a label used to identify the panel.
        Optionally pass a `support_role` to be mentioned when a ticket is opened.
        """

        if not ctx.guild:
            return

        em = discord.Embed(
            title="Support Tickets",
            description=(
                "Need help? Click the button below to open a private support ticket.\n\n"
                "A member of our team will assist you as soon as possible."
            ),
            color=0x456DD4,
        )
        em.set_thumbnail(url="https://i.imgur.com/mOTlTBy.png")
        em.set_footer(text="One ticket per user at a time.")

        view = TicketView(self.bot)
        msg = await channel.send(embed=em, view=view)

        if self.bot.db:
            await self.bot.db.execute(
                """INSERT INTO ticket_panels (guild_id, channel_id, message_id, name, support_role_id)
                   VALUES ($1, $2, $3, $4, $5)""",
                ctx.guild.id,
                channel.id,
                msg.id,
                name,
                support_role.id if support_role else None,
            )

        await ctx.message.add_reaction(self.bot.yes)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def tpanels(self, ctx: Context):
        """Lists all ticket panels for this server."""

        if not ctx.guild:
            return

        if not self.bot.db:
            return await ctx.send(
                embed=red_embed(f"{self.bot.no} Database unavailable.")
            )

        panels = await self.bot.db.fetch(
            "SELECT * FROM ticket_panels WHERE guild_id=$1 ORDER BY id",
            ctx.guild.id,
        )

        if not panels:
            return await ctx.send(
                embed=red_embed(f"{self.bot.no} No ticket panels set up yet.")
            )

        em = discord.Embed(title="Ticket Panels", color=0x456DD4)
        for panel in panels:
            channel = ctx.guild.get_channel(panel["channel_id"])
            role = (
                ctx.guild.get_role(panel["support_role_id"])
                if panel["support_role_id"]
                else None
            )
            status = (
                f"{self.bot.yes} Enabled"
                if panel["enabled"]
                else f"{self.bot.no} Disabled"
            )
            em.add_field(
                name=f"#{panel['id']} — {panel['name']}",
                value=(
                    f"Channel: {channel.mention if channel else 'Unknown'}\n"
                    f"Support Role: {role.mention if role else 'None'}\n"
                    f"Status: {status}"
                ),
                inline=False,
            )

        await ctx.send(embed=em)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def tdelete(self, ctx: Context, panel_id: int):
        """Deletes a ticket panel by its ID (see `tpanels`)."""

        if not ctx.guild:
            return

        if not self.bot.db:
            return await ctx.send(
                embed=red_embed(f"{self.bot.no} Database unavailable.")
            )

        panel = await self.bot.db.fetchrow(
            "SELECT * FROM ticket_panels WHERE id=$1 AND guild_id=$2",
            panel_id,
            ctx.guild.id,
        )

        if not panel:
            return await ctx.send(
                embed=red_embed(f"{self.bot.no} Panel `#{panel_id}` not found.")
            )

        channel = ctx.guild.get_channel(panel["channel_id"])
        if isinstance(channel, discord.TextChannel):
            try:
                msg = await channel.fetch_message(panel["message_id"])
                await msg.delete()
            except discord.NotFound:
                pass

        await self.bot.db.execute(
            "DELETE FROM ticket_panels WHERE id=$1 AND guild_id=$2",
            panel_id,
            ctx.guild.id,
        )

        await ctx.send(
            embed=green_embed(f"{self.bot.yes} Deleted panel **{panel['name']}**.")
        )

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_threads=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def tadd(self, ctx: Context, user: discord.Member):
        """Adds a user to the current ticket thread."""

        if isinstance(ctx.channel, discord.Thread):
            await ctx.channel.add_user(user)
            await ctx.send(
                embed=green_embed(f"{self.bot.yes} Added {user.mention} to the ticket.")
            )

        else:
            await ctx.send(
                embed=red_embed(
                    f"{self.bot.no} You can only add people to a ticket thread."
                )
            )

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_threads=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def tremove(self, ctx: Context, user: discord.Member):
        """Removes a user from the current ticket thread."""

        if isinstance(ctx.channel, discord.Thread):
            await ctx.channel.remove_user(user)
            await ctx.send(
                embed=green_embed(
                    f"{self.bot.yes} Removed {user.mention} to the ticket."
                )
            )

        else:
            await ctx.send(
                embed=red_embed(
                    f"{self.bot.no} You can only remove people from a ticket thread."
                )
            )

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_threads=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def tclose(self, ctx: Context):
        """Archives and locks the current ticket thread."""

        if isinstance(ctx.channel, discord.Thread):
            await ctx.send(embed=green_embed(f"{self.bot.yes} Closed the ticket."))
            await ctx.channel.edit(archived=True, locked=True)

            if self.bot.db and ctx.guild:
                await self.bot.db.execute(
                    "UPDATE ticket_logs SET closed_at=NOW(), closed_by=$1 WHERE thread_id=$2 AND guild_id=$3",
                    ctx.author.id,
                    ctx.channel.id,
                    ctx.guild.id,
                )

        else:
            await ctx.send(
                embed=red_embed(
                    f"{self.bot.no} You can only close tickets from ticket threads."
                )
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
            await ctx.send(
                embed=green_embed(
                    f"{self.bot.yes} Renamed the ticket thread to `{name}`"
                )
            )

        else:
            await ctx.send(
                embed=red_embed(f"{self.bot.no} You can only rename ticket threads.")
            )


async def setup(bot: PizzaHat) -> None:
    await bot.add_cog(Tickets(bot))
