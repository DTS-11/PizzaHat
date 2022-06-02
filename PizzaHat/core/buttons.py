from typing import Optional, Union

from discord import ButtonStyle, Emoji, PartialEmoji
from discord.ui import Button


class ButtonCreation(Button):
    def __init__(
        self,
        *,
        label: Optional[str] = None,
        style: ButtonStyle = ...,
        emoji: Optional[Union[str, Emoji, PartialEmoji]] = None,
        url: Optional[str] = None,
        disabled: bool = False
    ):
        super().__init__(label=label, style=style, emoji=emoji, url=url, disabled=disabled)
