"""Interactive help and companion information commands.

``/help`` builds its menu from the live application command tree, so every path
shown to users matches what Discord actually registers. The rest of the cog
keeps the standalone information surfaces together: ``/status``, ``/timezone``,
``/premium``, and the onboarding/invite panel.
"""

from __future__ import annotations

import datetime
import math
import time
from dataclasses import dataclass
from typing import Any, cast
from zoneinfo import ZoneInfo, available_timezones

import discord
from discord import ButtonStyle, Interaction, SelectOption, app_commands, ui
from discord.ext import commands
from discord.ext.commands import Context

from core.bot import Zync
from core.cog import Cog
from core.entitlements import Tier
from utils.config import (
    ADMIN_INVITE,
    REG_INVITE,
    REPO_LINK,
    SUPPORT_SERVER,
    UPGRADE_URL,
)
from utils.embed import ctx_embed, green_embed, orange_embed, red_embed

_TZ_NAMES: list[str] | None = None
HelpCommand = Any
PAGE_SIZE = 6

_CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "Moderation Actions": "Bans, kicks, timeouts, warnings and message controls",
    "Server Management": "Roles, channels, visibility, logs and insights",
    "Information": "Help, status, premium and general bot utilities",
    "Automation": "Workflows, automod and anti-alt configuration",
    "Community": "Tags, templates, tickets and role menus",
    "Quick Actions": "Right-click moderation shortcuts",
    "Other": "Additional commands",
}


def _emoji_text(value: Any) -> str:
    """Render an emoji for embed titles, field names, and select options."""
    return str(value) if value is not None else ""


def _command_emoji(command: HelpCommand, bot: Zync) -> Any | None:
    """Resolve the emoji declared on the cog that owns an app command.

    ``Cog.emoji`` uses ``bot.get_emoji()`` for numeric IDs, so guild emoji are
    fetched from the bot's cache and unknown IDs still render as partial emoji.
    """
    owner = getattr(command, "binding", None) or getattr(command, "cog", None)
    emoji = getattr(owner, "emoji", None)
    if emoji is not None:
        return emoji

    module = getattr(command, "module", "") or ""
    cog_name = module.rsplit(".", 1)[-1]
    cog = bot.get_cog(cog_name)
    return getattr(cog, "emoji", None)


def _category_emojis(categories: dict[str, list[HelpEntry]]) -> dict[str, Any]:
    """Pick the first cog-resolved emoji found in each help category."""
    result: dict[str, Any] = {}
    for category, entries in categories.items():
        for entry in entries:
            if entry.emoji is not None:
                result[category] = entry.emoji
                break
    return result


_MOD_ACTIONS = frozenset(
    {
        "ban",
        "unban",
        "banlist",
        "kick",
        "timeout",
        "warn",
        "warnings",
        "clear",
        "slowmode",
        "prune",
    }
)
_TOP_LEVEL_CATEGORIES: dict[str, str] = {
    "help": "Information",
    "status": "Information",
    "premium": "Information",
    "info": "Information",
    "antialt": "Automation",
    "automod": "Automation",
    "workflow": "Automation",
    "tag": "Community",
    "template": "Community",
    "tickets": "Community",
    "rolemenu": "Community",
    "emoji": "Community",
}


@dataclass(frozen=True)
class HelpEntry:
    """One discoverable command with ready-to-show usage text."""

    path: str
    category: str
    description: str
    usage: str
    example: str
    command: HelpCommand
    emoji: Any | None = None


def _timezone_names() -> list[str]:
    global _TZ_NAMES
    if _TZ_NAMES is None:
        _TZ_NAMES = sorted(available_timezones())
    return _TZ_NAMES


def _app_command_path(command: HelpCommand) -> str:
    """Return an application command's full slash path."""
    parts: list[str] = []
    current: HelpCommand | None = command
    while current is not None:
        parts.append(getattr(current, "name", ""))
        current = getattr(current, "parent", None)
    return " ".join(part for part in reversed(parts) if part)


def _command_description(command: HelpCommand) -> str:
    """Return a command's help text across hybrid, app and context commands."""
    return (
        getattr(command, "short_doc", None)
        or getattr(command, "help", None)
        or getattr(command, "description", None)
        or "No description provided."
    )


def _truncate(text: str, limit: int = 100) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else f"{collapsed[: limit - 1]}\u2026"


def _short_description(command: HelpCommand, limit: int = 70) -> str:
    """Return a compact one-line description for lists and select options."""
    return _truncate(_command_description(command), limit)


def _param_example(param: Any) -> str:
    """Pick a human-friendly example value for a command parameter."""
    name = getattr(param, "name", "value").casefold()
    choices = getattr(param, "choices", ()) or ()
    if choices:
        return str(getattr(choices[0], "value", choices[0]))
    if "member" in name or "user" in name or name in {"target", "targets"}:
        return "@member"
    if "role" in name:
        return "@role"
    if "channel" in name:
        return "#channel"
    if name == "duration":
        return "1h"
    if name in {"amount", "size", "days", "seconds", "warn_id", "user_id"}:
        return "10"
    if name in {"reason", "text", "nickname", "name", "source", "query"}:
        return "text"
    if name in {"soft", "clear", "bot_only", "locked", "hide", "hoist"}:
        return "true"
    return "value"


def _make_entry(command: HelpCommand, path: str, category: str, bot: Zync) -> HelpEntry:
    """Derive usage and an example from a registered command's parameters."""
    params = getattr(command, "_params", None)
    if params:
        required: list[str] = []
        optional: list[str] = []
        for param in params.values():
            label = str(getattr(param, "type", "value")).rsplit(".", 1)[-1]
            snippet = f"{getattr(param, 'name', 'value')}:<{label}>"
            if getattr(param, "required", False):
                required.append(snippet)
            else:
                optional.append(f"[{snippet}]")
        usage = f"/{path} " + " ".join(required + optional)
        example = f"/{path} " + " ".join(
            f"{getattr(param, 'name', 'value')}:{_param_example(param)}"
            for param in params.values()
        )
    else:
        signature = getattr(command, "signature", "") or ""
        usage = f"/{path} {signature}".strip()
        example = usage
    return HelpEntry(
        path=path,
        category=category,
        description=_short_description(command),
        usage=usage[:300],
        example=example[:300],
        command=command,
        emoji=_command_emoji(command, bot),
    )


def _build_entries(bot: Zync) -> dict[str, list[HelpEntry]]:
    """Build categorized help entries from the live command tree."""
    categories: dict[str, list[HelpEntry]] = {
        name: [] for name in _CATEGORY_DESCRIPTIONS
    }

    def add(command: HelpCommand, path: str, category: str) -> None:
        if getattr(command, "hidden", False):
            return
        categories.setdefault(category, []).append(
            _make_entry(command, path, category, bot)
        )

    for command in bot.tree.get_commands(type=discord.AppCommandType.chat_input):
        if command.name == "mod":
            for child in getattr(command, "commands", []):
                category = (
                    "Moderation Actions"
                    if child.name in _MOD_ACTIONS
                    else "Server Management"
                )
                add(child, f"mod {child.name}", category)
            continue

        category = _TOP_LEVEL_CATEGORIES.get(command.name, "Other")
        add(command, command.name, category)
        for child in getattr(command, "commands", []):
            add(child, f"{command.name} {child.name}", category)

    for menu in bot.tree.get_commands(type=discord.AppCommandType.user):
        add(menu, menu.name, "Quick Actions")

    for entries in categories.values():
        entries.sort(key=lambda entry: entry.path)
    return {name: entries for name, entries in categories.items() if entries}


def _find_entry(
    categories: dict[str, list[HelpEntry]], query: str
) -> tuple[str, HelpEntry] | None:
    """Find an entry by full path, falling back to a unique leaf name."""
    wanted = query.strip().lstrip("/").casefold()
    all_entries = [
        (category, entry)
        for category, entries in categories.items()
        for entry in entries
    ]
    for category, entry in all_entries:
        if entry.path.casefold() == wanted:
            return category, entry
    matches = [
        (category, entry)
        for category, entry in all_entries
        if entry.path.rsplit(" ", 1)[-1] == wanted
    ]
    return matches[0] if len(matches) == 1 else None


def _find_app_command(bot: Zync, query: str) -> HelpCommand | None:
    """Find an app command by its full path, falling back to a bare name."""
    wanted = query.strip().lstrip("/").casefold()
    commands = [
        command
        for command in bot.tree.walk_commands()
        if not getattr(command, "hidden", False)
    ]
    for command in commands:
        if _app_command_path(command).casefold() == wanted:
            return command
    for command in commands:
        if _app_command_path(command).rsplit(" ", 1)[-1] == wanted:
            return command
    return None


async def _home_help_embed(
    ctx: Context,
    categories: dict[str, list[HelpEntry]],
    emojis: dict[str, Any] | None = None,
) -> discord.Embed:
    """Build the compact landing embed; navigation lives in the view."""
    emojis = emojis or _category_emojis(categories)
    embed = await ctx_embed(ctx, title="Zync \u2014 Command Help", timestamp=True)
    embed.description = (
        "Zync is a deterministic Discord operations engine.\n\n"
        "Pick a category from the menu below, then select a command for usage "
        "and an example. Use `/help <command>` to jump straight to details.\n"
        "`<>` required  •  `[]` optional\n\n"
        f"[Invite]({REG_INVITE}) \u2022 [Support]({SUPPORT_SERVER}) \u2022 "
        f"[Source]({REPO_LINK})"
    )
    for category, entries in categories.items():
        label = f"{_emoji_text(emojis.get(category))} {category}".strip()
        embed.add_field(
            name=label,
            value=f"{_CATEGORY_DESCRIPTIONS.get(category, '')} \u2014 `{len(entries)}` commands",
            inline=False,
        )
    return embed


async def _category_help_embed(
    ctx: Context,
    category: str,
    entries: list[HelpEntry],
    page: int,
    pages: int,
    emojis: dict[str, Any] | None = None,
) -> discord.Embed:
    """Build one paginated category page (never one giant embed)."""
    prefix = _emoji_text((emojis or {}).get(category))
    title = f"{prefix} {category}".strip() if prefix else category
    embed = await ctx_embed(ctx, title=title, timestamp=True)
    embed.description = _CATEGORY_DESCRIPTIONS.get(category, "")
    start = page * PAGE_SIZE
    for entry in entries[start : start + PAGE_SIZE]:
        embed.add_field(name=f"/{entry.path}", value=entry.description, inline=False)
    embed.set_footer(
        text=f"Page {page + 1}/{pages}  \u2022  Select a command for usage",
        icon_url=ctx.author.display_avatar.url,
    )
    return embed


async def _entry_help_embed(
    ctx: Context,
    category: str,
    entry: HelpEntry,
    emojis: dict[str, Any] | None = None,
) -> discord.Embed:
    """Build the detail embed for a single command."""
    emoji = entry.emoji if entry.emoji is not None else (emojis or {}).get(category)
    prefix = _emoji_text(emoji)
    title = f"{prefix} /{entry.path}".strip() if prefix else f"/{entry.path}"
    embed = await ctx_embed(ctx, title=title, timestamp=True)
    embed.description = entry.description
    embed.add_field(name="Usage", value=f"```{entry.usage}```", inline=False)
    embed.add_field(name="Example", value=f"```{entry.example}```", inline=False)
    embed.add_field(name="Category", value=category, inline=True)
    cooldown = getattr(getattr(entry.command, "_buckets", None), "_cooldown", None)
    if cooldown is not None:
        embed.add_field(
            name="Cooldown",
            value=f"{cooldown.rate}x per {cooldown.per:.0f}s",
            inline=True,
        )
    embed.set_footer(
        text="Use Back to return to the category list.",
        icon_url=ctx.author.display_avatar.url,
    )
    return embed


class _HelpCategorySelect(ui.Select):
    """Top-level category picker."""

    def __init__(self, view: HelpView) -> None:
        self.help_view = view
        options = [
            SelectOption(
                label=category[:100],
                description=_truncate(description, 100),
                emoji=view.category_emojis.get(category),
            )
            for category, description in _CATEGORY_DESCRIPTIONS.items()
            if category in view.categories
        ]
        super().__init__(
            placeholder="Choose a category\u2026",
            min_values=1,
            max_values=1,
            options=options[:25],
            custom_id="help_category_select",
        )

    async def callback(self, interaction: Interaction) -> None:
        await self.help_view.show_category(interaction, self.values[0])


class _HelpCommandSelect(ui.Select):
    """Command picker for the current category page."""

    def __init__(self, view: HelpView) -> None:
        self.help_view = view
        super().__init__(
            placeholder="Choose a command\u2026",
            min_values=1,
            max_values=1,
            options=[SelectOption(label="Choose a category first", value="__home")],
            custom_id="help_command_select",
        )

    async def callback(self, interaction: Interaction) -> None:
        if self.values[0] == "__home":
            await self.help_view.go_home(interaction)
        else:
            await self.help_view.show_entry(interaction, self.values[0])


class HelpView(ui.View):
    """Paginated help browser with category/command selects and buttons."""

    def __init__(
        self,
        ctx: Context,
        bot: Zync,
        categories: dict[str, list[HelpEntry]],
        *,
        category: str | None = None,
        selected: str | None = None,
        category_emojis: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(timeout=180)
        self.ctx = ctx
        self.bot = bot
        self.categories = categories
        self.category = category
        self.selected = selected
        self.page = 0
        self.history: list[tuple[str | None, int, str | None]] = []
        self.message: discord.Message | None = None
        self.category_emojis = (
            _category_emojis(categories) if category_emojis is None else category_emojis
        )
        self.category_select = _HelpCategorySelect(self)
        self.command_select = _HelpCommandSelect(self)
        self.add_item(self.category_select)
        self.add_item(self.command_select)
        self._refresh_components()

    def _page_count(self) -> int:
        if self.category is None:
            return 1
        return max(1, math.ceil(len(self.categories[self.category]) / PAGE_SIZE))

    def _page_entries(self) -> list[HelpEntry]:
        if self.category is None:
            return []
        entries = self.categories[self.category]
        return entries[self.page * PAGE_SIZE : (self.page + 1) * PAGE_SIZE]

    def _refresh_components(self) -> None:
        if self.category is not None and self.selected is None:
            options = [
                SelectOption(
                    label=f"/{entry.path}"[:100],
                    description=entry.description[:100],
                    value=entry.path,
                    emoji=entry.emoji,
                )
                for entry in self._page_entries()
            ]
        else:
            options = [SelectOption(label="Choose a category", value="__home")]
        self.command_select.options = options[:25]

        disabled = {
            "help_prev": self.category is None or self.page <= 0,
            "help_next": self.category is None or self.page >= self._page_count() - 1,
            "help_back": not self.history,
        }
        for child in self.children:
            custom_id = getattr(child, "custom_id", "")
            if custom_id in disabled:
                cast(Any, child).disabled = disabled[custom_id]

    def _remember(self) -> None:
        self.history.append((self.category, self.page, self.selected))

    async def _render_embed(self) -> discord.Embed:
        if self.selected is not None:
            found = _find_entry(self.categories, self.selected)
            if found is not None:
                category, entry = found
                return await _entry_help_embed(
                    self.ctx, category, entry, self.category_emojis
                )
        if self.category is None:
            return await _home_help_embed(
                self.ctx, self.categories, self.category_emojis
            )
        return await _category_help_embed(
            self.ctx,
            self.category,
            self.categories[self.category],
            self.page,
            self._page_count(),
            self.category_emojis,
        )

    async def _render(self, interaction: Interaction) -> None:
        embed = await self._render_embed()
        self._refresh_components()
        await interaction.response.edit_message(embed=embed, view=self)

    async def show_category(self, interaction: Interaction, category: str) -> None:
        """Switch to a category, remembering where the user came from."""
        if category not in self.categories:
            await interaction.response.send_message(
                "That category is no longer available.", ephemeral=True
            )
            return
        self._remember()
        self.category = category
        self.page = 0
        self.selected = None
        await self._render(interaction)

    async def show_entry(self, interaction: Interaction, path: str) -> None:
        """Show usage and an example for one command."""
        self._remember()
        self.selected = path
        await self._render(interaction)

    @ui.button(
        label="Home",
        emoji="\N{HOUSE BUILDING}",
        style=ButtonStyle.blurple,
        custom_id="help_home",
    )
    async def _home_button(self, interaction: Interaction, button: ui.Button) -> None:
        """Button wrapper around :meth:`go_home`."""
        await self.go_home(interaction)

    async def go_home(self, interaction: Interaction) -> None:
        """Return to the category overview."""
        self._remember()
        self.category = None
        self.page = 0
        self.selected = None
        await self._render(interaction)

    @ui.button(
        label="Back",
        emoji="\N{LEFTWARDS ARROW WITH HOOK}",
        style=ButtonStyle.gray,
        custom_id="help_back",
    )
    async def go_back(self, interaction: Interaction, button: ui.Button) -> None:
        """Step back through previous categories and command details."""
        if not self.history:
            await interaction.response.send_message(
                "You are already at the home menu.", ephemeral=True
            )
            return
        self.category, self.page, self.selected = self.history.pop()
        await self._render(interaction)

    @ui.button(
        emoji="\N{BLACK LEFT-POINTING TRIANGLE}",
        style=ButtonStyle.gray,
        custom_id="help_prev",
    )
    async def previous_page(self, interaction: Interaction, button: ui.Button) -> None:
        """Show the previous page of the current category."""
        if self.category is None or self.page <= 0:
            await interaction.response.send_message(
                "There is no previous page.", ephemeral=True
            )
            return
        self.page -= 1
        self.selected = None
        await self._render(interaction)

    @ui.button(
        emoji="\N{BLACK RIGHT-POINTING TRIANGLE}",
        style=ButtonStyle.gray,
        custom_id="help_next",
    )
    async def next_page(self, interaction: Interaction, button: ui.Button) -> None:
        """Show the next page of the current category."""
        if self.category is None or self.page >= self._page_count() - 1:
            await interaction.response.send_message(
                "There is no next page.", ephemeral=True
            )
            return
        self.page += 1
        self.selected = None
        await self._render(interaction)

    @ui.button(emoji="\N{WASTEBASKET}", style=ButtonStyle.red, custom_id="help_delete")
    async def delete_menu(self, interaction: Interaction, button: ui.Button) -> None:
        """Close the help menu, including ephemeral menus that cannot be deleted."""
        message = interaction.message
        flags = getattr(message, "flags", None)
        ephemeral = bool(flags is not None and getattr(flags, "ephemeral", False))

        async def clear_components() -> None:
            payload = {"content": "Help menu closed.", "embeds": [], "view": None}
            try:
                if interaction.response.is_done():
                    await interaction.edit_original_response(**payload)
                else:
                    await interaction.response.edit_message(**payload)
            except discord.HTTPException:
                pass

        if message is not None and not ephemeral:
            await interaction.response.defer()
            try:
                await message.delete()
            except discord.HTTPException:
                await clear_components()
        else:
            await clear_components()
        self.stop()

    async def on_timeout(self) -> None:
        """Disable all components when the menu expires."""
        if self.message is None:
            return
        for child in self.children:
            cast(Any, child).disabled = True
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            pass

    async def interaction_check(self, interaction: Interaction) -> bool:
        """Only let the requester navigate the menu."""
        if interaction.user == self.ctx.author:
            return True
        await interaction.response.send_message(
            "This help menu isn't yours ._.", ephemeral=True
        )
        return False


class Help(Cog, emoji="\N{GEAR}"):
    """Help, status, timezone, billing and project links, kept together."""

    def __init__(self, bot: Zync):
        self.bot: Zync = bot
        self.bot.help_command = None  # type: ignore[assignment]

    # ── helpers ───────────────────────────────────────────────────────────────

    def _uptime(self) -> str:
        now = datetime.datetime.now(datetime.timezone.utc)
        delta = now - self.bot.uptime
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        if days:
            return f"{days}d {hours}h {minutes}m {seconds}s"
        return f"{hours}h {minutes}m {seconds}s"

    async def _tier(self, guild_id: int) -> Tier:
        service = getattr(self.bot, "entitlements", None)
        if service is not None:
            return await service.tier_for(guild_id)
        return Tier.FREE

    async def _respond(self, ctx: Context, embed: discord.Embed) -> None:
        """Send slash help privately; prefix invocations stay public."""
        interaction = ctx.interaction
        if interaction is not None and not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await ctx.send(embed=embed)

    # ── help ──────────────────────────────────────────────────────────────────

    async def _send_help(self, ctx: Context, query: str | None = None) -> None:
        categories = _build_entries(self.bot)
        category_emojis = _category_emojis(categories)
        view: HelpView | None = None

        if query:
            wanted = query.strip().casefold()
            for category, entries in categories.items():
                if category.casefold() == wanted:
                    embed = await _category_help_embed(
                        ctx,
                        category,
                        entries,
                        0,
                        math.ceil(len(entries) / PAGE_SIZE),
                        category_emojis,
                    )
                    view = HelpView(
                        ctx,
                        self.bot,
                        categories,
                        category=category,
                        category_emojis=category_emojis,
                    )
                    break
            else:
                found = _find_entry(categories, wanted)
                if found is not None:
                    category, entry = found
                    embed = await _entry_help_embed(
                        ctx, category, entry, category_emojis
                    )
                    view = HelpView(
                        ctx,
                        self.bot,
                        categories,
                        category=category,
                        selected=entry.path,
                        category_emojis=category_emojis,
                    )
                else:
                    embed = red_embed(
                        description=f"No command or category named `{query}` was found. "
                        "Use `/help` to browse."
                    )
        else:
            embed = await _home_help_embed(ctx, categories, category_emojis)
            view = HelpView(
                ctx,
                self.bot,
                categories,
                category_emojis=category_emojis,
            )

        if view is not None:
            view.message = await self._send_with_view(ctx, embed, view)
        else:
            await self._respond(ctx, embed)

    async def _send_with_view(
        self, ctx: Context, embed: discord.Embed, view: HelpView
    ) -> discord.Message:
        interaction = ctx.interaction
        if interaction is not None and not interaction.response.is_done():
            await interaction.response.send_message(
                embed=embed, view=view, ephemeral=True
            )
            return await interaction.original_response()
        return await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(
        name="help",
        aliases=["h"],
        help="Browse commands or get detailed help for one command/category.",
        with_app_command=True,
    )
    @app_commands.describe(query="Command or category to look up (optional)")
    async def help_command(self, ctx: Context, *, query: str | None = None) -> None:
        """Browse the interactive command menu or look up one command."""
        await self._send_help(ctx, query)

    @help_command.autocomplete("query")
    async def help_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Suggest real slash paths and category names."""
        current = current.casefold().lstrip("/")
        names: set[str] = set()
        for category, entries in _build_entries(self.bot).items():
            if not current or current in category.casefold():
                names.add(category)
            for entry in entries:
                if not current or current in entry.path.casefold():
                    names.add(entry.path)
        return [
            app_commands.Choice(name=name[:100], value=name)
            for name in sorted(names)[:25]
        ]

    # ── status ────────────────────────────────────────────────────────────────

    @commands.hybrid_command(
        name="status", aliases=["stats"], help="Show bot health and uptime."
    )
    async def status(self, ctx: Context) -> None:
        """Show bot health, uptime and server counts."""
        start = time.perf_counter()
        message = await ctx.send("Gathering status...")
        bot_ping = (time.perf_counter() - start) * 1000.0

        guilds = len(self.bot.guilds)
        members = sum(g.member_count or 0 for g in self.bot.guilds)
        em = await ctx_embed(ctx, title="Bot Status", timestamp=True)
        em.add_field(name="Uptime", value=f"`{self._uptime()}`", inline=True)
        em.add_field(
            name="Latency",
            value=f"API: `{round(self.bot.latency * 1000)} ms`\nBot: `{bot_ping:.0f} ms`",
            inline=True,
        )
        em.add_field(name="Guilds", value=f"`{guilds}`", inline=True)
        em.add_field(name="Members", value=f"`{members:,}`", inline=True)
        em.add_field(
            name="Commands",
            value=f"`{len(list(self.bot.walk_commands()))}`",
            inline=True,
        )
        em.add_field(name="Workflows", value="`/workflow list`", inline=True)
        await message.edit(content=None, embed=em)

    # ── timezone ──────────────────────────────────────────────────────────────

    @commands.hybrid_command(
        name="timezone",
        aliases=["tz", "time"],
        help="Show the current time in a timezone, or set your own IANA timezone.",
    )
    @app_commands.describe(
        timezone="Optional IANA timezone to set for yourself, e.g. Europe/London",
        member="Member whose timezone to look up (defaults to you)",
    )
    async def timezone(
        self,
        ctx: Context,
        timezone: str | None = None,
        member: discord.Member | discord.User | None = None,
    ) -> None:
        """Show a member's timezone, or set your own for scheduled workflows."""
        if timezone is not None:
            try:
                ZoneInfo(timezone)
            except (ValueError, KeyError):
                await ctx.send(
                    embed=red_embed(
                        description=(
                            f"{self.bot.no} `{timezone}` is not a valid IANA timezone. "
                            "See https://en.wikipedia.org/wiki/List_of_tz_database_time_zones"
                        )
                    )
                )
                return
            if self.bot.db is not None:
                await self.bot.db.execute(
                    "INSERT INTO user_preferences (user_id, timezone) VALUES ($1, $2) "
                    "ON CONFLICT (user_id) DO UPDATE SET timezone=$2, updated_at=NOW()",
                    ctx.author.id,
                    timezone,
                )
            await ctx.send(
                embed=green_embed(
                    description=f"{self.bot.yes} Timezone set to `{timezone}`."
                )
            )
            return

        member = member or ctx.author
        tz_name = None
        if self.bot.db is not None:
            tz_name = await self.bot.db.fetchval(
                "SELECT timezone FROM user_preferences WHERE user_id=$1", member.id
            )
        if not tz_name:
            await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} No timezone set for {member.mention}. "
                    "Use `/timezone timezone:Europe/London`."
                )
            )
            return
        try:
            now = datetime.datetime.now(ZoneInfo(tz_name))
        except (ValueError, KeyError):
            await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} `{tz_name}` is not a valid timezone."
                )
            )
            return
        await ctx.send(
            embed=await ctx_embed(
                ctx,
                description=(
                    f"\N{TIMER CLOCK} {member.mention}'s timezone is `{tz_name}`.\n"
                    f"Current time: `{now.strftime('%d-%m-%Y %H:%M:%S %Z')}`"
                ),
            )
        )

    @timezone.autocomplete("timezone")
    async def timezone_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        names = _timezone_names()
        current = current.casefold()
        matches = [n for n in names if current in n.casefold()][:25]
        return [app_commands.Choice(name=n, value=n) for n in matches]

    # ── premium / billing ─────────────────────────────────────────────────────

    @commands.hybrid_command(
        name="premium",
        help="Show this server's tier, billing status and workflow limits.",
    )
    async def premium(self, ctx: Context) -> None:
        """Show the server's current entitlement tier and billing status."""
        if ctx.guild is None:
            await ctx.send(
                embed=orange_embed(description="Premium status is server-only.")
            )
            return

        tier = await self._tier(ctx.guild.id)
        row = None
        if self.bot.db is not None:
            row = await self.bot.db.fetchrow(
                "SELECT tier, status, current_period_end, cancel_at_period_end "
                "FROM premium WHERE guild_id=$1",
                ctx.guild.id,
            )

        active = tier >= Tier.BASIC
        em = (
            green_embed(title="Premium Status")
            if active
            else red_embed(title="Premium Status")
        )
        em.description = (
            f"**Tier:** {tier.name}\n"
            f"**Billing:** {row['status'] if row else 'none'}\n"
            f"**Renews:** <t:{int(row['current_period_end'].timestamp())}:R>"
            if row and row["current_period_end"]
            else f"**Tier:** {tier.name}\n**Billing:** none"
        )
        if row and row["cancel_at_period_end"]:
            em.description += "\n**Cancels:** at the end of the current period."
        if not active:
            em.description += (
                "\n\nFree tier: 5 active workflows, 2 actions per workflow. "
                f"[Upgrade]({UPGRADE_URL})"
            )
        em.set_thumbnail(url="https://cdn3.emoji.gg/emojis/321814-cool-diamond.png")
        await ctx.send(embed=em)

    # ── onboarding ────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="invite", help="Add Zync to a server.")
    async def invite(self, ctx: Context) -> None:
        """Single onboarding panel for invites, support and source."""
        view = ui.View(timeout=None)
        if REG_INVITE:
            view.add_item(
                ui.Button(label="Invite", emoji="\N{LINK SYMBOL}", url=REG_INVITE)
            )
        if ADMIN_INVITE:
            view.add_item(
                ui.Button(label="Invite (Admin)", emoji="\N{GEAR}", url=ADMIN_INVITE)
            )
        if SUPPORT_SERVER:
            view.add_item(
                ui.Button(
                    label="Support Server",
                    emoji="\N{SPEECH BALLOON}",
                    url=SUPPORT_SERVER,
                )
            )

        description = "Add Zync to your server and automate your moderation workflows."
        if REG_INVITE:
            description += f"\n\n**[Invite]({REG_INVITE})**"
        if ADMIN_INVITE:
            description += f"\n**[Invite with admin permissions]({ADMIN_INVITE})**"
        if SUPPORT_SERVER:
            description += f"\n**[Support Server]({SUPPORT_SERVER})**"
        description += f"\n**[Source]({REPO_LINK})**"

        em = await ctx_embed(
            ctx,
            title="About Zync",
            description=description,
        )
        await ctx.send(embed=em, view=view)


async def setup(bot: Zync) -> None:
    await bot.add_cog(Help(bot))
