"""Persistent interaction registration.

Adds internal cogs that re-register role-menu and ticket views on startup so
buttons and selects keep working after a restart.
"""

from __future__ import annotations

import logging

from core.bot import Zync
from core.cog import Cog
from utils.ui import (
    RoleMenuView,
    TicketSettings,
    TicketView,
    _fetch_items,
)

logger = logging.getLogger("bot")


class RoleMenuEvents(Cog):
    """Persistent view registration for role menus."""

    def __init__(self, bot: Zync):
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


class TicketInteractions(Cog):
    """Reattach persistent ticket button views after a restart."""

    def __init__(self, bot: Zync):
        self.bot = bot

    async def cog_load(self) -> None:
        # Fallback registration keyed by the stable custom_id.
        self.bot.add_view(TicketView(self.bot))
        if not self.bot.db:
            return

        try:
            panels = await self.bot.db.fetch(
                "SELECT message_id, button_label, button_emoji FROM ticket_panels "
                "WHERE enabled=TRUE AND message_id IS NOT NULL"
            )
            for panel in panels:
                view = TicketView(
                    self.bot,
                    panel["button_label"] or "Open Ticket",
                    panel["button_emoji"] or "\N{ADMISSION TICKETS}",
                )
                self.bot.add_view(view, message_id=panel["message_id"])

            open_threads = await self.bot.db.fetch(
                "SELECT thread_id FROM tickets WHERE status='open' AND closed_at IS NULL"
            )
            for row in open_threads:
                self.bot.add_view(TicketSettings(row["thread_id"], self.bot))
        except Exception as exc:
            logger.warning("Failed to restore ticket views: %s", exc)


async def setup(bot: Zync) -> None:
    await bot.add_cog(RoleMenuEvents(bot))
    await bot.add_cog(TicketInteractions(bot))
