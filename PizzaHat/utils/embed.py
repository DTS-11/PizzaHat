import datetime
from typing import Any, Optional

from discord import Color, Embed

theme_cache: dict[int, int] = {}


async def get_guild_theme(pool, guild_id: int) -> int:
    if guild_id in theme_cache:
        return theme_cache[guild_id]

    accent_color = await pool.fetchval(
        "SELECT accent_color FROM guild_themes WHERE guild_id = $1", guild_id
    )

    color = accent_color if accent_color else 0x456DD4

    theme_cache[guild_id] = color
    return color


def invalidate_theme_cache(guild_id: int | None = None):
    """Invalidate the theme cache for a guild or all guilds."""

    if guild_id:
        theme_cache.pop(guild_id, None)
    else:
        theme_cache.clear()


def green_embed(
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    timestamp: Optional[bool] = None,
) -> Embed:
    """Creates embed with green color."""

    return Embed(
        title=title,
        description=description,
        color=0x57F287,
        timestamp=datetime.datetime.now() if timestamp else None,
    )


def red_embed(
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    timestamp: Optional[bool] = None,
) -> Embed:
    """Creates embed with red color."""

    return Embed(
        title=title,
        description=description,
        color=0xED4245,
        timestamp=datetime.datetime.now() if timestamp else None,
    )


def orange_embed(
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    timestamp: Optional[bool] = None,
) -> Embed:
    """Creates embed with orange color."""

    return Embed(
        title=title,
        description=description,
        color=0xFAA61A,
        timestamp=datetime.datetime.now() if timestamp else None,
    )


def golden_embed(
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    timestamp: Optional[bool] = None,
) -> Embed:
    """Creates embed with golden color."""

    return Embed(
        title=title,
        description=description,
        color=0xFFD700,
        timestamp=datetime.datetime.now() if timestamp else None,
    )


def normal_embed(
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    color: Optional[int] = None,
    timestamp: Optional[bool] = None,
) -> Embed:
    """Creates embed with bot's default color."""

    return Embed(
        title=title,
        description=description,
        color=color or 0x456DD4,
        timestamp=datetime.datetime.now() if timestamp else None,
    )


async def get_themed_embed(
    pool: Any,
    guild_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    timestamp: Optional[bool] = None,
) -> Embed:
    """Get a normal_embed with guild theme (premium) support."""

    from utils.custom_checks import is_premium_guild

    if await is_premium_guild(pool, guild_id):
        color = await get_guild_theme(pool, guild_id)
    else:
        color = 0x456DD4

    return normal_embed(title, description, color=color, timestamp=timestamp)


async def ctx_embed(
    ctx: Any,
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    color: Optional[int] = None,
    timestamp: Optional[bool] = None,
) -> Embed:
    """Get a themed embed using context (auto-detects guild/premium)."""

    if ctx.guild and ctx.bot.db:
        return await get_themed_embed(
            ctx.bot.db, ctx.guild.id, title, description, timestamp=timestamp
        )
    return normal_embed(title, description, timestamp=timestamp)


async def guild_embed(
    pool: Any,
    guild_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    timestamp: Optional[bool] = None,
) -> Embed:
    """Get a themed embed using pool and guild_id (for use in events/listeners)."""

    return await get_themed_embed(
        pool, guild_id, title, description, timestamp=timestamp
    )
