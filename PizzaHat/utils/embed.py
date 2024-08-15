import datetime
from typing import Optional

from discord import Color, Embed


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


def normal_embed(
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    timestamp: Optional[bool] = None,
) -> Embed:
    return Embed(
        title=title,
        description=description,
        color=0x456DD4,
        timestamp=datetime.datetime.now() if timestamp else None,
    )
