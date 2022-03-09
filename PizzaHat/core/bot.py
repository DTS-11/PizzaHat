import discord
from discord.ext import commands
from discord_together import DiscordTogether
import datetime
import os
import asyncpg
import aiohttp


class PizzaHat(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or("p!", "P!"),
            intents=discord.Intents.all(),
            case_insensitive=True,
            strip_after_prefix=True,
            activity=discord.Activity(
                type=discord.ActivityType.watching, name='dsc.gg/pizza-invite | discord.gg/WhNVDTF'),
            mentions=discord.AllowedMentions(everyone=False, roles=False)
        )
        self._BotBase__cogs = commands.core._CaseInsensitiveDict()
        self.yes = '<:yes:813819712953647206>'
        self.no = '<:no:829841023445631017>'
        self.color = discord.Color.blue()
        self.success = discord.Color.green()
        self.failed = discord.Color.red()
        self.session = aiohttp.ClientSession()

        try:
            self.loop.run_until_complete(self.create_db_pool())
        except ConnectionRefusedError:
            print("PizzaHat.db is not defined, some commands will not work.")

        self.public_extensions = self.loop.run_until_complete(self.load_extensions("cogs"))
        self.hidden_extensions = self.loop.run_until_complete(self.load_extensions("cogs_hidden"))

    async def on_ready(self):
        if not hasattr(self, 'uptime'):
            self.uptime = datetime.datetime.utcnow()
        self.togetherControl = await DiscordTogether(os.getenv("TOKEN"), debug=True)
        print("Bot online.")
        
    async def create_db_pool(self):
        self.db = await asyncpg.create_pool(
            database=os.getenv("PGDATABASE"), user=os.getenv("PGUSER"), password=os.getenv("PGPASSWORD"))

    async def load_extensions(self, dir_name: str):
        extensions = []

        success = fail = 0
        fails = {}

        list_dir = [file_name for file_name in os.listdir(dir_name) if file_name.endswith(".py")]
        total = len(list_dir)

        for file_name in list_dir:
            ext_name = f"{dir_name}.{file_name.split('.')[0]}"

            try:
                self.load_extension(ext_name)
                extensions.append(ext_name)
                success += 1
            except Exception as e:
                fails[ext_name] = e
                fail += 1
            
            print(  # fancy loading
                (f"Loading extension {ext_name} "
                f"(Success {success}, Fail {fail}, Done {success + fail}/{total})")
                + " " * 20,  # whitespace padding
                end="\r" if success + fail < total else "\n"
            )
        
        if fail:
            print(f"Failed to load {fail} extention(s):")
            for ext_name, e in fails.items():
                print(f"  {ext_name}: {e}")
        
        return extensions
    
    def cog_is_public(self, cog: commands.Cog):
        return cog.__module__ in self.public_extensions
