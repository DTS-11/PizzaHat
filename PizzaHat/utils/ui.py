from typing import List

import discord
from discord.ext.commands import Context


class Paginator(discord.ui.View):
    def __init__(self, ctx: Context, embeds: List[discord.Embed]):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.message = None
        self.embeds = embeds
        self.current = 0

    async def on_timeout(self) -> None:
        if self.message:
            for child in self.children:
                child.disabled = True  # type: ignore

            await self.message.edit(view=self)  # type: ignore

    @discord.ui.button(emoji="⏮", style=discord.ButtonStyle.blurple)
    async def first(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current == 0:
            return await interaction.response.send_message(
                "Already at the first page ._.", ephemeral=True
            )
        await interaction.response.edit_message(embed=self.embeds[0], view=self)
        self.current = 0

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.blurple)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current == 0:
            return await interaction.response.send_message(
                "Already at the first page ._.", ephemeral=True
            )
        await interaction.response.edit_message(
            embed=self.embeds[self.current - 1], view=self
        )
        self.current -= 1

    @discord.ui.button(emoji="🛑", style=discord.ButtonStyle.red)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.message is not None:
            await interaction.message.delete()

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.blurple)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current + 1 == len(self.embeds):
            return await interaction.response.send_message(
                "Already at the last page ._.", ephemeral=True
            )
        await interaction.response.edit_message(
            embed=self.embeds[self.current + 1], view=self
        )
        self.current += 1

    @discord.ui.button(emoji="⏭", style=discord.ButtonStyle.blurple)
    async def last(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current + 1 == len(self.embeds):
            return await interaction.response.send_message(
                "Already at the last page ._.", ephemeral=True
            )
        await interaction.response.edit_message(embed=self.embeds[-1], view=self)
        self.current = len(self.embeds) - 1

    async def interaction_check(self, interaction):
        if interaction.user == self.ctx.author:
            return True
        await interaction.response.send_message("Not your command ._.", ephemeral=True)
