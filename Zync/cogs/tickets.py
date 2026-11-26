"""Ticket panel commands.

Panel setup and thread management go through :class:`TicketService`; Discord
UI and transcript rendering stay in ``utils.ui``.
"""

from __future__ import annotations

from typing import Optional

import discord
from discord.ext import commands
from discord.ext.commands import Context

from core.bot import Zync
from core.cog import Cog
from services import get_tickets
from services.tickets import TicketError
from utils.embed import green_embed, red_embed
from utils.ui import TicketView


class Tickets(Cog, emoji=1268867314292625469):
    """Button ticket system for support and help!"""

    def __init__(self, bot: Zync):
        self.bot: Zync = bot
        self.tickets = get_tickets(bot)

    async def _fail(self, ctx: Context, message: str) -> None:
        await ctx.send(embed=red_embed(f"{self.bot.no} {message}"))

    async def _managed_thread(self, ctx: Context) -> discord.Thread | None:
        """Ensure the current thread is a registered, open ticket."""

        if not isinstance(ctx.channel, discord.Thread) or ctx.guild is None:
            await self._fail(ctx, "You can only do this in a ticket thread.")
            return None
        try:
            await self.tickets.require_ticket(ctx.guild.id, ctx.channel.id)
        except TicketError as exc:
            await self._fail(ctx, str(exc))
            return None
        return ctx.channel

    @commands.hybrid_command()
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

        if not ctx.guild or not self.bot.db:
            return await self._fail(ctx, "Database unavailable.")

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
        panel = await self.tickets.create_panel(
            ctx.guild.id,
            channel.id,
            msg.id,
            name,
            support_role_id=support_role.id if support_role else None,
        )
        if panel is None:
            return await self._fail(ctx, "Database unavailable.")
        self.bot.add_view(view, message_id=msg.id)

        if ctx.interaction is None and ctx.message is not None:
            await ctx.message.add_reaction(self.bot.yes)
        else:
            await ctx.send(
                embed=green_embed(
                    f"{self.bot.yes} Ticket panel **{panel['name']}** created in {channel.mention}."
                )
            )

    @commands.hybrid_command()
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def tpanels(self, ctx: Context):
        """Lists all ticket panels for this server."""

        if not ctx.guild:
            return

        panels = await self.tickets.list_panels(ctx.guild.id)
        if not panels:
            return await self._fail(ctx, "No ticket panels set up yet.")

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

    @commands.hybrid_command()
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def tdelete(self, ctx: Context, panel_id: int):
        """Deletes a ticket panel by its ID (see `tpanels`)."""

        if not ctx.guild:
            return

        panel = await self.tickets.get_panel(ctx.guild.id, panel_id)
        if not panel:
            return await self._fail(ctx, f"Panel `#{panel_id}` not found.")

        channel = ctx.guild.get_channel(panel["channel_id"])
        if isinstance(channel, discord.TextChannel):
            try:
                msg = await channel.fetch_message(panel["message_id"])
                await msg.delete()
            except discord.NotFound:
                pass

        await self.tickets.delete_panel(ctx.guild.id, panel_id)
        await ctx.send(
            embed=green_embed(f"{self.bot.yes} Deleted panel **{panel['name']}**.")
        )

    @commands.hybrid_command()
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_threads=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def tadd(self, ctx: Context, user: discord.Member):
        """Adds a user to the current ticket thread."""

        thread = await self._managed_thread(ctx)
        if thread is None:
            return
        await thread.add_user(user)
        await ctx.send(
            embed=green_embed(f"{self.bot.yes} Added {user.mention} to the ticket.")
        )

    @commands.hybrid_command()
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_threads=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def tremove(self, ctx: Context, user: discord.Member):
        """Removes a user from the current ticket thread."""

        thread = await self._managed_thread(ctx)
        if thread is None:
            return
        await thread.remove_user(user)
        await ctx.send(
            embed=green_embed(f"{self.bot.yes} Removed {user.mention} from the ticket.")
        )

    @commands.hybrid_command()
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_threads=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def tclose(self, ctx: Context):
        """Archives and locks the current ticket thread."""

        thread = await self._managed_thread(ctx)
        if thread is None or ctx.guild is None:
            return
        await ctx.channel.edit(archived=True, locked=True)
        await self.tickets.close_ticket(ctx.guild.id, thread.id, ctx.author.id)
        await ctx.send(embed=green_embed(f"{self.bot.yes} Closed the ticket."))

    @commands.hybrid_command()
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_threads=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def trename(self, ctx: Context, name: str):
        """Rename the current ticket thread."""

        thread = await self._managed_thread(ctx)
        if thread is None or ctx.guild is None:
            return
        await thread.edit(name=name)
        await self.tickets.set_subject(ctx.guild.id, thread.id, name)
        await ctx.send(
            embed=green_embed(f"{self.bot.yes} Renamed the ticket thread to `{name}`")
        )


async def setup(bot: Zync) -> None:
    await bot.add_cog(Tickets(bot))
