"""Command checks for the Discord surface.

All tier resolution goes through :class:`core.entitlements.EntitlementService`;
no cog or utility keeps its own premium cache.
"""

from __future__ import annotations

import datetime

from discord.ext import commands
from discord.ext.commands import Context

from core.entitlements import Tier
from utils.config import UPGRADE_URL


class PremiumCheck(commands.CheckFailure):
    """Raised when a command requires a higher entitlement tier."""


def premium(tier: Tier = Tier.BASIC):
    """Require at least ``tier`` for the current guild."""

    required = tier

    async def predicate(ctx: Context) -> bool:
        if ctx.guild is None:
            raise commands.CheckFailure(
                f"{ctx.bot.no} This command can only be used in a server."
            )

        service = getattr(ctx.bot, "entitlements", None)
        if service is None:
            granted = Tier.FREE
        else:
            granted = await service.tier_for(ctx.guild.id)

        if granted >= required:
            return True

        raise PremiumCheck(
            f"{ctx.bot.no} This is a **{required.name.title()}** feature. "
            f"[Learn more]({UPGRADE_URL})."
        )

    return commands.check(predicate)


async def is_premium_guild(pool, guild_id: int) -> bool:
    """Return whether a guild has any paid entitlement.

    Prefer the bot's entitlement service when available; this helper exists for
    non-application code paths that only hold a database pool.
    """

    row = await pool.fetchrow(
        "SELECT tier, status, current_period_end FROM premium WHERE guild_id=$1",
        guild_id,
    )
    if row is None or row["status"] != "active":
        return False
    period_end = row["current_period_end"]
    if period_end is not None and period_end <= datetime.datetime.now(
        datetime.timezone.utc
    ):
        return False
    try:
        return Tier(int(row["tier"])) >= Tier.BASIC
    except ValueError:
        return False


def clear_tier_cache(guild_id: int | None = None) -> None:
    """Compatibility no-op; cache invalidation is owned by the service."""
