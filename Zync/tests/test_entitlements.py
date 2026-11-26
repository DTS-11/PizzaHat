from __future__ import annotations

import asyncio
import datetime

from core.entitlements import EntitlementService, Tier

FUTURE = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)


class FakePool:
    def __init__(self, row: dict | None) -> None:
        self.row = row
        self.calls = 0

    async def fetchrow(self, *args):  # noqa: ANN002, ANN201
        self.calls += 1
        return self.row


def test_inactive_subscription_is_free() -> None:
    pool = FakePool({"tier": 2, "status": "cancelled", "current_period_end": FUTURE})
    service = EntitlementService(pool)
    assert asyncio.run(service.tier_for(1)) is Tier.FREE
    assert asyncio.run(service.has(1, Tier.BASIC)) is False


def test_active_subscription_is_cached() -> None:
    pool = FakePool({"tier": 1, "status": "active", "current_period_end": FUTURE})
    service = EntitlementService(pool)
    assert asyncio.run(service.tier_for(2)) is Tier.BASIC
    assert asyncio.run(service.tier_for(2)) is Tier.BASIC
    assert pool.calls == 1

    service.invalidate(2)
    assert asyncio.run(service.tier_for(2)) is Tier.BASIC
    assert pool.calls == 2


def test_unknown_tier_is_safe() -> None:
    service = EntitlementService(FakePool({"tier": 99, "status": "active", "current_period_end": FUTURE}))
    assert asyncio.run(service.tier_for(3)) is Tier.FREE


def test_expired_subscription_is_free() -> None:
    past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    service = EntitlementService(
        FakePool({"tier": 2, "status": "active", "current_period_end": past})
    )
    assert asyncio.run(service.tier_for(4)) is Tier.FREE
