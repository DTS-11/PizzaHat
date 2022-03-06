from dotenv import load_dotenv
import os

from core.bot import PizzaHat

# run "python ." in \PizzaHat\Pizzahat\
if __name__ == '__main__':
    load_dotenv()

    bot = PizzaHat()
    bot.run(os.getenv("TOKEN"))
