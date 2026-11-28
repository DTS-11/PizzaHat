"""Bot bootstrap and shared application state.

Defines :class:`Lucent`, its intents/session setup, extension lists, database
lifecycle, and command error handling. Structural concerns such as logging and
entitlements live in dedicated modules.
"""

from __future__ import annotations

import datetime
import os

import aiohttp
import discord
from discord.ext import commands
from discord.ext.commands import CommandError, Context

from core.database import create_db_pool, run_migrations
from core.entitlements import EntitlementService, Tier
from core.logging import get_logger
from utils.config import REPO_LINK
from utils.embed import golden_embed, orange_embed, red_embed

logger = get_logger("bot")

__all__ = ["Lucent", "Tier", "INITIAL_EXTENSIONS", "SUB_EXTENSIONS"]

INITIAL_EXTENSIONS = [
    "cogs.dev",
    "cogs.emojis",
    "cogs.mod",
    "cogs.role_menus",
    "cogs.safety",
    "cogs.help",
    "cogs.setup",
    "cogs.tags",
    "cogs.templates",
    "cogs.tickets",
    "cogs.workflows",
]


SUB_EXTENSIONS = [
    "cogs_hidden.events",
    "cogs_hidden.guild_logs",
    "cogs_hidden.interactions",
    "cogs_hidden.safety_hooks",
    "cogs_hidden.workflow_runner",
]

description = f"""
Your server, on autopilot.

Automate the boring parts of Discord with custom rules, welcome flows, and
built-in anti-alt & automod protection. Fast, reliable, and zero bloat.

Source: [GitHub]({REPO_LINK})
"""


class Lucent(commands.Bot):
    def __init__(self):
        # Voice-state logging does not need PyNaCl or davey.
        discord.VoiceClient.warn_nacl = False
        discord.VoiceClient.warn_dave = False

        allowed_mentions = discord.AllowedMentions(
            roles=False, everyone=False, users=True, replied_user=True
        )
        intents = discord.Intents(
            guilds=True,
            invites=True,
            members=True,
            messages=True,
            message_content=True,
            reactions=True,
            moderation=True,
            integrations=True,
            voice_states=True,
            auto_moderation=True,
            emojis_and_stickers=True,
        )

        super().__init__(
            command_prefix=commands.when_mentioned,
            description=description,
            intents=intents,
            allowed_mentions=allowed_mentions,
            case_insensitive=True,
            status=discord.Status.online,
            activity=discord.CustomActivity(name="🔗 lucentbot.app"),
        )

        self._BotBase__cogs = commands.core._CaseInsensitiveDict()
        self.yes = "<:yes:1268859625105784865>"
        self.no = "<:no:1268859614129295514>"
        self.color = 0x456DD4
        self.logging_webhooks: dict[int, discord.Webhook] = {}

        self.can_read_message_content = intents.message_content

    async def sync_commands(self) -> bool:
        """Sync the tree, scoped to DEV_GUILD_ID when set to avoid dev global syncs."""
        if os.getenv("SYNC_COMMANDS", "1") == "0":
            logger.info("Command sync skipped (SYNC_COMMANDS=0).")
            return True

        raw_guild_id = os.getenv("DEV_GUILD_ID")
        guild = (
            discord.Object(id=int(raw_guild_id))
            if raw_guild_id and raw_guild_id.isdigit()
            else None
        )
        try:
            if guild is None:
                await self.tree.sync()
            else:
                await self.tree.sync(guild=guild)
        except discord.DiscordException as exc:
            logger.warning("Slash command sync failed: %s", exc)
            return False
        return True

    async def on_tree_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        """Give clear, ephemeral feedback for failed application commands."""
        if isinstance(error, discord.app_commands.NoPrivateMessage):
            message = "This command can only be used in a server."
        elif isinstance(error, discord.app_commands.MissingPermissions):
            missing = ", ".join(p.replace("_", " ") for p in error.missing_permissions)
            message = f"You need **{missing}** permission to use this command."
        elif isinstance(error, discord.app_commands.BotMissingPermissions):
            missing = ", ".join(p.replace("_", " ") for p in error.missing_permissions)
            message = f"I'm missing the **{missing}** permission to do that."
        elif isinstance(error, discord.app_commands.CommandOnCooldown):
            message = (
                f"That command is on cooldown. Try again in `{error.retry_after:.0f}s`."
            )
        elif isinstance(error, discord.app_commands.CommandInvokeError):
            logger.error(
                "Application command /%s failed",
                interaction.command.name if interaction.command else "unknown",
                exc_info=(
                    type(error.original),
                    error.original,
                    error.original.__traceback__,
                ),
            )
            message = "Something went wrong while running that command."
        elif isinstance(error, commands.CheckFailure):
            message = str(error) or "You cannot use this command here."
        else:
            message = str(error) or "That command could not be completed."

        embed = orange_embed(description=message)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass

    async def setup_hook(self) -> None:
        if not hasattr(self, "uptime"):
            self.uptime = datetime.datetime.now(datetime.timezone.utc)

        self.db = await create_db_pool()
        await run_migrations(self.db)
        self.entitlements = EntitlementService(self.db)

        self.session = aiohttp.ClientSession()

        extensions = list(INITIAL_EXTENSIONS) + list(SUB_EXTENSIONS)
        if os.getenv("ENABLE_JISHAKU", "0") == "1":
            extensions.append("jishaku")

        success = fail = 0
        for ext in extensions:
            try:
                await self.load_extension(ext)
                success += 1
            except Exception as exc:
                logger.exception("Failed to load extension %s: %s", ext, exc)
                fail += 1

        await self.sync_commands()

        logger.info(
            "Extensions loaded: %s/%s (failed: %s)", success, len(extensions), fail
        )
        if fail:
            logger.warning("Startup completed with %s failed extension(s)", fail)

    async def close(self) -> None:
        """Close all owned resources in reverse creation order."""

        self.logging_webhooks.clear()
        if getattr(self, "session", None) is not None and not self.session.closed:
            await self.session.close()
        if getattr(self, "db", None) is not None:
            await self.db.close()
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
            invoked = getattr(ctx, "invoked_with", "") or "command"
            await ctx.send(
                embed=red_embed(
                    description=(
                        f"{self.no} Unknown command `{invoked}`. "
                        "Use `@Lucent help` to see what I can do."
                    )
                ),
                delete_after=10,
            )

        elif isinstance(error, commands.NotOwner):
            pass

        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.author.send(
                embed=discord.Embed(
                    description="This command cannot be used in direct messages.",
                    color=0xED4245,
                )
            )

        elif isinstance(error, commands.DisabledCommand):
            await ctx.send(
                embed=discord.Embed(
                    description="This command is currently disabled.",
                    color=0xFAA61A,
                )
            )

        elif isinstance(error, commands.BotMissingPermissions):
            if (
                error.missing_permissions[0] == "send_messages"
                and ctx.interaction is None
            ):
                return await ctx.message.add_reaction(self.no)

            perm_name = " ".join(error.missing_permissions[0].split("_")).title()
            await ctx.send(
                embed=discord.Embed(
                    description=f"I'm missing the **{perm_name}** permission to do that.",
                    color=0xED4245,
                )
            )

        elif isinstance(error, commands.MissingPermissions):
            perm_name = " ".join(error.missing_permissions[0].split("_")).title()
            await ctx.send(
                embed=discord.Embed(
                    description=f"You need the **{perm_name}** permission to use this command.",
                    color=0xED4245,
                )
            )

        elif isinstance(error, commands.MaxConcurrencyReached):
            await ctx.send(
                embed=discord.Embed(
                    description=f"This command is already running. You can only have `{error.number}` instance(s) active at once.",
                    color=0xFAA61A,
                )
            )

        elif isinstance(error, commands.ArgumentParsingError):
            await ctx.send(embed=discord.Embed(description=str(error), color=0xED4245))

        elif isinstance(error, commands.CommandInvokeError):
            original = error.original
            if not isinstance(original, discord.HTTPException):
                logger.error(
                    "Prefix command %s failed",
                    ctx.command.qualified_name if ctx.command else "unknown",
                    exc_info=(
                        type(original),
                        original,
                        original.__traceback__,
                    ),
                )

        elif isinstance(error, commands.MissingRequiredArgument):
            if ctx.command is not None:
                em = discord.Embed(
                    title=f"Missing Argument — {ctx.command.name}",
                    description=(
                        f"```\n{ctx.command.name} {ctx.command.signature}\n```\n"
                        + (ctx.command.help or "No description available.")
                        + "\n\n```\n<> Required  |  [] Optional\n```"
                    ),
                    color=0xFAA61A,
                )

                ctx.command.reset_cooldown(ctx)
                await ctx.send(embed=em)

        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                embed=discord.Embed(
                    description=f"⏳ This command is on cooldown. Try again in `{error.retry_after:.0f}s`.",
                    color=0xFAA61A,
                ),
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
