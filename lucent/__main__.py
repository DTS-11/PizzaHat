"""Bot process entry point.

Creates :class:`core.bot.Lucent`, configures logging, and runs the bot with the
configured Discord token.
"""

from core.bot import Lucent
from core.logging import configure_logging
from utils.config import TOKEN

if __name__ == "__main__":
    configure_logging()
    Lucent().run(TOKEN)  # type: ignore[call-arg]
