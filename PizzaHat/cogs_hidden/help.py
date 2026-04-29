from __future__ import annotations

from typing import Union

import discord
from core.bot import PizzaHat
from core.cog import Cog
from discord import ButtonStyle, Interaction, app_commands, ui
from discord.ext import commands
from utils.config import COG_EXCEPTIONS, REG_INVITE, SUPPORT_SERVER, TOPGG_VOTE
from utils.embed import normal_embed


def bot_help_embed(ctx: commands.Context) -> discord.Embed:
    em = normal_embed(
        title=f"{ctx.bot.user.name} Help",
        timestamp=True,
    )
    em.description = """
Hello, welcome to the help page!
Use the dropdown menu to select a category.\n
- Use `help [command]` for more info on a command.
- Use `help [category]` for more info on a category.
    """

    em.add_field(name="About me", value=ctx.bot.description, inline=False)
    em.add_field(
        name="Support Server",
        value=f"For more help, consider joining the official server over by [clicking here]({SUPPORT_SERVER}).",
        inline=False,
    )
    em.add_field(
        name="🔗 Links",
        value=f"**[Invite me]({REG_INVITE})** • **[Vote]({TOPGG_VOTE})**",
        inline=False,
    )

    em.set_thumbnail(url=ctx.bot.user.avatar.url)
    em.set_footer(
        text=f"Requested by {ctx.author}",
        icon_url=ctx.author.avatar.url if ctx.author.avatar else None,
    )

    return em


def cog_help_embed(cog: Cog | None) -> Union[discord.Embed, None]:
    if cog is None:
        return

    em = discord.Embed(
        title=cog.qualified_name,
        description=(cog.description if cog.description else "No description..."),
        color=cog.color,
    )
    em.set_thumbnail(url=cog.emoji.url if cog.emoji else "")
    em.set_footer(text="Use help [command] for more info.")

    commands_info = []
    for cmd in sorted(cog.get_commands(), key=lambda c: c.name):
        if cmd.hidden:
            continue
        cmd_help = cmd.short_doc if cmd.short_doc else cmd.help
        commands_info.append(f"<:arrow:1267380018116563016> `{cmd.name}` - {cmd_help}")

    commands_value = "\n".join(commands_info)
    if commands_value:
        em.description += f"\n### Commands\n{commands_value}"  # type: ignore

    return em


def cmds_list_embed(ctx: commands.Context, mapping) -> discord.Embed:
    em = normal_embed(
        title=f"{ctx.bot.user.name} Help",
        timestamp=True,
    )

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

            cmds = ", ".join([f"`{command.name}`" for command in visible_commands])
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
                        description=cog.description,
                        emoji=cog.emoji if hasattr(cog, "emoji") else None,
                    )
                )

        super().__init__(
            placeholder="Choose a category...",
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
            content="Not your help command ._.", ephemeral=True
        )
        return False

    @ui.button(label="Home", emoji="🏠", style=ButtonStyle.blurple)
    async def go_home(self, interaction: Interaction, button: ui.Button):
        embed = bot_help_embed(self.ctx)
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Commands List", emoji="📜", style=ButtonStyle.blurple)
    async def cmds_list(self, interaction: Interaction, button: ui.Button):
        embed = cmds_list_embed(self.ctx, self.mapping)
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Delete Menu", emoji="🛑", style=ButtonStyle.red)
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
        view.message = await ctx.send(embed=bot_help_embed(ctx), view=view)  # type: ignore

    async def _send_command_help(
        self, ctx: commands.Context, command: commands.Command
    ) -> None:
        prefix = "/" if ctx.interaction else ctx.clean_prefix
        title = f"{prefix}{command.qualified_name} {command.signature}".strip()

        embed = normal_embed(
            title=title,
            description=(command.help or "No help found...")
            + "\n\n```ml\n<> Required Argument | [] Optional Argument\n```",
        )

        if command.aliases:
            embed.add_field(
                name="Aliases",
                value=", ".join([f"`{alias}`" for alias in command.aliases]),
                inline=False,
            )

        if cog := command.cog:
            embed.add_field(name="Category", value=cog.qualified_name, inline=False)

        if command._buckets and (cooldown := command._buckets._cooldown):
            embed.add_field(
                name="Cooldown",
                value=f"{cooldown.rate} per {cooldown.per:.0f} seconds",
                inline=False,
            )

        await ctx.send(embed=embed)

    async def _send_group_help(
        self, ctx: commands.Context, group: commands.Group
    ) -> None:
        prefix = "/" if ctx.interaction else ctx.clean_prefix
        title = f"{prefix}{group.qualified_name} {group.signature}".strip()

        embed = normal_embed(
            title=title,
            description=(group.help or "No help found...")
            + "\n\n```ml\n<> Required Argument | [] Optional Argument\n```",
        )

        for command in sorted(group.commands, key=lambda c: c.name):
            if command.hidden:
                continue
            cmd_help = command.short_doc if command.short_doc else command.help
            embed.add_field(
                name=f"{prefix}{command.qualified_name} {command.signature}".strip(),
                value=cmd_help or "No help found...",
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

        await ctx.send(f'No command or category called "{query}" was found.')

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


async def setup(bot):
    await bot.add_cog(Help(bot))
    await bot.tree.sync()
