"""Bot process entry point.

Creates :class:`core.bot.Zync` and runs it with the test token from
``utils.config``.
"""

import logging

from core.bot import Zync
from utils.config import TOKEN

logger = logging.getLogger("bot")

if __name__ == "__main__":
    bot = Zync()
    bot.run(TOKEN, root_logger=True)  # type: ignore
