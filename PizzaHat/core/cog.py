from discord.ext.commands import Cog as DiscordCog
from discord.ext.commands import CogMeta as DiscordCogMeta


class CogMeta(DiscordCogMeta):
    """Metaclass used for passing an emoji parameter to a Cog object."""
    def __new__(mcs, *args, **kwargs):
        name, bases, attrs = args
        attrs["__cog_emoji__"] = kwargs.pop("emoji", None)

        mcs.instance = super().__new__(mcs, name, bases, attrs, **kwargs)
        return mcs.instance


class Cog(DiscordCog, metaclass=CogMeta):
    """
    Base class for all cogs that contains an emoji passed either by id 
    or the raw name.

    Example usage: `class MyCog(Cog, emoji='❓')`
    """

    @property
    def emoji(self):
        e = None

        if hasattr(self, "__cog_emoji__"):
            e = self.__cog_emoji__  # type: ignore
            if isinstance(e, int):  # custom emoji referenced by id
                e = self.bot.get_emoji(e)  # type: ignore
        
        return e
    
    @property
    def full_description(self):
        """The cog's emoji with the cog's description."""

        return (str((self.emoji or "")) + " " + self.description).strip()
