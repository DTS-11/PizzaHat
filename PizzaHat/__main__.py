import topgg
import os
from dotenv import load_dotenv
from discord.ext import tasks

from core.bot import PizzaHat


@tasks.loop(minutes=30)
async def update_stats():
    try:
        bot.topggpy = topgg.DBLClient(bot, os.getenv("DBL_TOKEN"), autopost=True)
        await bot.topggpy.post_guild_count()
        print(f"Posted server count: {bot.topggpy.guild_count}")

    except Exception as e:
        print(f"Failed to post server count\n{e.__class__.__name__}: {e}")

    update_stats.start()


# run "python ." in \PizzaHat\PizzaHat\
if __name__ == '__main__':
    load_dotenv()
    bot = PizzaHat()
    
    bot.run(os.getenv("TOKEN"))