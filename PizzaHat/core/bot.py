import discord
from discord.ext import commands
from discord.ext.commands.errors import ExtensionAlreadyLoaded
from discord_together import DiscordTogether
import datetime
import asyncio
import aiohttp
import wavelink
import asyncpg
import topgg
import ssl
import os



INITIAL_EXTENSIONS = [
    "cogs.activities",
    "cogs.admin",
    "cogs.emoji",
    "cogs.fun",
    "cogs.games",
    "cogs.image",
    "cogs.mod",
    "cogs.music",
    "cogs.poll",
    "cogs.utility",
]

SUB_EXTENSIONS = [
    "utils.automod",
    "utils.dev",
    "utils.events",
    "utils.help",
]


class PizzaHat(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix = commands.when_mentioned_or("p!", "P!"),
            intents = discord.Intents.all(),
            case_insensitive = True,
            strip_after_prefix = True,
            status = discord.Status.online,
            activity = discord.Activity(
                type=discord.ActivityType.watching, name="p!help | pizzahat.ml"
            ),
        )
        self._BotBase__cogs = commands.core._CaseInsensitiveDict()
        self.yes = "<:yes:813819712953647206>"
        self.no = "<:no:829841023445631017>"
        self.color = 0x456dd4
        self.success = discord.Color.green()
        self.failed = discord.Color.red()
        self.session = aiohttp.ClientSession()


    async def on_ready(self):
        if not hasattr(self, 'uptime'):
            self.uptime = datetime.datetime.utcnow()

        self.togetherControl = await DiscordTogether(os.getenv("TOKEN"), debug=True)
        print(f"Logged in as {self.user}")

    
    async def create_db_pool(self):
        ssl_object = ssl.create_default_context()
        ssl_object.check_hostname = False
        ssl_object.verify_mode = ssl.CERT_NONE
        self.db = await asyncpg.create_pool(
            database=os.getenv("PGDATABASE"),
            user=os.getenv("PGUSER"),
            password=os.getenv("PGPASSWORD"),
            ssl=ssl_object
        )


    async def on_wavelink_node_ready(self, node: wavelink.Node):
        print(f"Node: {node.identifier} is ready.")

    async def on_wavelink_track_end(self, player: wavelink.Player, track: wavelink.Track, reason):
        ctx = player.ctx
        vc: player = ctx.voice_client

        if vc.loop:
            return await vc.play(track)

        try:
            next_song = vc.queue.get()
            await vc.play(next_song)

            em = discord.Embed(color=self.color)
            em.add_field(name="▶ Now playing", value=f"[{next_song.title}]({next_song.uri})", inline=False)
            em.add_field(name="⌛ Song Duration", value=str(datetime.timedelta(seconds=next_song.duration)), inline=False)
            em.add_field(name="👥 Requested by", value=ctx.author.mention, inline=False)
            em.add_field(name="🎵 Song by", value=next_song.author, inline=False)
            em.set_thumbnail(url=vc.source.thumbnail)

            await ctx.send(embed=em)

        except wavelink.errors.QueueEmpty:
            pass


    async def update_stats(self):
        try:
            self.topggpy = topgg.DBLClient(self, os.getenv("DBL_TOKEN"), autopost=True, post_shard_count=True)
            await self.wait_until_ready()
            await asyncio.sleep(60)
            await self.topggpy.post_guild_count()
            print(f"Posted server count ({self.topggpy.guild_count})")

        except Exception as e:
            print(f"Failed to post server count\n{e.__class__.__name__}: {e}")


    async def setup_hook(self):
        self.public_extensions = await self.load_extensions("cogs")
        self.hidden_extensions = ["jishaku"] + await self.load_extensions("utils")

        await self.update_stats()

        try:
            await self.loop.create_task(self.create_db_pool())
        
        except ConnectionRefusedError:
            print("Database not connected.")


    async def load_extensions(self, dir_name: str):
        extensions = []

        success = fail = 0
        fails = {}

        list_dir = [file_name for file_name in os.listdir(dir_name) if file_name.endswith(".py")]
        total = len(list_dir)

        for file_name in list_dir:
            ext_name = f"{dir_name}.{file_name.split('.')[0]}"

            try:
                await self.load_extension(ext_name)
                extensions.append(ext_name)
                success += 1

            except Exception as e:
                fails[ext_name] = e
                fail += 1

            try:
                await self.load_extension("jishaku")
                print("Jishaku has been loaded.")
            
            except ExtensionAlreadyLoaded:
                pass
            
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

    
    async def cog_is_public(self, cog: commands.Cog):
        return cog.__module__ in self.public_extensions