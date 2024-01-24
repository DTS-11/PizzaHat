import asyncio

import discord
from core.bot import PizzaHat
from core.cog import Cog
from discord import ButtonStyle, Interaction, ui
from discord.ext import commands
from discord.ext.commands import Context


class TicketView(ui.View):
    def __init__(self, bot):
        self.bot = bot
        super().__init__(timeout=None)

    async def get_staff_role(self, guild_id: int):
        await self.bot.db.fetchval(
            "SELECT role FROM staff_role WHERE guild_id=$1", guild_id
        )

    @ui.button(
        emoji="<:ticket_emoji:1004648922158989404>", custom_id="create_ticket_btn"
    )
    async def create_ticket(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_message(
            "Please wait while your ticket is being processed...", ephemeral=True
        )

        if interaction.guild is not None:
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(
                    read_messages=False
                ),
                interaction.guild.me: discord.PermissionOverwrite(read_messages=True),
                interaction.guild.get_role(self.get_staff_role(interaction.guild.id)): discord.PermissionOverwrite(read_messages=True),  # type: ignore
            }

            channel = await interaction.guild.create_text_channel(
                name=f"{interaction.user.name}-{interaction.user.id}",
                overwrites=overwrites,  # type: ignore
            )

            await interaction.response.edit_message(
                content=f"Ticket created! {channel.mention}"
            )

            em = discord.Embed(
                title="Ticket Created!",
                description=f"{interaction.user.mention} created a ticket.",
                color=0x456DD4,
            )
            await channel.send(embed=em, view=TicketSettings())


class TicketSettings(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Close", style=ButtonStyle.red, custom_id="close_ticket_btn")
    async def close_ticket(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_message("Closing ticket...")
        await asyncio.sleep(2)
        await interaction.channel.delete()  # type: ignore


class Tickets(Cog, emoji="🎟"):
    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot

    @commands.command(aliases=["tickets"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.has_permissions(manage_guild=True)
    async def ticket(self, ctx: Context):
        """Set up ticket system."""

        await ctx.send(
            "Please use the command `p!setup tickets <#channel>` to setup ticket system in this server."
        )


async def setup(bot):
    await bot.add_cog(Tickets(bot))
