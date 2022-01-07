import discord
from discord.ext import commands
import asyncpg
import datetime
from config import TOKEN

INITIAL_EXTENSIONS = [
    'cogs.dev',
    'cogs.events',
    'cogs.fun',
    'cogs.games',
    'cogs.help',
    'cogs.image',
    'cogs.mod',
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
                print('Failed to load extension {}\n{}: {}'.format(
                    extension, type(e).__name__, e))

    async def on_ready(self):
        if not hasattr(self, 'uptime'):
            self.uptime = datetime.datetime.utcnow()
        print('Bot online')

    async def create_db_pool(self):
        self.db = await asyncpg.create_pool(database="PizzaHat", user="postgres", password=os.getenv('PG_PASS'))

    async def close(self):
        await super().close()

bot = PizzaHat()
if __name__ == '__main__':
    bot.run(TOKEN)
