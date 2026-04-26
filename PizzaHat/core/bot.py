import datetime
import sys
import traceback
from enum import IntEnum
from importlib import import_module
from logging.config import dictConfig

import aiohttp
import discord
from core.database import bootstrap_database, create_db_pool, get_prefix
from discord.ext import commands
from discord.ext.commands import CommandError, Context
from discord.ext.commands.errors import ExtensionAlreadyLoaded
from utils.config import DEFAULT_PREFIX, REPO_LINK
from utils.embed import golden_embed

INITIAL_EXTENSIONS = [
    "cogs.antialt",
    "cogs.automod",
    "cogs.dev",
    "cogs.emojis",
    "cogs.fun",
    "cogs.mod",
    "cogs.starboard",
    "cogs.tags",
    "cogs.tickets",
    "cogs.utility",
]

SUB_EXTENSIONS = [
    "cogs_hidden.antialt",
    "cogs_hidden.automod",
    "cogs_hidden.events",
    "cogs_hidden.guild_logs",
    "cogs_hidden.help",
    "cogs_hidden.starboard",
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


class Tier(IntEnum):
    FREE = 0
    BASIC = 1
    PRO = 2


description = f"""
I'm PizzaHat —— Your Ultimate Discord Companion, a bot made by @itsdts.
I have features such as moderation, utiltity, games and more!

I'm also open source. You can see my code on [GitHub]({REPO_LINK})
"""


class PizzaHat(commands.Bot):
    def __init__(self):
        allowed_mentions = discord.AllowedMentions(
            roles=False, everyone=False, users=True, replied_user=True
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
            emojis_and_stickers=True,
        )

        super().__init__(
            command_prefix=self.get_custom_prefix,
            description=description,
            intents=intents,
            allowed_mentions=allowed_mentions,
            case_insensitive=True,
            strip_after_prefix=True,
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.custom, name="p!help | pizzahat.vercel.app"
            ),
        )

        self._BotBase__cogs = commands.core._CaseInsensitiveDict()
        self.yes = "<:yes:1268859625105784865>"
        self.no = "<:no:1268859614129295514>"
        self.color = 0x456DD4
        self.logging_webhooks: dict[int, discord.Webhook] = {}

    async def get_custom_prefix(
        self, bot: "PizzaHat", message: discord.Message
    ) -> list[str]:
        bot_mention = [f"<@{bot.user.id}>", f"<@!{bot.user.id}>"] if bot.user else []

        if message.guild is None:
            return [DEFAULT_PREFIX] + bot_mention

        prefix = await get_prefix(self.db, message.guild.id)
        return [prefix] + bot_mention

    async def setup_hook(self) -> None:
        if not hasattr(self, "uptime"):
            self.uptime = datetime.datetime.now(datetime.timezone.utc)

        # Create DB connection
        self.db = await create_db_pool()
        await bootstrap_database(self.db)

        # Create aiohttp session
        self.session = aiohttp.ClientSession()

        # Make the tickets view persistent
        ticket_view = import_module("utils.ui").TicketView(self)
        self.add_view(ticket_view)

        # Loading cogs...
        success = fail = 0
        total = len(INITIAL_EXTENSIONS + SUB_EXTENSIONS)

        for ext in INITIAL_EXTENSIONS:
            try:
                await self.load_extension(ext)
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
            f"Loaded all cogs.\nSuccess: {success}, Fail: {fail}\nDone! ({success + fail}/{total})"
        )
        print()
        print(f"Logged in as {self.user}")
        print("=========================")

    async def close(self) -> None:
        if hasattr(self, "session") and not self.session.closed:
            await self.session.close()
        await super().close()

    async def get_logging_webhook(
        self, channel: discord.TextChannel
    ) -> discord.Webhook | None:
        cached_webhook = self.logging_webhooks.get(channel.id)
        if cached_webhook is not None:
            return cached_webhook

        if self.user is None:
            return None

        webhook_name = f"{self.user.name} Logging"

        try:
            webhooks = await channel.webhooks()
        except discord.Forbidden:
            return None

        for webhook in webhooks:
            if (
                webhook.name == webhook_name
                and webhook.user
                and webhook.user.id == self.user.id
            ):
                self.logging_webhooks[channel.id] = webhook
                return webhook

        try:
            webhook = await channel.create_webhook(name=webhook_name)
        except discord.Forbidden:
            return None

        self.logging_webhooks[channel.id] = webhook
        return webhook

    async def send_log(
        self,
        channel: discord.TextChannel,
        *,
        embed: discord.Embed,
        content: str | None = None,
    ) -> None:
        webhook = await self.get_logging_webhook(channel)
        if webhook is None or self.user is None:
            await channel.send(content=content, embed=embed)
            return

        try:
            if content is None:
                await webhook.send(
                    embed=embed,
                    username=f"{self.user.name} Logging",
                    avatar_url=self.user.display_avatar.url,
                    wait=False,
                )
            else:
                await webhook.send(
                    content=content,
                    embed=embed,
                    username=f"{self.user.name} Logging",
                    avatar_url=self.user.display_avatar.url,
                    wait=False,
                )
        except (discord.Forbidden, discord.HTTPException):
            self.logging_webhooks.pop(channel.id, None)
            await channel.send(content=content, embed=embed)

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

                ctx.command.reset_cooldown(ctx)
                await ctx.send(embed=em)

        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                f"Whoopsie! This command needs a timeout. Hang tight while it takes a siesta. 😴⏳\nTry again after `{error.retry_after:.0f}s`",
                delete_after=5,
            )

        elif isinstance(error, commands.CheckFailure):
            from utils.custom_checks import PremiumCheck

            if isinstance(error, PremiumCheck):
                await ctx.send(
                    embed=golden_embed(
                        "Premium Required", str(error), timestamp=True
                    ).set_thumbnail(
                        url="https://cdn3.emoji.gg/emojis/321814-cool-diamond.png"
                    )
                )
