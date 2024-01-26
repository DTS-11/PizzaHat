import os

from core.bot import PizzaHat
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    bot = PizzaHat()
    bot.run(os.getenv("TOKEN"))  # type: ignore
