import discord
from discord.ext import commands
from discord_together import DiscordTogether
import datetime
from ruamel.yaml import YAML
from dotenv import load_dotenv
import os
import asyncpg
import traceback

load_dotenv()
yaml = YAML()

with open("./config.yml", "r", encoding="utf-8") as file:
    config = yaml.load(file)

INITIAL_EXTENSIONS = [
    'cogs.activities',
    #'cogs.configuration',
    'cogs.dev',
    'cogs.events',
    'cogs.fun',
    'cogs.games',
    'cogs.help',
    'cogs.image',
    'cogs.mod',
    #'cogs.music',
    'cogs.utility'
]

class PizzaHat(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or("p!", "P!"),
            intents=discord.Intents.all(),
            case_insensitive=True,
            strip_after_prefix=True,
            activity=discord.Activity(type=discord.ActivityType.watching, name='dsc.gg/pizza-invite | discord.gg/WhNVDTF'),
            mentions=discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=True)
        )
        self._BotBase__cogs = commands.core._CaseInsensitiveDict()
        self.yes = '<:yes:813819712953647206>'
        self.no = '<:no:829841023445631017>'
        self.color = discord.Color.blue()
        self.christmas = discord.Color.red()
        self.loop.run_until_complete(self.create_db_pool())

        for extension in INITIAL_EXTENSIONS:
            try:
                self.load_extension(extension)
            except Exception as e:
                print(f"Failed to load extension {extension}")
                print("".join(traceback.format_exception(e, e, e.__traceback__)))

    async def on_ready(self):
        print("Bot online")
        self.uptime = datetime.datetime.utcnow()
        self.togetherControl = await DiscordTogether(os.getenv("TOKEN"), debug=True)
        
    async def create_db_pool(self):
        self.db = await asyncpg.create_pool(database=os.getenv("PGDATABASE"), user=os.getenv("PGUSER"), password=os.getenv("PGPASSWORD"))

bot = PizzaHat()
if __name__ == '__main__':
    bot.run(os.getenv("TOKEN"))
