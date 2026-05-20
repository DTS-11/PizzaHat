import logging

from core.bot import PizzaHat
from utils.config import TOKEN

logger = logging.getLogger("bot")

if __name__ == "__main__":
    bot = PizzaHat()
    bot.run(TOKEN, root_logger=True)  # type: ignore
