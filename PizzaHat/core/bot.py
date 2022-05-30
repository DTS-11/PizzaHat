import discord
from discord.ext import commands
from discord.ext.commands.errors import ExtensionAlreadyLoaded
from discord_together import DiscordTogether
import datetime
import aiohttp
import asyncpg
import wavelink
import ssl
import os


description = """
I'm PizzaHat, a bot made by DTS#5976 to provide some epic server utilities.
I have features such as moderation, utiltity, music and more! You can get more information on my commands by using the dropdown below.

I'm also open source. You can see my code on [GitHub](https://github.com/DTS-11/PizzaHat)
"""


class PizzaHat(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix = commands.when_mentioned_or("p!", "P!"),
            description=description,
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
            dsn=os.getenv("DATABASE_URL"),
            ssl=ssl_object
        )


    async def on_wavelink_node_ready(self, node: wavelink.Node):
        print(f"Node: {node.identifier} is ready.")

    async def on_wavelink_track_end(self, player: wavelink.Player, track: wavelink.Track, reason):
        ctx = player.ctx
        vc: player = ctx.voice_client

        track.info["requester"] = ctx.author
        wavelink_track = wavelink.Track(track.id, track.info)

        if vc.loop:
            return await vc.play(track)

        try:
            next_song = vc.queue.get()
            await vc.play(next_song)

            em = discord.Embed(color=self.color)
            em.add_field(name="▶ Now playing", value=f"[{next_song.title}]({next_song.uri})", inline=False)
            em.add_field(name="⌛ Song Duration", value=str(datetime.timedelta(seconds=next_song.duration)), inline=False)
            em.add_field(name="👥 Requested by", value=wavelink_track, inline=False)
            em.add_field(name="🎵 Song by", value=next_song.author, inline=False)
            em.set_thumbnail(url=vc.source.thumbnail)

            await ctx.send(embed=em)

        except wavelink.errors.QueueEmpty:
            pass


    async def setup_hook(self):
        # pterodactyl host
        self.public_extensions = await self.load_extensions("./container/PizzaHat/cogs")
        self.hidden_extensions = ["jishaku"] + await self.load_extensions("./container/PizzaHat/utils")

        # normal loading..
        # self.public_extensions = await self.load_extensions("cogs")
        # self.hidden_extensions = ["jishaku"] + await self.load_extensions("utils")

        try:
            await self.loop.create_task(self.create_db_pool())
        
        except ConnectionRefusedError:
            print("DB not connected.")

        
    async def load_extensions(self, dir_name):
        extensions = []

        success = fail = 0
        fails = {}

        list_dir = [file_name for file_name in os.listdir(dir_name) if file_name.endswith(".py")]
        total = len(list_dir)

        for file_name in list_dir:
            ext_name = f"{dir_name}.{file_name[:-3]}"

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