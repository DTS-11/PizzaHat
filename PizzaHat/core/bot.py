import datetime
import logging
import sys
import traceback
from importlib import import_module
from logging.config import dictConfig

import aiohttp
import core.database as db
import discord
from discord.ext import commands
from discord.ext.commands import CommandError, Context
from discord.ext.commands.errors import ExtensionAlreadyLoaded

INITIAL_EXTENSIONS = [
    # "cogs.antialt",
    "cogs.automod",
    "cogs.dev",
    "cogs.emojis",
    "cogs.fun",
    "cogs.games",
    "cogs.mod",
    "cogs.polls",
    # "cogs.starboard",
    "cogs.tags",
    "cogs.tickets",
    "cogs.utility",
]

SUB_EXTENSIONS = [
    "cogs_hidden.antialts",
    "cogs_hidden.automod",
    "cogs_hidden.events",
    "cogs_hidden.guild_logs",
    "cogs_hidden.help",
]

LOGGING_CONFIG = {
    "version": 1,
    "disabled_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(levelname)-10s - %(asctime)s - %(module)-15s : %(message)s",
        },
        "standard": {
            "format": "%(levelname)-10s - %(name)-15s : %(message)s",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
        "console2": {
            "level": "WARNING",
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
        "file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "formatter": "verbose",
            "filename": "bot.log",
            "mode": "w",
        },
    },
    "loggers": {
        "bot": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "discord": {
            "handlers": ["console2", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

dictConfig(LOGGING_CONFIG)

description = """
I'm PizzaHat —— Your Ultimate Discord Companion, a bot made by @itsdts.
I have features such as moderation, utiltity, games and more!

I'm also open source. You can see my code on [GitHub](https://github.com/DTS-11/PizzaHat)
"""


class PizzaHat(commands.Bot):
    def __init__(self):
        allowed_mentions = discord.AllowedMentions(
            roles=False, everyone=False, users=True
        )
        intents = discord.Intents(
            guilds=True,
            emojis=True,
            invites=True,
            members=True,
            messages=True,
            webhooks=True,
            reactions=True,
            moderation=True,
            integrations=True,
            voice_states=True,
            message_content=True,
            auto_moderation=True,
        )

        super().__init__(
            command_prefix=commands.when_mentioned_or("p!", "P!"),
            description=description,
            intents=intents,
            allowed_mentions=allowed_mentions,
            case_insensitive=True,
            strip_after_prefix=True,
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching, name="p!help"
            ),
        )

        self._BotBase__cogs = commands.core._CaseInsensitiveDict()
        self.yes = "<:yes:813819712953647206>"
        self.no = "<:no:829841023445631017>"
        self.color = 0x456DD4
        self.session = aiohttp.ClientSession()

    async def setup_hook(self) -> None:
        if not hasattr(self, "uptime"):
            self.uptime = datetime.datetime.now(datetime.timezone.utc)

        # Create DB connection
        if db is not None:
            self.db = await db.create_db_pool()

        # Make the tickets view persistent
        ticket_view = import_module("cogs.tickets").TicketView(self)
        self.add_view(ticket_view)

        # Loading cogs...
        success = fail = 0
        total = len(INITIAL_EXTENSIONS + SUB_EXTENSIONS)

        for ext in INITIAL_EXTENSIONS:
            try:
                self.public_extensions = await self.load_extension(ext)
                success += 1

            except Exception as e:
                print(f"Failed to load extension {ext}")
                print("".join(traceback.format_exception(e, e, e.__traceback__)))  # type: ignore
                fail += 1

        for sub_ext in SUB_EXTENSIONS:
            try:
                await self.load_extension(sub_ext)
                success += 1

            except Exception as e:
                print(f"Failed to load extension: {sub_ext}")
                print("".join(traceback.format_exception(e, e, e.__traceback__)))  # type: ignore
                fail += 1

        try:
            await self.load_extension("jishaku")
            print("Jishaku has been loaded.")

        except ExtensionAlreadyLoaded:
            pass

        print(
            f"Loaded all cogs.\nSuccess: {success}, Fail: {fail}\nDone! ({success+fail}/{total})"
        )
        print()
        print(f"Logged in as {self.user}")
        print("=========================")

    async def on_command_error(self, ctx: Context, error: CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            pass

        elif isinstance(error, commands.NotOwner):
            pass

        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.author.send("This command cannot be used in private messages.")

        elif isinstance(error, commands.DisabledCommand):
            await ctx.send("Sorry. This command is disabled and cannot be used.")

        elif isinstance(error, commands.BotMissingPermissions):
            if error.missing_permissions[0] == "send_messages":
                return await ctx.message.add_reaction(self.no)

            await ctx.send(
                "I am missing **{}** permissions.".format(
                    " ".join(error.missing_permissions[0].split("_")).title()
                )
            )

        elif isinstance(error, commands.MissingPermissions):
            await ctx.send(
                "You need **{}** perms to run this command.".format(
                    " ".join(error.missing_permissions[0].split("_")).title()
                )
            )

        elif isinstance(error, commands.MaxConcurrencyReached):
            await ctx.send(
                "An instance of this command is already running...\n"
                f"You can only run `{error.number}` instances at the same time."
            )

        elif isinstance(error, commands.ArgumentParsingError):
            await ctx.send(str(error))

        elif isinstance(error, commands.CommandInvokeError):
            original = error.original
            if not isinstance(original, discord.HTTPException):
                if ctx.command is not None:
                    print(f"In {ctx.command.qualified_name}:", file=sys.stderr)
                    traceback.print_tb(original.__traceback__)
                    print(f"{original.__class__.__name__}: {original}", file=sys.stderr)
                    print()
                    print()

        elif isinstance(error, commands.MissingRequiredArgument):
            if ctx.command is not None:
                em = discord.Embed(
                    title=f"{ctx.command.name} {ctx.command.signature}",
                    description=ctx.command.help,
                    color=discord.Color.og_blurple(),
                )

                await ctx.send(embed=em)

        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                f"Whoopsie! This command needs a timeout. Hang tight while it takes a siesta. 😴⏳\nTry again after `{error.retry_after:.0f}s`",
                delete_after=5,
            )
