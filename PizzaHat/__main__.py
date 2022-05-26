import os
from dotenv import load_dotenv

from core.bot import PizzaHat


# run "python ." in \PizzaHat\PizzaHat\
if __name__ == '__main__':
    load_dotenv()
    bot = PizzaHat()
    
    bot.run(os.getenv("TOKEN"))