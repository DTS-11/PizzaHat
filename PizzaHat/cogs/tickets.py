import discord
from core.bot import PizzaHat
from core.cog import Cog
from discord import ButtonStyle, Interaction, ui
from discord.ext import commands
from discord.ext.commands import Context


class TicketView(ui.View):
    def __init__(self, bot):
        self.bot = bot
        self.thread_id = None
        super().__init__(timeout=None)

    async def get_staff_role(self, guild_id: int) -> int:
        return await self.bot.db.fetchval(
            "SELECT role_id FROM staff_role WHERE guild_id=$1", guild_id
        )

    @ui.button(
        emoji="<:ticket_emoji:1004648922158989404>", custom_id="create_ticket_btn"
    )
    @commands.bot_has_permissions(create_private_threads=True)
    async def create_ticket(self, interaction: Interaction, button: ui.Button):
        if interaction.guild is not None:
            staff_role = interaction.guild.get_role(
                await self.get_staff_role(interaction.guild.id)
            )

            if staff_role is not None:
                thread = await interaction.channel.create_thread(  # type: ignore
                    name=f"{interaction.user}-ticket",
                    reason=f"Ticket created by {interaction.user}",
                    invitable=False,  # type: ignore
                )
                await thread.add_user(interaction.user)

                em = discord.Embed(
                    title="Ticket created!",
                    description=f"Welcome {interaction.user.mention} `[{interaction.user}]`. Support team will get back to you shortly.",
                    color=self.bot.color,
                    timestamp=interaction.created_at,
                )
                em.set_footer(
                    text=interaction.user,
                    icon_url=interaction.user.avatar.url
                    if interaction.user.avatar
                    else None,
                )

                await thread.send(
                    content=f"{interaction.user.mention}",
                    embed=em,
                    view=TicketSettings(thread.id),
                )
                self.thread_id = thread.id


class TicketSettings(ui.View):
    def __init__(self, thread_id: int):
        self.thread_id = thread_id
        super().__init__(timeout=None)

    @ui.button(label="Close", style=ButtonStyle.red, custom_id="close_ticket_btn")
    async def close_ticket(self, interaction: Interaction, button: ui.Button):
        if interaction.guild is not None:
            thread = interaction.guild.get_thread(self.thread_id)

            if thread:
                await interaction.response.send_message(
                    content="Ticket thread has been archived!"
                )
                await thread.edit(archived=True, locked=True)
            else:
                await interaction.followup.send("Unable to find ticket thread!")

    @ui.button(label="Reopen", style=ButtonStyle.green, custom_id="reopen_ticket_btn")
    async def reopen_ticket(self, interaction: Interaction, button: ui.Button):
        if interaction.guild is not None:
            thread = interaction.guild.get_thread(self.thread_id)

            if thread:
                await thread.edit(archived=False, locked=False)
                await interaction.response.send_message(
                    content="Ticket thread has been reopened!"
                )
            else:
                await interaction.followup.send("Unable to find ticket thread!")


class Tickets(Cog, emoji="🎟"):
    """Ticket system."""

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
