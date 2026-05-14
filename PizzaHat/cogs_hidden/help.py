from __future__ import annotations

from typing import Union

import discord
from discord import ButtonStyle, Interaction, app_commands, ui
from discord.ext import commands

from core.bot import PizzaHat
from core.cog import Cog
from core.database import get_prefix
from utils.config import COG_EXCEPTIONS, REG_INVITE, SUPPORT_SERVER, TOPGG_VOTE
from utils.embed import ctx_embed


async def bot_help_embed(ctx: commands.Context) -> discord.Embed:
    prefix = await get_prefix(ctx.bot.db, ctx.guild.id if ctx.guild else 0) or "p!"
    em = await ctx_embed(ctx, title=f"{ctx.bot.user.name}", timestamp=True)
    em.description = (
        f"{ctx.bot.description}\n\n"
        f"**Getting Started**\n"
        f"↳ Prefix: `{prefix}` or {ctx.bot.user.mention}\n"
        f"↳ Use `help [command]` for detailed command info\n"
        f"↳ Use `help [category]` to browse a category\n\n"
        f"**Links**\n"
        f"[Invite]({REG_INVITE})  •  [Vote]({TOPGG_VOTE})  •  [Support]({SUPPORT_SERVER})"
    )
    em.add_field(
        name="📂 Browse Categories",
        value="Use the dropdown below to explore all available command categories.",
        inline=False,
    )
    em.set_thumbnail(url=ctx.bot.user.avatar.url)
    em.set_author(
        name=ctx.bot.user.name,
        icon_url=ctx.bot.user.avatar.url if ctx.bot.user.avatar else None,
    )
    em.set_footer(
        text=f"Requested by {ctx.author}",
        icon_url=ctx.author.avatar.url if ctx.author.avatar else None,
    )
    return em


def cog_help_embed(cog: Cog | None) -> Union[discord.Embed, None]:
    if cog is None:
        return None

    em = discord.Embed(
        title=f"{cog.qualified_name}",
        description=cog.description if cog.description else "No description available.",
        color=cog.color,
    )
    em.set_thumbnail(url=cog.emoji.url if cog.emoji else "")
    em.set_footer(text="Use help [command] for detailed info on any command.")

    commands_info = []
    for cmd in sorted(cog.get_commands(), key=lambda c: c.name):
        if cmd.hidden:
            continue
        cmd_help = cmd.short_doc if cmd.short_doc else cmd.help or "No description."
        commands_info.append(f"`{cmd.name}` — {cmd_help}")

    if commands_info:
        em.add_field(
            name=f"Commands  [{len(commands_info)}]",
            value="\n".join(commands_info),
            inline=False,
        )

    return em


async def cmds_list_embed(ctx: commands.Context, mapping) -> discord.Embed:
    em = await ctx_embed(ctx, title="All Commands", timestamp=True)
    em.description = "A full listing of every available command, grouped by category."
    em.set_thumbnail(url=ctx.bot.user.avatar.url)
    em.set_footer(
        text=f"Requested by {ctx.author}",
        icon_url=ctx.author.avatar.url if ctx.author.avatar else None,
    )

    for cog, commands_ in mapping.items():
        if cog and cog.qualified_name not in COG_EXCEPTIONS:
            visible_commands = [
                command
                for command in sorted(commands_, key=lambda x: x.name)
                if not command.hidden
            ]
            if not visible_commands:
                continue

            cmds = "  ".join([f"`{command.name}`" for command in visible_commands])
            cog_emoji = cog.emoji if hasattr(cog, "emoji") else ""

            em.add_field(
                name=f"{cog_emoji} {cog.qualified_name}".strip(),
                value=cmds,
                inline=False,
            )

    return em


class HelpDropdown(ui.Select):
    def __init__(self, mapping: dict, ctx: commands.Context):
        self.cog_mapping = mapping
        self.ctx = ctx
        options = []

        for cog, _ in mapping.items():
            if cog and cog.qualified_name not in COG_EXCEPTIONS:
                options.append(
                    discord.SelectOption(
                        label=cog.qualified_name,
                        description=cog.description[:100] if cog.description else None,
                        emoji=cog.emoji if hasattr(cog, "emoji") else None,
                    )
                )

        super().__init__(
            placeholder="Select a category...",
            min_values=1,
            max_values=1,
            options=sorted(options, key=lambda x: x.label),
        )

    async def callback(self, interaction: Interaction):
        cog_name = self.values[0]
        cog = None

        for c, _ in self.cog_mapping.items():
            if c and c.qualified_name == cog_name:
                cog = c
                break

        embed = cog_help_embed(cog)
        if embed is None:
            await interaction.response.send_message(
                content="Unable to load that category.", ephemeral=True
            )
            return

        await interaction.response.edit_message(embed=embed)


class HelpView(ui.View):
    def __init__(self, mapping: dict, ctx: commands.Context):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.mapping = mapping
        self.message = None
        self.add_item(HelpDropdown(mapping, ctx))

    async def on_timeout(self) -> None:
        if self.message:
            for child in self.children:
                child.disabled = True  # type: ignore

            try:
                await self.message.edit(view=self)  # type: ignore
            except discord.HTTPException:
                pass

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user == self.ctx.author:
            return True

        await interaction.response.send_message(
            content="This help menu belongs to someone else.", ephemeral=True
        )
        return False

    @ui.button(label="Home", emoji="🏠", style=ButtonStyle.blurple)
    async def go_home(self, interaction: Interaction, button: ui.Button):
        embed = await bot_help_embed(self.ctx)
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="All Commands", emoji="📋", style=ButtonStyle.gray)
    async def cmds_list(self, interaction: Interaction, button: ui.Button):
        embed = await cmds_list_embed(self.ctx, self.mapping)
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(emoji="🗑", style=ButtonStyle.red)
    async def delete_menu(self, interaction: Interaction, button: ui.Button):
        if interaction.message is not None:
            await interaction.message.delete()
            self.stop()


class Help(Cog, emoji="\N{BLACK QUESTION MARK ORNAMENT}"):
    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot
        self.bot.help_command = None

    def _get_mapping(self) -> dict[Cog, list[commands.Command]]:
        mapping: dict[Cog, list[commands.Command]] = {}
        for cog in self.bot.cogs.values():
            if not isinstance(cog, Cog):
                continue

            cog_commands = [cmd for cmd in cog.get_commands() if not cmd.hidden]
            if cog_commands:
                mapping[cog] = cog_commands

        return mapping

    def _find_cog(self, name: str) -> Cog | None:
        lookup = name.casefold()
        for cog in self.bot.cogs.values():
            if isinstance(cog, Cog) and cog.qualified_name.casefold() == lookup:
                return cog

        return None

    async def _send_bot_help(self, ctx: commands.Context) -> None:
        mapping = self._get_mapping()
        view = HelpView(mapping, ctx)
        embed = await bot_help_embed(ctx)
        view.message = await ctx.send(embed=embed, view=view)  # type: ignore

    async def _send_command_help(
        self, ctx: commands.Context, command: commands.Command
    ) -> None:
        prefix = "/" if ctx.interaction else ctx.clean_prefix
        title = f"{prefix}{command.qualified_name} {command.signature}".strip()

        embed = await ctx_embed(ctx, title=title)

        description_parts = [command.help or "No description available."]
        description_parts.append("\n```\n<> Required  |  [] Optional\n```")
        embed.description = "\n".join(description_parts)

        if command.aliases:
            embed.add_field(
                name="Aliases",
                value="  ".join([f"`{alias}`" for alias in command.aliases]),
                inline=False,
            )

        if cog := command.cog:
            embed.add_field(name="Category", value=cog.qualified_name, inline=True)

        if command._buckets and (cooldown := command._buckets._cooldown):
            embed.add_field(
                name="Cooldown",
                value=f"{cooldown.rate}x per {cooldown.per:.0f}s",
                inline=True,
            )

        await ctx.send(embed=embed)

    async def _send_group_help(
        self, ctx: commands.Context, group: commands.Group
    ) -> None:
        prefix = "/" if ctx.interaction else ctx.clean_prefix
        title = f"{prefix}{group.qualified_name} {group.signature}".strip()

        embed = await ctx_embed(
            ctx,
            title=title,
            description=(group.help or "No description available.")
            + "\n\n```\n<> Required  |  [] Optional\n```",
        )

        for command in sorted(group.commands, key=lambda c: c.name):
            if command.hidden:
                continue
            cmd_help = command.short_doc if command.short_doc else command.help
            embed.add_field(
                name=f"`{prefix}{command.qualified_name} {command.signature}`.strip()",
                value=cmd_help or "No description.",
                inline=False,
            )

        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="help",
        aliases=["h"],
        help="Help command for the bot",
        with_app_command=True,
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    @app_commands.describe(query="Command or category to get help for")
    async def help_command(self, ctx: commands.Context, *, query: str | None = None):
        """Help command for the bot."""

        if not query:
            await self._send_bot_help(ctx)
            return

        query = query.strip()
        if not query:
            await self._send_bot_help(ctx)
            return

        command = self.bot.get_command(query)
        if command:
            if isinstance(command, commands.Group):
                await self._send_group_help(ctx, command)
                return

            await self._send_command_help(ctx, command)
            return

        if cog := self._find_cog(query):
            embed = cog_help_embed(cog)
            if embed:
                await ctx.send(embed=embed)
                return

        await ctx.send(
            embed=discord.Embed(
                description=f"No command or category called `{query}` was found.",
                color=0xED4245,
            )
        )

    @help_command.autocomplete("query")
    async def help_autocomplete(
        self, interaction: Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        current_lower = current.casefold()
        choices: list[app_commands.Choice[str]] = []
        seen: set[str] = set()

        for command in self.bot.walk_commands():
            if command.hidden:
                continue

            name = command.qualified_name
            if current_lower and current_lower not in name.casefold():
                continue

            if name in seen:
                continue

            choices.append(app_commands.Choice(name=f"Command: {name}", value=name))
            seen.add(name)

            if len(choices) >= 25:
                return choices

        for cog in self.bot.cogs.values():
            if not isinstance(cog, Cog):
                continue
            if cog.qualified_name in COG_EXCEPTIONS:
                continue

            name = cog.qualified_name
            if current_lower and current_lower not in name.casefold():
                continue

            if name in seen:
                continue

            choices.append(app_commands.Choice(name=f"Category: {name}", value=name))
            seen.add(name)

            if len(choices) >= 25:
                break

        return choices


async def setup(bot: PizzaHat) -> None:
    await bot.add_cog(Help(bot))
    await bot.tree.sync()
