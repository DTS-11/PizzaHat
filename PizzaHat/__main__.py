import asyncio
import os

import core.database as db
from core.bot import PizzaHat
from dotenv import load_dotenv

load_dotenv()


# run "python ." in \PizzaHat\PizzaHat\
async def main():
    pool = await db.create_db_pool()
    if pool is not None:
        print("DB Connected")
        async with bot:
            bot.db = pool  # type: ignore
            await bot.start(os.getenv("TOKEN"))  # type: ignore


if __name__ == "__main__":
    bot = PizzaHat()

    try:
        asyncio.run(main())

    except ConnectionRefusedError:
        print("DB not connected.")

    except KeyboardInterrupt:
        print("Bot manually terminated.")

    except Exception as e:
        print(e)
