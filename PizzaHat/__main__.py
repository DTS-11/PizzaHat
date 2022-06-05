import os

from dotenv import load_dotenv

from core.bot import PizzaHat
import core.database as db
import asyncio

load_dotenv()


# run "python ." in \PizzaHat\PizzaHat\
async def main():
    pool = await db.create_db_pool()
    async with pool as db_pool:
        print("DB Connected")
        async with bot:
            bot.db = db_pool
            await bot.start(os.getenv("TOKEN"))


if __name__ == '__main__':
    bot = PizzaHat()

    try:
        asyncio.run(main())

    except ConnectionRefusedError:
        print("DB not connected.")

    except Exception as e:
        print(e)