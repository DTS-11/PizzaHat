import asyncio
import asyncpg
import topgg
import ssl
import os
from discord.ext import tasks
from dotenv import load_dotenv

from core.bot import PizzaHat


async def create_db_pool():
    ssl_object = ssl.create_default_context()
    ssl_object.check_hostname = False
    ssl_object.verify_mode = ssl.CERT_NONE
    bot.db = await asyncpg.create_pool(
        database=os.getenv("PGDATABASE"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
        ssl=ssl_object
    )


@tasks.loop()
async def update_stats():
    """This function runs every 30 minutes to automatically update your server count."""
    try:
        bot.topggpy = topgg.DBLClient(bot, os.getenv("DBL_TOKEN"), autopost=True, post_shard_count=True)
        await bot.wait_until_ready()
        await asyncio.sleep(60)
        await bot.topggpy.post_guild_count()
        print(f"Posted server count ({bot.topggpy.guild_count})")

    except Exception as e:
        print(f"Failed to post server count\n{e.__class__.__name__}: {e}")


# run "python ." in \PizzaHat\PizzaHat\
if __name__ == '__main__':
    load_dotenv()
    bot = PizzaHat()

    try:
        loop=asyncio.get_event_loop()
        loop.run_until_complete(create_db_pool())
        update_stats.start()

    except ConnectionRefusedError:
        print("Database not connected.")

    
    bot.run(os.getenv("TOKEN"))
