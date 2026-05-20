from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import ButtonStyle, Interaction, SelectOption

from core.bot import PizzaHat
from core.cog import Cog

logger = logging.getLogger("bot")

DISCORD_MAX_ITEMS = 25


def _parse_emoji(raw: Optional[str]) -> Optional[discord.PartialEmoji]:
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("<") and raw.endswith(">"):
        try:
            animated = raw.startswith("<a:")
            name, emoji_id = raw.rsplit(":", 1)
            name = name.split(":")[-1]
            return discord.PartialEmoji(
                name=name, id=int(emoji_id[:-1]), animated=animated
            )
        except (ValueError, IndexError):
            return None
    return discord.PartialEmoji(name=raw)


def _item_label(item: dict, guild: Optional[discord.Guild]) -> str:
    label = item.get("label")
    if label:
        return label[:80]
    if guild:
        role = guild.get_role(item["role_id"])
        if role:
            return role.name[:80]
    return f"Role {item['role_id']}"


class RoleMenuButton(discord.ui.Button["RoleMenuView"]):
    def __init__(self, menu_id: int, item: dict, guild: Optional[discord.Guild]):
        super().__init__(
            style=ButtonStyle.secondary,
            label=_item_label(item, guild),
            emoji=_parse_emoji(item.get("emoji")),
            custom_id=f"rm:btn:{menu_id}:{item['role_id']}",
        )
        self.menu_id = menu_id
        self.role_id = item["role_id"]

    async def callback(self, interaction: Interaction) -> None:
        await _handle_button(interaction, self.menu_id, self.role_id)


class RoleMenuSelect(discord.ui.Select["RoleMenuView"]):
    def __init__(
        self,
        menu_id: int,
        menu: dict,
        items: list[dict],
        guild: Optional[discord.Guild],
    ):
        options = [
            SelectOption(
                label=_item_label(item, guild),
                value=str(item["role_id"]),
                description=(item.get("description") or None),
                emoji=_parse_emoji(item.get("emoji")),
            )
            for item in items
        ]
        if not options:
            options = [SelectOption(label="(empty)", value="0", default=False)]

        if menu.get("mode") == "single":
            min_values, max_values = 0, 1
        else:
            limit = menu.get("max_selections") or len(items) or 1
            max_values = max(1, min(limit, len(items) or 1, DISCORD_MAX_ITEMS))
            min_values = 0

        super().__init__(
            placeholder="Pick your roles…",
            min_values=min_values,
            max_values=max_values,
            options=options,
            custom_id=f"rm:sel:{menu_id}",
        )
        self.menu_id = menu_id

    async def callback(self, interaction: Interaction) -> None:
        await _handle_select(interaction, self.menu_id, self.values)


class RoleMenuView(discord.ui.View):
    """View used both for sending new menus and for persistent reattachment."""

    def __init__(self, menu: dict, items: list[dict], guild: Optional[discord.Guild]):
        super().__init__(timeout=None)
        menu_id = menu["id"]
        items = items[:DISCORD_MAX_ITEMS]

        if menu.get("type") == "dropdown":
            self.add_item(RoleMenuSelect(menu_id, menu, items, guild))
        else:
            for item in items:
                self.add_item(RoleMenuButton(menu_id, item, guild))


async def _fetch_menu(bot: PizzaHat, menu_id: int) -> Optional[dict]:
    if not bot.db:
        return None
    row = await bot.db.fetchrow("SELECT * FROM role_menus WHERE id=$1", menu_id)
    return dict(row) if row else None


async def _fetch_items(bot: PizzaHat, menu_id: int) -> list[dict]:
    if not bot.db:
        return []
    rows = await bot.db.fetch(
        "SELECT * FROM role_menu_items WHERE menu_id=$1 ORDER BY position, role_id",
        menu_id,
    )
    return [dict(r) for r in rows]


def build_embed(
    menu: dict, items: list[dict], guild: Optional[discord.Guild]
) -> discord.Embed:
    title = menu.get("title") or menu["name"]
    description = menu.get("description")
    if not description:
        bullets = []
        for item in items:
            label = _item_label(item, guild)
            emoji = item.get("emoji") or ""
            bullets.append(f"{emoji} <@&{item['role_id']}> — {label}".strip())
        description = "\n".join(bullets) or "No roles configured yet."
    return discord.Embed(title=title, description=description, color=0x456DD4)


async def _build_embed_with_template(
    bot: PizzaHat,
    menu: dict,
    items: list[dict],
    guild: Optional[discord.Guild],
) -> discord.Embed:
    """Build the menu embed, falling back to the inline title/description if no template."""

    from utils.embed import resolve_template

    fallback = build_embed(menu, items, guild)
    return await resolve_template(bot.db, menu.get("template_id"), fallback)


async def publish_menu(
    bot: PizzaHat,
    menu: dict,
    items: list[dict],
    channel: discord.abc.Messageable,
) -> discord.Message:
    """Post a new menu message and persist its IDs. Returns the sent message."""

    guild = getattr(channel, "guild", None)
    view = RoleMenuView(menu, items, guild)
    embed = await _build_embed_with_template(bot, menu, items, guild)
    message = await channel.send(embed=embed, view=view)
    if bot.db:
        await bot.db.execute(
            "UPDATE role_menus SET channel_id=$1, message_id=$2 WHERE id=$3",
            message.channel.id,
            message.id,
            menu["id"],
        )
    bot.add_view(view, message_id=message.id)
    return message


async def refresh_menu(bot: PizzaHat, menu_id: int) -> bool:
    """Rebuild the embed + view for an existing posted menu. No-op if not posted."""

    menu = await _fetch_menu(bot, menu_id)
    if not menu or not menu.get("message_id") or not menu.get("channel_id"):
        return False

    guild = bot.get_guild(menu["guild_id"])
    channel = bot.get_channel(menu["channel_id"]) if guild else None
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        return False

    items = await _fetch_items(bot, menu_id)
    view = RoleMenuView(menu, items, guild)
    embed = await _build_embed_with_template(bot, menu, items, guild)
    try:
        message = await channel.fetch_message(menu["message_id"])
        await message.edit(embed=embed, view=view)
    except (discord.NotFound, discord.Forbidden):
        return False

    bot.add_view(view, message_id=menu["message_id"])
    return True


async def _ensure_can_use(
    interaction: Interaction, menu: dict
) -> tuple[bool, discord.Member | None]:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "Role menus can only be used in a server.", ephemeral=True
        )
        return False, None

    if not menu.get("enabled", True):
        await interaction.response.send_message(
            "This role menu is disabled.", ephemeral=True
        )
        return False, None

    required = menu.get("required_role_id")
    if required:
        if not any(r.id == required for r in interaction.user.roles):
            await interaction.response.send_message(
                f"You need <@&{required}> to use this menu.", ephemeral=True
            )
            return False, None

    return True, interaction.user


async def _handle_button(interaction: Interaction, menu_id: int, role_id: int) -> None:
    bot: PizzaHat = interaction.client  # type: ignore[assignment]
    menu = await _fetch_menu(bot, menu_id)
    if not menu:
        await interaction.response.send_message(
            "This menu no longer exists.", ephemeral=True
        )
        return

    ok, member = await _ensure_can_use(interaction, menu)
    if not ok or not member or not interaction.guild:
        return

    role = interaction.guild.get_role(role_id)
    if not role:
        await interaction.response.send_message(
            "That role no longer exists.", ephemeral=True
        )
        return

    if (
        not interaction.guild.me.guild_permissions.manage_roles
        or role >= interaction.guild.me.top_role
    ):
        await interaction.response.send_message(
            f"I can't manage **{role.name}** — check my permissions and role position.",
            ephemeral=True,
        )
        return

    items = await _fetch_items(bot, menu_id)
    menu_role_ids = {it["role_id"] for it in items}
    user_role_ids = {r.id for r in member.roles}
    has_role = role.id in user_role_ids
    mode = menu.get("mode") or "multi"

    try:
        if has_role:
            await member.remove_roles(role, reason=f"Role menu {menu_id}")
            msg = f"Removed {role.mention}."
        else:
            if mode == "single":
                to_remove = [
                    interaction.guild.get_role(rid)
                    for rid in (menu_role_ids & user_role_ids)
                    if rid != role.id
                ]
                to_remove = [r for r in to_remove if r]
                if to_remove:
                    await member.remove_roles(
                        *to_remove, reason=f"Role menu {menu_id} (single)"
                    )
            elif menu.get("max_selections"):
                limit = menu["max_selections"]
                current_from_menu = menu_role_ids & user_role_ids
                if len(current_from_menu) >= limit:
                    await interaction.response.send_message(
                        f"You can only pick **{limit}** role(s) from this menu. "
                        f"Remove one first.",
                        ephemeral=True,
                    )
                    return
            await member.add_roles(role, reason=f"Role menu {menu_id}")
            msg = f"Gave you {role.mention}."
    except discord.Forbidden:
        await interaction.response.send_message(
            "I don't have permission to change your roles.", ephemeral=True
        )
        return
    except discord.HTTPException:
        await interaction.response.send_message(
            "Something went wrong updating your roles.", ephemeral=True
        )
        return

    await interaction.response.send_message(msg, ephemeral=True)


async def _handle_select(
    interaction: Interaction, menu_id: int, values: list[str]
) -> None:
    bot: PizzaHat = interaction.client  # type: ignore[assignment]
    menu = await _fetch_menu(bot, menu_id)
    if not menu:
        await interaction.response.send_message(
            "This menu no longer exists.", ephemeral=True
        )
        return

    ok, member = await _ensure_can_use(interaction, menu)
    if not ok or not member or not interaction.guild:
        return

    if not interaction.guild.me.guild_permissions.manage_roles:
        await interaction.response.send_message(
            "I'm missing the Manage Roles permission.", ephemeral=True
        )
        return

    items = await _fetch_items(bot, menu_id)
    menu_role_ids = {it["role_id"] for it in items}

    selected_ids: set[int] = set()
    for v in values:
        try:
            selected_ids.add(int(v))
        except ValueError:
            continue
    selected_ids &= menu_role_ids

    bot_top = interaction.guild.me.top_role
    manageable = lambda r: r is not None and r < bot_top  # noqa: E731

    user_role_ids = {r.id for r in member.roles}
    to_add: list[discord.Role] = []
    to_remove: list[discord.Role] = []

    for rid in selected_ids - user_role_ids:
        role = interaction.guild.get_role(rid)
        if manageable(role):
            to_add.append(role)  # type: ignore[arg-type]

    for rid in (menu_role_ids & user_role_ids) - selected_ids:
        role = interaction.guild.get_role(rid)
        if manageable(role):
            to_remove.append(role)  # type: ignore[arg-type]

    try:
        if to_add:
            await member.add_roles(*to_add, reason=f"Role menu {menu_id} select")
        if to_remove:
            await member.remove_roles(*to_remove, reason=f"Role menu {menu_id} select")
    except discord.Forbidden:
        await interaction.response.send_message(
            "I don't have permission to change your roles.", ephemeral=True
        )
        return
    except discord.HTTPException:
        await interaction.response.send_message(
            "Something went wrong updating your roles.", ephemeral=True
        )
        return

    parts = []
    if to_add:
        parts.append("**+** " + ", ".join(r.mention for r in to_add))
    if to_remove:
        parts.append("**−** " + ", ".join(r.mention for r in to_remove))
    summary = "\n".join(parts) if parts else "No changes."
    await interaction.response.send_message(summary, ephemeral=True)


class RoleMenuEvents(Cog):
    """Persistent view registration for role menus."""

    def __init__(self, bot: PizzaHat):
        self.bot = bot

    async def cog_load(self) -> None:
        if not self.bot.db:
            return
        rows = await self.bot.db.fetch(
            "SELECT * FROM role_menus WHERE enabled=TRUE AND message_id IS NOT NULL"
        )
        for row in rows:
            menu = dict(row)
            items = await _fetch_items(self.bot, menu["id"])
            guild = self.bot.get_guild(menu["guild_id"])
            try:
                view = RoleMenuView(menu, items, guild)
                self.bot.add_view(view, message_id=menu["message_id"])
            except Exception as e:
                logger.warning("Failed to register role menu %s: %s", menu["id"], e)


async def setup(bot: PizzaHat) -> None:
    await bot.add_cog(RoleMenuEvents(bot))
