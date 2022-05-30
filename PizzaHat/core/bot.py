import discord
from discord.ext import commands
from discord.ext.commands.errors import ExtensionAlreadyLoaded
from discord_together import DiscordTogether
import datetime
import aiohttp
import asyncpg
import wavelink
import traceback
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
        for ext in INITIAL_EXTENSIONS:
            try:
                self.public_extensions = await self.load_extension(ext)
                print(f"Loaded {ext}")
                print("=========================")

            except Exception as e:
                print(f"Failed to load extension {ext}")
                print("".join(traceback.format_exception(e, e, e.__traceback__)))

        for sub_ext in SUB_EXTENSIONS:
            try:
                await self.load_extension(sub_ext)
                print(f"Loaded {sub_ext}")
                print("=========================")

            except Exception as e:
                print(f"Failed to load extension {sub_ext}")
                print("".join(traceback.format_exception(e, e, e.__traceback__)))

        try:
            await self.load_extension("jishaku")
            print("Jishaku has been loaded.")
            print("=========================")

        except ExtensionAlreadyLoaded:
            pass

        try:
            await self.loop.create_task(self.create_db_pool())
        
        except ConnectionRefusedError:
            print("DB not connected.")