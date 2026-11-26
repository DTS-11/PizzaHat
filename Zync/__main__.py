"""Bot process entry point.

Creates :class:`core.bot.Zync`, configures logging, and runs the bot with the
configured Discord token.
"""

from core.bot import Zync
from core.logging import configure_logging
from utils.config import TOKEN

if __name__ == "__main__":
    configure_logging()
    Zync().run(TOKEN)  # type: ignore[call-arg]
