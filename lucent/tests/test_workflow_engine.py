from __future__ import annotations

import asyncio
import datetime
from types import SimpleNamespace

from workflows.conditions import ConditionEvaluator
from workflows.engine import WorkflowEngine
from workflows.triggers import WorkflowContext


def _engine() -> WorkflowEngine:
    return WorkflowEngine(SimpleNamespace(db=None, user=None))  # type: ignore[arg-type]


def _context(**overrides: object) -> WorkflowContext:
    guild = SimpleNamespace(id=123)
    values: dict[str, object] = {
        "guild": guild,
        "trigger_type": "message_create",
        "message": SimpleNamespace(content="hello world"),
    }
    values.update(overrides)
    return WorkflowContext(**values)  # type: ignore[arg-type]


def test_interval_schedule_advances_to_next_slot() -> None:
    now = datetime.datetime(2026, 1, 1, 12, 0, 30, tzinfo=datetime.timezone.utc)
    run_at, slot = WorkflowEngine.next_schedule(
        {"frequency": "interval", "interval_minutes": 5}, now=now
    )
    assert run_at == datetime.datetime(2026, 1, 1, 12, 5, tzinfo=datetime.timezone.utc)
    assert slot == "interval:5890897"


def test_daily_schedule_rolls_to_tomorrow_when_time_passed() -> None:
    now = datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.timezone.utc)
    run_at, slot = WorkflowEngine.next_schedule(
        {"frequency": "daily", "hour": 9, "minute": 30, "timezone": "UTC"}, now=now
    )
    assert run_at.date() == datetime.date(2026, 1, 2)
    assert slot == "2026-01-02"


def test_invalid_timezone_falls_back_to_utc() -> None:
    now = datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.timezone.utc)
    run_at, _ = WorkflowEngine.next_schedule(
        {"frequency": "daily", "timezone": "Not/AZone"}, now=now
    )
    assert run_at.tzinfo is not None


def test_contains_text_and_negate() -> None:
    evaluator = ConditionEvaluator()
    ctx = _context()
    positive = asyncio.run(
        evaluator.evaluate([{"type": "contains_text", "text": "WORLD"}], ctx)
    )
    assert positive.passed

    negative = asyncio.run(
        evaluator.evaluate(
            [{"type": "contains_text", "text": "world", "negate": True}], _context()
        )
    )
    assert not negative.passed


def test_contains_link_condition() -> None:
    evaluator = ConditionEvaluator()
    ctx = _context(message=SimpleNamespace(content="see https://example.com"))
    result = asyncio.run(evaluator.evaluate([{"type": "contains_link"}], ctx))
    assert result.passed


def test_evaluation_stops_at_first_failure() -> None:
    evaluator = ConditionEvaluator()
    result = asyncio.run(
        evaluator.evaluate(
            [
                {"type": "contains_text", "text": "missing"},
                {"type": "contains_link"},
            ],
            _context(),
        )
    )
    assert not result.passed
    assert len(result.results) == 1


def test_account_age_condition_uses_member_timestamp() -> None:
    young = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2)
    evaluator = ConditionEvaluator()
    ctx = _context(
        message=None, member=SimpleNamespace(created_at=young, bot=False, id=5)
    )
    result = asyncio.run(
        evaluator.evaluate([{"type": "account_age_lt", "days": 7}], ctx)
    )
    assert result.passed
