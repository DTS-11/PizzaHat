from __future__ import annotations

import asyncio
import uuid

from services.moderation import ModerationService
from services.tickets import TicketService


class CasePool:
    """Minimal asyncpg-shaped double for case creation."""

    def __init__(self, existing: dict | None = None) -> None:
        self.existing = existing
        self.insert_sql = ""
        self.args: tuple = ()

    async def fetchrow(self, sql: str, *args: object) -> dict | None:
        self.insert_sql = " ".join(sql.split())
        self.args = args
        if self.existing is not None:
            return dict(self.existing)
        return {
            "case_id": args[0],
            "guild_id": args[1],
            "subject_user_id": args[2],
            "moderator_user_id": args[3],
            "action_type": args[4],
            "source": args[5],
            "reason": args[6],
            "duration_seconds": args[7],
            "status": args[8],
        }


def test_case_creation_uses_uuid_and_idempotency_key() -> None:
    pool = CasePool()
    service = ModerationService(pool)  # type: ignore[arg-type]

    case = asyncio.run(
        service.create_case(
            10, 20, 30, "warn", reason="spam", idempotency_key="fixed-key"
        )
    )

    assert case is not None
    assert uuid.UUID(str(case["case_id"]))
    assert pool.args[-1] == "fixed-key"
    assert "ON CONFLICT (idempotency_key) DO NOTHING" in pool.insert_sql
    assert case["source"] == "manual"


def test_duplicate_case_returns_existing_row() -> None:
    original = {"case_id": uuid.uuid4(), "guild_id": 10, "action_type": "warn"}
    pool = CasePool(existing=original)
    service = ModerationService(pool)  # type: ignore[arg-type]

    case = asyncio.run(
        service.create_case(
            10, 20, 30, "warn", idempotency_key="duplicate-key"
        )
    )
    assert case is not None
    assert case["case_id"] == original["case_id"]


class TicketPool:
    def __init__(self, row: dict | None = None) -> None:
        self.row = row
        self.statements: list[str] = []

    async def fetchrow(self, sql: str, *args: object) -> dict | None:
        self.statements.append(" ".join(sql.split()))
        # First call is the existing-ticket lookup, second is the insert.
        if self.row is not None and len(self.statements) == 2:
            return dict(self.row)
        return None


def test_open_ticket_is_idempotent_by_thread_id() -> None:
    row = {"id": 1, "guild_id": 10, "thread_id": 99, "creator_id": 20}
    pool = TicketPool(row=row)
    service = TicketService(pool)  # type: ignore[arg-type]

    ticket = asyncio.run(service.open_ticket(10, 99, 20))
    assert ticket["thread_id"] == 99
    assert any("ON CONFLICT (thread_id) DO NOTHING" in sql for sql in pool.statements)
