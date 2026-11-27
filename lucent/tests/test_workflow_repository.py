from __future__ import annotations

import asyncio

from workflows.repository import WorkflowRepository


class RecordingPool:
    def __init__(self, value: object = None) -> None:
        self.value = value
        self.statements: list[str] = []

    async def fetchval(self, sql: str, *args: object) -> object:
        self.statements.append(" ".join(sql.split()))
        return self.value


def test_get_dedupe_uses_base_table_column_names() -> None:
    # `bot_msg_id` is an alias exposed by the star_info view. The base table
    # column is `bot_message_id`; querying the alias here raises at runtime.
    pool = RecordingPool(4242)
    repo = WorkflowRepository(pool)  # type: ignore[arg-type]

    assert asyncio.run(repo.get_dedupe(10, 20)) == 4242
    statement = pool.statements[0]
    assert "SELECT bot_message_id FROM workflow_dedupe" in statement
    assert "bot_msg_id" not in statement
