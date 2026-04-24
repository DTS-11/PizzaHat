from typing import List, Optional, Union

import chat_exporter
import discord
from discord import ButtonStyle, Interaction, ui
from discord.ext import commands
from discord.ext.commands import Context

from core.bot import Tier
from utils.custom_checks import _tier_cache
from utils.embed import normal_embed


# credits to Nirlep's EpicBot paginator system!
# https://github.com/Nirlep5252/EpicBot/blob/main/utils/ui.py#L70
class Paginator(ui.View):
    def __init__(
        self,
        ctx: Context,
        embeds: List[discord.Embed],
        file_paths: Optional[List[str]] = None,
    ):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.embeds = embeds
        self.file_paths = file_paths
        self.current = 0

    def get_current_file(self):
        if self.file_paths and self.current < len(self.file_paths):
            return discord.File(
                self.file_paths[self.current], filename=f"image_{self.current + 1}.png"
            )
        return None

    async def update_message(self, interaction: Interaction):
        file = self.get_current_file()
        embed = self.embeds[self.current]
        if file:
            embed.set_image(url=f"attachment://image_{self.current + 1}.png")
        await interaction.response.edit_message(
            embed=embed, attachments=[file] if file else [], view=self
        )

    @ui.button(label="<<", style=ButtonStyle.gray)
    async def first(self, interaction: Interaction, button: ui.Button):
        if self.current == 0:
            return await interaction.response.send_message(
                "Already at the first page ._.", ephemeral=True
            )
        self.current = 0
        await self.update_message(interaction)

    @ui.button(label="Back", style=ButtonStyle.blurple)
    async def back(self, interaction: Interaction, button: ui.Button):
        if self.current == 0:
            return await interaction.response.send_message(
                "Already at the first page ._.", ephemeral=True
            )
        self.current -= 1
        await self.update_message(interaction)

    @ui.button(emoji="🛑", style=ButtonStyle.red)
    async def delete(self, interaction: Interaction, button: ui.Button):
        if interaction.message is not None:
            await interaction.message.delete()

    @ui.button(label="Next", style=ButtonStyle.blurple)
    async def next(self, interaction: Interaction, button: ui.Button):
        if self.current + 1 == len(self.embeds):
            return await interaction.response.send_message(
                "Already at the last page ._.", ephemeral=True
            )
        self.current += 1
        await self.update_message(interaction)

    @ui.button(label=">>", style=ButtonStyle.gray)
    async def last(self, interaction: Interaction, button: ui.Button):
        if self.current + 1 == len(self.embeds):
            return await interaction.response.send_message(
                "Already at the last page ._.", ephemeral=True
            )
        self.current = len(self.embeds) - 1
        await self.update_message(interaction)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user == self.ctx.author:
            return True
        await interaction.response.send_message(
            content="Not your command ._.", ephemeral=True
        )
        return False


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

        if isinstance(interaction.channel, discord.TextChannel):
            thread = await interaction.channel.create_thread(
                name=f"ticket-{interaction.user}",
                reason=f"Ticket created by {interaction.user}",
                invitable=False,  # type: ignore
            )
            await thread.add_user(interaction.user)

            if self.bot.db:
                await self.bot.db.execute(
                    "INSERT INTO ticket_logs (guild_id, thread_id, creator_id) VALUES ($1, $2, $3)",
                    interaction.guild.id,
                    thread.id,
                    interaction.user.id,
                )

            em = normal_embed(
                title="Ticket created!",
                description=f"Welcome {interaction.user.mention} `[{interaction.user}]`. Support team will get back to you shortly.",
                timestamp=True,
            )
            em.set_footer(
                text=interaction.user,
                icon_url=(
                    interaction.user.avatar.url if interaction.user.avatar else None
                ),
            )

            await thread.send(
                content=f"{interaction.user.mention}",
                embed=em,
                view=TicketSettings(thread.id, self.bot),
            )
            self.thread_id = thread.id


class TicketSettings(ui.View):
    def __init__(self, thread_id: int, bot):
        self.thread_id = thread_id
        self.bot = bot
        super().__init__(timeout=None)

    async def check_premium(self, guild_id: int) -> bool:
        cached_tier = _tier_cache.get(guild_id)
        if cached_tier is None and self.bot.db is not None:
            row = await self.bot.db.fetchrow(
                "SELECT tier FROM premium WHERE guild_id=$1", guild_id
            )
            if row:
                cached_tier = Tier(row["tier"])
                _tier_cache[guild_id] = cached_tier
            else:
                cached_tier = Tier.FREE
                _tier_cache[guild_id] = Tier.FREE

        return cached_tier is not None and cached_tier >= Tier.BASIC

    @ui.button(
        label="Close Ticket",
        emoji="🔐",
        style=ButtonStyle.red,
        custom_id="close_ticket_btn",
    )
    async def close_ticket(self, interaction: Interaction, button: ui.Button):
        if interaction.guild is None:
            return

        member = interaction.guild.get_member(interaction.user.id)
        if not member or not (
            member.guild_permissions.manage_threads
            or member.guild_permissions.manage_channels
        ):
            return await interaction.response.send_message(
                "You need **Manage Threads** or **Manage Channels** permission to close tickets.",
                ephemeral=True,
            )

        thread = interaction.guild.get_thread(self.thread_id)

        if thread:
            await interaction.response.send_message(
                content="Ticket thread has been archived!"
            )
            await thread.edit(archived=True, locked=True)

            if self.bot.db:
                await self.bot.db.execute(
                    "UPDATE ticket_logs SET closed_at=NOW(), closed_by=$1 WHERE thread_id=$2 AND guild_id=$3",
                    interaction.user.id,
                    self.thread_id,
                    interaction.guild.id,
                )
        else:
            await interaction.followup.send(content="Unable to find ticket thread!")

    @ui.button(
        label="Transcript",
        emoji="📝",
        style=ButtonStyle.blurple,
        custom_id="ticket_transcript_btn",
    )
    async def ticket_transcript(self, interaction: Interaction, button: ui.Button):
        if interaction.guild is None:
            return

        is_premium = await self.check_premium(interaction.guild.id)
        if not is_premium:
            return await interaction.response.send_message(
                "This feature is for **Basic** or **Pro** tiers only.\n"
                "Purchase [here](https://pizzahat.vercel.app/premium)",
                ephemeral=True,
            )

        thread = interaction.guild.get_thread(self.thread_id)

        if thread:
            await chat_exporter.quick_export(thread)
        else:
            await interaction.followup.send(
                content="Unable to generate transcript for this ticket."
            )
