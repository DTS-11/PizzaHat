"""Ticket persistence: panels, ticket lifecycle and member management guards."""

from __future__ import annotations

from typing import Any

from asyncpg.exceptions import UniqueViolationError

ONE_OPEN_TICKET_INDEX = "tickets_one_open_per_creator_idx"


class TicketError(Exception):
    """Base class for clean, user-facing ticket failures."""


class TicketNotFound(TicketError):
    """The thread is not a registered, open ticket."""


class TicketAlreadyOpen(TicketError):
    """The creator already has another open ticket."""


class TicketService:
    """All ticket database access for commands and persistent views."""

    def __init__(self, pool: Any | None) -> None:
        self.db = pool

    # ── panels ──────────────────────────────────────────────────────────────

    async def create_panel(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        name: str,
        *,
        template_id: int | None = None,
        button_label: str = "Open Ticket",
        button_emoji: str | None = None,
        support_role_id: int | None = None,
        enabled: bool = True,
    ) -> dict[str, Any] | None:
        if self.db is None:
            return None
        return dict(
            await self.db.fetchrow(
                """INSERT INTO ticket_panels (
                       guild_id, channel_id, message_id, name, template_id,
                       button_label, button_emoji, support_role_id, enabled
                   ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                   ON CONFLICT (guild_id, name) DO UPDATE
                   SET channel_id=EXCLUDED.channel_id,
                       message_id=EXCLUDED.message_id,
                       template_id=EXCLUDED.template_id,
                       button_label=EXCLUDED.button_label,
                       button_emoji=EXCLUDED.button_emoji,
                       support_role_id=EXCLUDED.support_role_id,
                       enabled=EXCLUDED.enabled
                   RETURNING *""",
                guild_id,
                channel_id,
                message_id,
                name,
                template_id,
                button_label,
                button_emoji,
                support_role_id,
                enabled,
            )
        )

    async def list_panels(self, guild_id: int) -> list[dict[str, Any]]:
        if self.db is None:
            return []
        rows = await self.db.fetch(
            "SELECT * FROM ticket_panels WHERE guild_id=$1 ORDER BY id", guild_id
        )
        return [dict(row) for row in rows]

    async def get_panel(self, guild_id: int, panel_id: int) -> dict[str, Any] | None:
        if self.db is None:
            return None
        row = await self.db.fetchrow(
            "SELECT * FROM ticket_panels WHERE id=$1 AND guild_id=$2",
            panel_id,
            guild_id,
        )
        return dict(row) if row else None

    async def get_panel_by_message(
        self, guild_id: int, message_id: int
    ) -> dict[str, Any] | None:
        if self.db is None:
            return None
        row = await self.db.fetchrow(
            "SELECT * FROM ticket_panels WHERE message_id=$1 AND guild_id=$2",
            message_id,
            guild_id,
        )
        return dict(row) if row else None

    async def delete_panel(self, guild_id: int, panel_id: int) -> dict[str, Any] | None:
        if self.db is None:
            return None
        row = await self.db.fetchrow(
            "DELETE FROM ticket_panels WHERE id=$1 AND guild_id=$2 RETURNING *",
            panel_id,
            guild_id,
        )
        return dict(row) if row else None

    # ── tickets ─────────────────────────────────────────────────────────────

    async def open_ticket(
        self,
        guild_id: int,
        thread_id: int,
        creator_id: int,
        *,
        panel_id: int | None = None,
        subject: str | None = None,
    ) -> dict[str, Any]:
        """Register a thread idempotently and enforce one open ticket per user."""

        if self.db is None:
            return {
                "id": None,
                "guild_id": guild_id,
                "thread_id": thread_id,
                "creator_id": creator_id,
                "panel_id": panel_id,
                "subject": subject,
                "status": "open",
            }

        existing = await self.get_ticket(guild_id, thread_id)
        if existing is not None:
            return existing

        try:
            row = await self.db.fetchrow(
                """INSERT INTO tickets
                   (guild_id, thread_id, panel_id, creator_id, subject)
                   VALUES ($1, $2, $3, $4, $5)
                   ON CONFLICT (thread_id) DO NOTHING
                   RETURNING *""",
                guild_id,
                thread_id,
                panel_id,
                creator_id,
                subject,
            )
        except UniqueViolationError as exc:
            if getattr(exc, "constraint_name", "") == ONE_OPEN_TICKET_INDEX:
                raise TicketAlreadyOpen(
                    "You already have an open ticket. Close it before opening another."
                ) from exc
            raise

        if row is not None:
            return dict(row)

        # Lost an insert race on thread_id: return the winner's registration.
        found = await self.get_ticket(guild_id, thread_id)
        if found is not None:
            return found
        raise TicketNotFound("That ticket could not be registered.")

    async def get_ticket(
        self, guild_id: int, thread_id: int
    ) -> dict[str, Any] | None:
        if self.db is None:
            return None
        row = await self.db.fetchrow(
            "SELECT * FROM tickets WHERE guild_id=$1 AND thread_id=$2",
            guild_id,
            thread_id,
        )
        return dict(row) if row else None

    async def require_ticket(
        self, guild_id: int, thread_id: int, *, require_open: bool = True
    ) -> dict[str, Any]:
        """Validate that a thread is a registered ticket before managing it."""

        ticket = await self.get_ticket(guild_id, thread_id)
        if ticket is None:
            raise TicketNotFound(
                "This thread is not a registered ticket. Use a ticket opened with the ticket panel."
            )
        if require_open and ticket["status"] != "open":
            raise TicketNotFound("This ticket is already closed.")
        return ticket

    async def close_ticket(
        self, guild_id: int, thread_id: int, closed_by: int
    ) -> dict[str, Any] | None:
        if self.db is None:
            return None
        row = await self.db.fetchrow(
            """UPDATE tickets SET status='closed', closed_at=NOW(), closed_by=$3
               WHERE guild_id=$1 AND thread_id=$2 AND status='open'
               RETURNING *""",
            guild_id,
            thread_id,
            closed_by,
        )
        return dict(row) if row else None

    async def set_subject(
        self, guild_id: int, thread_id: int, subject: str
    ) -> dict[str, Any] | None:
        if self.db is None:
            return None
        row = await self.db.fetchrow(
            "UPDATE tickets SET subject=$3 WHERE guild_id=$1 AND thread_id=$2 RETURNING *",
            guild_id,
            thread_id,
            subject,
        )
        return dict(row) if row else None

    async def list_tickets(
        self, guild_id: int, *, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        if self.db is None:
            return []
        if status is None:
            rows = await self.db.fetch(
                "SELECT * FROM tickets WHERE guild_id=$1 ORDER BY opened_at DESC LIMIT $2",
                guild_id,
                limit,
            )
        else:
            rows = await self.db.fetch(
                """SELECT * FROM tickets WHERE guild_id=$1 AND status=$2
                   ORDER BY opened_at DESC LIMIT $3""",
                guild_id,
                status,
                limit,
            )
        return [dict(row) for row in rows]

    async def insights(self, guild_id: int) -> dict[str, Any]:
        """Aggregates used by ``/mod insights`` from the ticket tables."""

        if self.db is None:
            return {
                "total": 0,
                "open": 0,
                "closed": 0,
                "avg_resolution": 0,
                "top_staff": [],
            }

        stats = await self.db.fetchrow(
            """SELECT COUNT(*) AS total,
                      COUNT(*) FILTER (WHERE status='open') AS open,
                      COUNT(*) FILTER (WHERE status='closed') AS closed,
                      COALESCE(AVG(EXTRACT(EPOCH FROM (closed_at - opened_at))/60), 0)
                          AS avg_resolution
               FROM tickets WHERE guild_id=$1""",
            guild_id,
        )
        top_staff = await self.db.fetch(
            """SELECT closed_by AS user_id, COUNT(*) AS count
               FROM tickets
               WHERE guild_id=$1 AND closed_by IS NOT NULL
               GROUP BY closed_by ORDER BY count DESC LIMIT 5""",
            guild_id,
        )
        return {
            "total": int(stats["total"] or 0),
            "open": int(stats["open"] or 0),
            "closed": int(stats["closed"] or 0),
            "avg_resolution": float(stats["avg_resolution"] or 0),
            "top_staff": [dict(row) for row in top_staff],
        }
