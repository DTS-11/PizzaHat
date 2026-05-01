import datetime
from typing import Optional

from discord import Color, Embed

theme_cache: dict[int, int] = {}


async def get_guild_theme(pool, guild_id: int) -> int:
    if guild_id in theme_cache:
        return theme_cache[guild_id]

    accent_color = await pool.fetchval(
        "SELECT accent_color FROM guild_themes WHERE guild_id = $1", guild_id
    )

    color = int(accent_color.lstrip("#"), 16) if accent_color else 0x456DD4

    theme_cache[guild_id] = color
    return color


def green_embed(
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    timestamp: Optional[bool] = None,
) -> Embed:
    return Embed(
        title=title,
        description=description,
        color=Color.green(),
        timestamp=datetime.datetime.now() if timestamp else None,
    )


def red_embed(
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    timestamp: Optional[bool] = None,
) -> Embed:
    return Embed(
        title=title,
        description=description,
        color=Color.red(),
        timestamp=datetime.datetime.now() if timestamp else None,
    )


def orange_embed(
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    timestamp: Optional[bool] = None,
) -> Embed:
    return Embed(
        title=title,
        description=description,
        color=Color.orange(),
        timestamp=datetime.datetime.now() if timestamp else None,
    )


def golden_embed(
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    timestamp: Optional[bool] = None,
) -> Embed:
    return Embed(
        title=title,
        description=description,
        color=Color.gold(),
        timestamp=datetime.datetime.now() if timestamp else None,
    )


def normal_embed(
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    color: Optional[int] = 0x456DD4,
    timestamp: Optional[bool] = None,
) -> Embed:
    return Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.datetime.now() if timestamp else None,
    )
