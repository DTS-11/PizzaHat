from typing import List, Optional, Union

import chat_exporter
import discord
from discord import ButtonStyle, Interaction, ui
from discord.ext import commands
from discord.ext.commands import Context


# credits to Nirlep's EpicBot paginator system!
# https://github.com/Nirlep5252/EpicBot/blob/main/utils/ui.py#L70
class Paginator(ui.View):
    def __init__(self, ctx: Context, embeds: List[discord.Embed]):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.embeds = embeds
        self.current = 0

    async def on_timeout(self) -> None:
        self.clear_items()

    @ui.button(label="<<", style=ButtonStyle.gray)
    async def first(self, interaction: Interaction, button: ui.Button):
        if self.current == 0:
            return await interaction.response.send_message(
                "Already at the first page ._.", ephemeral=True
            )
        await interaction.response.edit_message(embed=self.embeds[0], view=self)
        self.current = 0

    @ui.button(label="Back", style=ButtonStyle.blurple)
    async def back(self, interaction: Interaction, button: ui.Button):
        if self.current == 0:
            return await interaction.response.send_message(
                "Already at the first page ._.", ephemeral=True
            )
        await interaction.response.edit_message(
            embed=self.embeds[self.current - 1], view=self
        )
        self.current -= 1

    @ui.button(emoji="🛑", style=ButtonStyle.red)
    async def stop(self, interaction: Interaction, button: ui.Button):
        if interaction.message is not None:
            await interaction.message.delete()

    @ui.button(label="Next", style=ButtonStyle.blurple)
    async def next(self, interaction: Interaction, button: ui.Button):
        if self.current + 1 == len(self.embeds):
            return await interaction.response.send_message(
                "Already at the last page ._.", ephemeral=True
            )
        await interaction.response.edit_message(
            embed=self.embeds[self.current + 1], view=self
        )
        self.current += 1

    @ui.button(label=">>", style=ButtonStyle.gray)
    async def last(self, interaction: Interaction, button: ui.Button):
        if self.current + 1 == len(self.embeds):
            return await interaction.response.send_message(
                "Already at the last page ._.", ephemeral=True
            )
        await interaction.response.edit_message(embed=self.embeds[-1], view=self)
        self.current = len(self.embeds) - 1

    async def interaction_check(self, interaction: Interaction):
        if interaction.user == self.ctx.author:
            return True
        await interaction.response.send_message("Not your command ._.", ephemeral=True)


class ConfirmationView(ui.View):
    def __init__(
        self,
        ctx: Context,
        timeout: Optional[int] = 300,
        user: Optional[Union[discord.Member, discord.User]] = None,
    ):
        super().__init__(timeout=timeout)
        self.value = None
        self.ctx = ctx
        self.user = user or self.ctx.author

    @ui.button(label="Confirm", style=ButtonStyle.green)
    async def confirm(self, interaction: Interaction, button: ui.Button):
        self.value = True
        self.stop()

    @ui.button(label="Abort", style=ButtonStyle.red)
    async def abort(self, interaction: Interaction, button: ui.Button):
        self.value = False
        self.stop()

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user != self.user:
            await interaction.response.send_message(
                "This confirmation dialog is not for you.", ephemeral=True
            )
            return False
        return True


class TicketView(ui.View):
    def __init__(self, bot):
        self.bot = bot
        self.thread_id = None
        super().__init__(timeout=None)

    @ui.button(
        emoji="<:ticketbadge:1268879389324611595>", custom_id="create_ticket_btn"
    )
    @commands.bot_has_permissions(create_private_threads=True)
    async def create_ticket(self, interaction: Interaction, button: ui.Button):
        if not interaction.guild:
            return

        for thread in interaction.guild.threads:
            if thread.name == f"ticket-{interaction.user}" and not thread.archived:
                return await interaction.response.send_message(
                    f"You already have a ticket opened: {thread.mention}",
                    ephemeral=True,
                )

        thread = await interaction.channel.create_thread(  # type: ignore
            name=f"ticket-{interaction.user}",
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
            icon_url=(interaction.user.avatar.url if interaction.user.avatar else None),
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

    @ui.button(
        label="Close Ticket",
        emoji="🔐",
        style=ButtonStyle.red,
        custom_id="close_ticket_btn",
    )
    async def close_ticket(self, interaction: Interaction, button: ui.Button):
        if interaction.guild is not None:
            thread = interaction.guild.get_thread(self.thread_id)

            if thread:
                await interaction.response.send_message(
                    content="Ticket thread has been archived!"
                )
                await thread.edit(archived=True, locked=True)
            else:
                await interaction.followup.send(content="Unable to find ticket thread!")

    @ui.button(
        label="Transcript",
        emoji="📝",
        style=ButtonStyle.blurple,
        custom_id="ticket_transcript_btn",
    )
    async def ticket_transcript(self, interaction: Interaction, button: ui.Button):
        if interaction.guild is not None:
            thread = interaction.guild.get_thread(self.thread_id)

            if thread:
                msg = await chat_exporter.quick_export(thread)
                await chat_exporter.quick_link(thread, msg)
            else:
                await interaction.followup.send(
                    content="Unable to generate transcript for this ticket."
                )
