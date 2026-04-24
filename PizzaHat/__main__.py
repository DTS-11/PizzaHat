import logging

from core.bot import PizzaHat
from utils.config import TEST_BOT

logger = logging.getLogger("bot")

if __name__ == "__main__":
    bot = PizzaHat()
    bot.run(TEST_BOT, root_logger=True)  # type: ignore
