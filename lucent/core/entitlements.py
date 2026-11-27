"""Centralised entitlement model and tier resolution.

This module deliberately has no Discord or bot imports so it can be used by
commands, services, workflow validation and future non-Discord integrations
without creating import cycles.
"""

from __future__ import annotations

import datetime
from enum import IntEnum
from typing import Any


class Tier(IntEnum):
    """Subscription tiers supported by the Discord engine."""

    FREE = 0
    BASIC = 1
    PRO = 2


class EntitlementService:
    """Resolve guild entitlements through a single cached code path.

    ``pool`` may be ``None`` in offline tests; in that case every guild is FREE.
    Cached values are keyed by guild ID and can be invalidated after a
    subscription change.
    """

    def __init__(self, pool: Any | None = None) -> None:
        self.pool = pool
        self._tier_cache: dict[int, Tier] = {}

    async def tier_for(self, guild_id: int) -> Tier:
        cached = self._tier_cache.get(guild_id)
        if cached is not None:
            return cached

        tier = Tier.FREE
        if self.pool is not None:
            row = await self.pool.fetchrow(
                "SELECT tier, status, current_period_end FROM premium "
                "WHERE guild_id=$1",
                guild_id,
            )
            if row and row["status"] == "active":
                period_end = row["current_period_end"]
                if period_end is None or period_end > datetime.datetime.now(
                    datetime.timezone.utc
                ):
                    try:
                        tier = Tier(int(row["tier"]))
                    except ValueError:
                        tier = Tier.FREE

        self._tier_cache[guild_id] = tier
        return tier

    async def has(self, guild_id: int, required: Tier) -> bool:
        return await self.tier_for(guild_id) >= required

    def invalidate(self, guild_id: int | None = None) -> None:
        if guild_id is None:
            self._tier_cache.clear()
        else:
            self._tier_cache.pop(guild_id, None)
