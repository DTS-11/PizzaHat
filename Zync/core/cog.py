"""Shared cog base classes.

Defines the project-specific ``Cog`` and ``CogMeta`` used to attach emoji
metadata to command modules. Colors are static so imports never perform network
or image-processing work.
"""

from __future__ import annotations

from typing import Union

from discord import Emoji, PartialEmoji
from discord.ext.commands import Cog as DiscordCog
from discord.ext.commands import CogMeta as DiscordCogMeta

DEFAULT_COG_COLOR = 0x456DD4


class CogMeta(DiscordCogMeta):
    """Metaclass used for passing an emoji parameter to a Cog object."""

    def __new__(mcs, *args, **kwargs):
        name, bases, attrs = args
        attrs["__cog_emoji__"] = kwargs.pop("emoji", None)
        mcs.instance = super().__new__(mcs, name, bases, attrs, **kwargs)
        return mcs.instance


class Cog(DiscordCog, metaclass=CogMeta):
    """Base cog that supports an optional emoji in the class declaration."""

    @property
    def emoji(self) -> Union[Emoji, PartialEmoji, None]:
        value = getattr(self, "__cog_emoji__", None)
        if not value:
            return None
        if isinstance(value, (Emoji, PartialEmoji)):
            return value
        if isinstance(value, int):
            guild_emoji = self.bot.get_emoji(value)  # type: ignore[attr-defined]
            return guild_emoji or PartialEmoji(id=value, name="_")
        if isinstance(value, str):
            if value.startswith("<") and value.endswith(">"):
                animated = value.startswith("<a:")
                name, emoji_id = value.rsplit(":", 1)
                return PartialEmoji(
                    name=name.split(":")[-1],
                    id=int(emoji_id[:-1]),
                    animated=animated,
                )
            return PartialEmoji(name=value)
        return None

    @property
    def full_description(self) -> str:
        """The cog's emoji with the cog's description."""

        return (str(self.emoji or "") + " " + self.description).strip()

    @property
    def color(self) -> int:
        """Static brand color for help and informational embeds."""

        return DEFAULT_COG_COLOR
