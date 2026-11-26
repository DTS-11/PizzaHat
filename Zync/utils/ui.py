"""Reusable Discord UI components.

Contains persistent and ephemeral views for pagination, confirmations, tickets,
and role menus, along with their database-backed helpers.
"""

from typing import List, Optional, Union

import chat_exporter
import discord
from discord import ButtonStyle, Interaction, SelectOption, ui
from discord.ext import commands
from discord.ext.commands import Context

from core.bot import Zync
from core.entitlements import Tier
from utils.config import UPGRADE_URL


def _rowcount(status: str) -> int:
    """Return the affected-row count from an asyncpg command tag."""
    try:
        return int(status.rsplit(" ", 1)[-1])
    except (AttributeError, ValueError):
        return 0


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
        self._original_footers = [(e.footer.text, e.footer.icon_url) for e in embeds]
        self._update_button_states()

    def _update_button_states(self):
        is_first = self.current == 0
        is_last = self.current == len(self.embeds) - 1
        self.first.disabled = is_first
        self.back.disabled = is_first
        self.next.disabled = is_last
        self.last.disabled = is_last

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

        orig_text, orig_icon = self._original_footers[self.current]
        page_info = f"Page {self.current + 1} of {len(self.embeds)}"
        footer_text = f"{orig_text}  •  {page_info}" if orig_text else page_info
        embed.set_footer(text=footer_text, icon_url=orig_icon)

        self._update_button_states()
        await interaction.response.edit_message(
            embed=embed, attachments=[file] if file else [], view=self
        )

    @ui.button(emoji="⏮", style=ButtonStyle.gray)
    async def first(self, interaction: Interaction, button: ui.Button):
        self.current = 0
        await self.update_message(interaction)

    @ui.button(emoji="◀", style=ButtonStyle.blurple)
    async def back(self, interaction: Interaction, button: ui.Button):
        self.current -= 1
        await self.update_message(interaction)

    @ui.button(label="Quit", style=ButtonStyle.red)
    async def delete(self, interaction: Interaction, button: ui.Button):
        if interaction.message is not None:
            await interaction.message.delete()

    @ui.button(emoji="▶", style=ButtonStyle.blurple)
    async def next(self, interaction: Interaction, button: ui.Button):
        self.current += 1
        await self.update_message(interaction)

    @ui.button(emoji="⏭", style=ButtonStyle.gray)
    async def last(self, interaction: Interaction, button: ui.Button):
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

    @ui.button(label="Confirm", emoji="✅", style=ButtonStyle.green)
    async def confirm(self, interaction: Interaction, button: ui.Button):
        self.value = True
        self.stop()

    @ui.button(label="Cancel", emoji="✖", style=ButtonStyle.red)
    async def abort(self, interaction: Interaction, button: ui.Button):
        self.value = False
        self.stop()

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user != self.user:
            await interaction.response.send_message(
                "This confirmation dialog is not for you ._.", ephemeral=True
            )
            return False
        return True


class TicketView(ui.View):
    def __init__(
        self,
        bot: Zync,
        button_label: str = "Open Ticket",
        button_emoji: str = "\N{ADMISSION TICKETS}",
    ):
        self.bot = bot
        self.thread_id = None
        super().__init__(timeout=None)
        self.create_ticket.label = button_label
        self.create_ticket.emoji = button_emoji  # type: ignore

    @ui.button(
        label="Open Ticket",
        emoji="\N{ADMISSION TICKETS}",
        style=ButtonStyle.blurple,
        custom_id="create_ticket_btn",
    )
    @commands.bot_has_permissions(create_private_threads=True)
    async def create_ticket(self, interaction: Interaction, button: ui.Button):
        if not interaction.guild:
            return

        panel = None
        if self.bot.db and interaction.message:
            panel = await self.bot.db.fetchrow(
                "SELECT * FROM ticket_panels WHERE message_id=$1 AND guild_id=$2",
                interaction.message.id,
                interaction.guild.id,
            )
            if panel and not panel["enabled"]:
                return await interaction.response.send_message(
                    "This ticket panel is currently disabled.", ephemeral=True
                )

        # The partial unique index on tickets guarantees one open ticket per
        # creator, so check the durable record before creating a thread.
        existing = None
        if self.bot.db:
            existing = await self.bot.db.fetchrow(
                "SELECT thread_id FROM tickets "
                "WHERE guild_id=$1 AND creator_id=$2 AND status='open'",
                interaction.guild.id,
                interaction.user.id,
            )
        if existing is not None:
            existing_thread = interaction.guild.get_thread(existing["thread_id"])
            mention = existing_thread.mention if existing_thread else "an existing thread"
            return await interaction.response.send_message(
                f"You already have an open ticket: {mention}", ephemeral=True
            )

        if isinstance(interaction.channel, discord.TextChannel):
            thread = await interaction.channel.create_thread(
                name=f"ticket-{interaction.user}",
                reason=f"Ticket created by {interaction.user}",
                invitable=False,  # type: ignore
            )
            await thread.add_user(interaction.user)

            if self.bot.db:
                inserted = await self.bot.db.execute(
                    "INSERT INTO tickets (guild_id, thread_id, panel_id, creator_id) "
                    "VALUES ($1, $2, $3, $4) "
                    "ON CONFLICT (guild_id, creator_id) WHERE status='open' DO NOTHING",
                    interaction.guild.id,
                    thread.id,
                    panel["id"] if panel else None,
                    interaction.user.id,
                )
                if _rowcount(inserted) == 0:
                    # Another path (e.g. TicketService) won the race. Keep the
                    # durable ticket authoritative and discard our new thread.
                    try:
                        await thread.delete()
                    except discord.HTTPException:
                        pass
                    return await interaction.response.send_message(
                        "You already have an open ticket.", ephemeral=True
                    )

            support_role = None
            if panel and panel["support_role_id"]:
                support_role = interaction.guild.get_role(panel["support_role_id"])

            tvars = {
                "user": str(interaction.user),
                "user.mention": interaction.user.mention,
                "user.name": interaction.user.name,
                "user.id": str(interaction.user.id),
                "guild": interaction.guild.name,
                "guild.id": str(interaction.guild.id),
            }
            fallback_em = discord.Embed(
                title="Ticket Opened",
                description=(
                    f"Welcome, {interaction.user.mention}!\n\n"
                    "Please describe your issue in detail and a member of our support team will be with you shortly.\n\n"
                    "Use the **Close Ticket** button below when your issue has been resolved."
                ),
                color=0x57F287,
            )
            fallback_em.set_footer(
                text=str(interaction.user),
                icon_url=(
                    interaction.user.avatar.url if interaction.user.avatar else None
                ),
            )
            if panel and panel.get("template_id"):
                from utils.embed import resolve_template

                em = await resolve_template(
                    self.bot.db, panel["template_id"], fallback_em, **tvars
                )
            else:
                em = fallback_em

            content = interaction.user.mention
            if support_role:
                content += f" {support_role.mention}"

            await thread.send(
                content=content,
                embed=em,
                view=TicketSettings(thread.id, self.bot),
            )
            self.thread_id = thread.id

            await interaction.response.send_message(
                f"Your ticket has been created: {thread.mention}",
                ephemeral=True,
            )


class TicketSettings(ui.View):
    def __init__(self, thread_id: int, bot):
        self.thread_id = thread_id
        self.bot = bot
        super().__init__(timeout=None)

    async def check_premium(self, guild_id: int) -> bool:
        service = getattr(self.bot, "entitlements", None)
        if service is not None:
            return await service.has(guild_id, Tier.BASIC)
        return False

    @ui.button(
        label="Close Ticket",
        emoji="🔒",
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
            closed_rows = 0
            if self.bot.db:
                status = await self.bot.db.execute(
                    "UPDATE tickets SET closed_at=NOW(), closed_by=$1, status='closed' "
                    "WHERE thread_id=$2 AND guild_id=$3 AND status='open'",
                    interaction.user.id,
                    self.thread_id,
                    interaction.guild.id,
                )
                closed_rows = _rowcount(status)

            close_em = discord.Embed(
                description="🔒 This ticket has been closed and archived.",
                color=0xED4245,
            )
            await interaction.response.send_message(embed=close_em)
            await thread.edit(archived=True, locked=True)
            if self.bot.db and closed_rows == 0:
                await interaction.followup.send(
                    "Ticket record was already closed or missing; the thread is archived.",
                    ephemeral=True,
                )
        else:
            await interaction.response.send_message(
                content="Unable to find the ticket thread.", ephemeral=True
            )

    @ui.button(
        label="Transcript",
        emoji="📄",
        style=ButtonStyle.gray,
        custom_id="ticket_transcript_btn",
    )
    async def ticket_transcript(self, interaction: Interaction, button: ui.Button):
        if interaction.guild is None:
            return

        is_premium = await self.check_premium(interaction.guild.id)
        if not is_premium:
            return await interaction.response.send_message(
                "Transcripts are available on **Basic** and **Pro** tiers.\n"
                f"[Upgrade now]({UPGRADE_URL}).",
                ephemeral=True,
            )

        thread = interaction.guild.get_thread(self.thread_id)

        if thread:
            await interaction.response.defer(ephemeral=True)
            await chat_exporter.quick_export(thread)
        else:
            await interaction.response.send_message(
                content="Unable to generate a transcript for this ticket.",
                ephemeral=True,
            )


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

        if menu.get("type") == "select":
            self.add_item(RoleMenuSelect(menu_id, menu, items, guild))
        else:
            for item in items:
                self.add_item(RoleMenuButton(menu_id, item, guild))


async def _fetch_menu(
    bot: Zync, menu_id: int, guild_id: Optional[int] = None
) -> Optional[dict]:
    if not bot.db:
        return None
    if guild_id is None:
        row = await bot.db.fetchrow("SELECT * FROM role_menus WHERE id=$1", menu_id)
    else:
        row = await bot.db.fetchrow(
            "SELECT * FROM role_menus WHERE id=$1 AND guild_id=$2", menu_id, guild_id
        )
    return dict(row) if row else None


async def _fetch_items(
    bot: Zync, menu_id: int, guild_id: Optional[int] = None
) -> list[dict]:
    if not bot.db:
        return []
    if guild_id is None:
        rows = await bot.db.fetch(
            "SELECT * FROM role_menu_items WHERE menu_id=$1 ORDER BY position, role_id",
            menu_id,
        )
    else:
        rows = await bot.db.fetch(
            "SELECT item.* FROM role_menu_items AS item "
            "JOIN role_menus AS menu ON menu.id=item.menu_id "
            "WHERE item.menu_id=$1 AND menu.guild_id=$2 "
            "ORDER BY item.position, item.role_id",
            menu_id,
            guild_id,
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
    bot: Zync,
    menu: dict,
    items: list[dict],
    guild: Optional[discord.Guild],
) -> discord.Embed:
    """Build the menu embed, falling back to the inline title/description if no template."""

    from utils.embed import resolve_template

    fallback = build_embed(menu, items, guild)
    return await resolve_template(bot.db, menu.get("template_id"), fallback)


async def publish_menu(
    bot: Zync,
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
            "UPDATE role_menus SET channel_id=$1, message_id=$2, updated_at=NOW() "
            "WHERE id=$3 AND guild_id=$4",
            message.channel.id,
            message.id,
            menu["id"],
            menu["guild_id"],
        )
    bot.add_view(view, message_id=message.id)
    return message


async def refresh_menu(
    bot: Zync, menu_id: int, guild_id: Optional[int] = None
) -> bool:
    """Rebuild the embed + view for an existing posted menu. No-op if not posted."""

    menu = await _fetch_menu(bot, menu_id, guild_id)
    if not menu or not menu.get("message_id") or not menu.get("channel_id"):
        return False

    guild = bot.get_guild(menu["guild_id"])
    channel = bot.get_channel(menu["channel_id"]) if guild else None
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        return False

    items = await _fetch_items(bot, menu_id, menu["guild_id"])
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
    bot: Zync = interaction.client  # type: ignore[assignment]
    menu = await _fetch_menu(
        bot, menu_id, interaction.guild.id if interaction.guild else None
    )
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

    items = await _fetch_items(bot, menu_id, interaction.guild.id)
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
    bot: Zync = interaction.client  # type: ignore[assignment]
    menu = await _fetch_menu(
        bot, menu_id, interaction.guild.id if interaction.guild else None
    )
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

    items = await _fetch_items(bot, menu_id, interaction.guild.id)
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
