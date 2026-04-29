from typing import List

import discord
from async_lru import alru_cache
from core.bot import PizzaHat, Tier
from core.cog import Cog
from discord.ext import commands
from discord.ext.commands import Context
from utils.custom_checks import premium
from utils.embed import normal_embed
from utils.message import wait_for_msg

AVAILABLE_MODULES = [
    "banned_words",
    "all_caps",
    "message_spam",
    "invites",
    "mass_mentions",
    "emoji_spam",
    "zalgo_text",
]

MODULE_DESCRIPTIONS = {
    "banned_words": "Deletes messages containing banned words.",
    "all_caps": "Deletes messages that are mostly uppercase.",
    "message_spam": "Purges rapid consecutive messages.",
    "invites": "Deletes messages containing external Discord invite links.",
    "mass_mentions": "Deletes messages that mention 3 or more users.",
    "emoji_spam": "Deletes messages with excessive emoji usage.",
    "zalgo_text": "Deletes messages containing zalgo/corrupted text.",
}

MODULE_EMOJIS = {
    "banned_words": "🚫",
    "all_caps": "🔠",
    "message_spam": "💬",
    "invites": "🔗",
    "mass_mentions": "@",
    "emoji_spam": "😀",
    "zalgo_text": "👹",
}


class AutoModModulesView(discord.ui.View):
    def __init__(self, context: Context, current_modules: List[str]):
        super().__init__(timeout=300)
        self.context = context
        self.selected_modules = set(current_modules)
        self.done = False

        for module in AVAILABLE_MODULES:
            default = module in self.selected_modules
            button = discord.ui.Button(
                label=f"{MODULE_EMOJIS[module]} {module.replace('_', ' ').title()}",
                style=discord.ButtonStyle.green
                if default
                else discord.ButtonStyle.gray,
                custom_id=f"am_mod_{module}",
            )
            button.callback = self.make_callback(module, button)
            self.add_item(button)

    def make_callback(self, module: str, button: discord.ui.Button):
        async def callback(interaction: discord.Interaction):
            if interaction.user != self.context.author:
                return await interaction.response.send_message(
                    "Not your interaction ._.", ephemeral=True
                )

            if module in self.selected_modules:
                self.selected_modules.discard(module)
                button.style = discord.ButtonStyle.gray
            else:
                self.selected_modules.add(module)
                button.style = discord.ButtonStyle.green

            await interaction.response.edit_message(view=self)

        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.context.author:
            await interaction.response.send_message(
                "Not your interaction ._.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(custom_id="am_next")
    async def next_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not self.selected_modules:
            return await interaction.response.send_message(
                "You must select at least one module!", ephemeral=True
            )
        self.done = True
        self.stop()

    @discord.ui.button(custom_id="am_cancel")
    async def cancel_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.done = False
        self.stop()


class AutoModView(discord.ui.View):
    def __init__(self, context: Context):
        super().__init__(timeout=300)
        self.context = context
        self.warn_action = "none"
        self.done = False

    @discord.ui.select(
        placeholder="Select warn action (PREMIUM)",
        options=[
            discord.SelectOption(
                label="None",
                description="No action will be taken on warn threshold.",
                value="none",
                emoji="⛔",
            ),
            discord.SelectOption(
                label="Timeout",
                description="Timeout the user when they hit the warn threshold.",
                value="timeout",
                emoji="<:timer:1268872526549745736>",
            ),
            discord.SelectOption(
                label="Kick",
                description="Kick the user when they hit the warn threshold.",
                value="kick",
                emoji="👞",
            ),
            discord.SelectOption(
                label="Ban",
                description="Ban the user when they hit the warn threshold.",
                value="ban",
                emoji="<:ban:1268874381648465920>",
            ),
        ],
    )
    async def action_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        if interaction.user != self.context.author:
            return await interaction.response.send_message(
                "Not your interaction ._.", ephemeral=True
            )

        self.warn_action = select.values[0]
        await interaction.response.send_message(
            f"Warn action set to **{select.values[0]}**. Click Next to continue.",
            ephemeral=True,
        )

    @discord.ui.button(label="Skip Warn Setup", style=discord.ButtonStyle.gray)
    async def skip_warn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user != self.context.author:
            return await interaction.response.send_message(
                "Not your interaction ._.", ephemeral=True
            )
        self.warn_action = "none"
        self.done = True
        self.stop()

    @discord.ui.button(label="Next", style=discord.ButtonStyle.green)
    async def next_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user != self.context.author:
            return await interaction.response.send_message(
                "Not your interaction ._.", ephemeral=True
            )
        self.done = True
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user != self.context.author:
            return await interaction.response.send_message(
                "Not your interaction ._.", ephemeral=True
            )
        self.done = False
        self.stop()


class AutoModeration(Cog, emoji=1268880500248936491):
    """Configure Auto-Moderation in the server."""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot

    def clear_config_cache(self, guild_id: int | None = None) -> None:
        self.check_if_am_is_enabled.cache_clear()
        self.get_automod_config.cache_clear()

        hidden_cog = self.bot.get_cog("AutoModConfig")
        clear_cache = getattr(hidden_cog, "clear_config_cache", None)
        if callable(clear_cache):
            clear_cache(guild_id)

    @alru_cache()
    async def check_if_am_is_enabled(self, guild_id: int) -> bool:
        data: bool = (
            await self.bot.db.fetchval(
                "SELECT enabled FROM automod WHERE guild_id=$1", guild_id
            )
            if self.bot.db
            else False
        )
        return data

    @alru_cache()
    async def get_automod_config(self, guild_id: int):
        if self.bot.db is None:
            return None
        row = await self.bot.db.fetchrow(
            "SELECT enabled, modules, warn_action, warn_threshold FROM automod WHERE guild_id=$1",
            guild_id,
        )
        if not row:
            return None
        return {
            "enabled": row["enabled"],
            "modules": row["modules"] or AVAILABLE_MODULES,
            "warn_action": row["warn_action"] or "none",
            "warn_threshold": row["warn_threshold"] or 0,
        }

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def automod(self, ctx: Context):
        """Automod config commands."""

        if ctx.subcommand_passed is None:
            if not ctx.guild or not self.bot.db:
                return

            config = await self.get_automod_config(ctx.guild.id)
            enabled = config["enabled"] if config else False
            modules = config["modules"] if config else AVAILABLE_MODULES
            warn_action = config["warn_action"] if config else "none"
            warn_threshold = config["warn_threshold"] if config else 0

            mod_list = "\n".join(
                f"{MODULE_EMOJIS.get(m, '•')} **{m.replace('_', ' ').title()}** — {f'{self.bot.yes} Enabled' if m in modules else f'{self.bot.no} Disabled'}"
                for m in AVAILABLE_MODULES
            )

            em = normal_embed(
                title="Auto-Moderation",
                description=(
                    f"Status: **{f'{self.bot.yes} Enabled' if enabled else f'{self.bot.no} Disabled'}**\n\n"
                    f"**Modules**\n{mod_list}\n\n"
                    f"**Warn Threshold**\n"
                    f"Action: **{warn_action.title()}** | Threshold: **{warn_threshold} warns**\n"
                    f"<:cooldiamond:1497276086210527242> *Premium feature (Basic tier required)*"
                ),
                timestamp=True,
            )
            em.add_field(
                name="Usage",
                value=(
                    "`automod enable` — Enable AutoMod\n"
                    "`automod disable` — Disable AutoMod\n"
                    "`automod modules` — Configure modules interactively\n"
                    "`automod warnsetup` — Configure warn threshold action <:cooldiamond:1497276086210527242>"
                ),
                inline=False,
            )
            await ctx.send(embed=em)

    @automod.command(name="enable")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def automod_enable(self, ctx: Context):
        """Enables automod in the server."""

        if not ctx.guild or not self.bot.db:
            return

        await self.bot.db.execute(
            "INSERT INTO automod (guild_id, enabled, modules) VALUES ($1, $2, $3) ON CONFLICT (guild_id) DO UPDATE SET enabled=$2",
            ctx.guild.id,
            True,
            AVAILABLE_MODULES,
        )
        self.clear_config_cache(ctx.guild.id)
        await ctx.send(f"{self.bot.yes} Auto-mod enabled.")

    @automod.command(name="disable")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def automod_disable(self, ctx: Context):
        """Disables automod in the server."""

        if not ctx.guild or not self.bot.db:
            return

        await self.bot.db.execute(
            "UPDATE automod SET enabled=$1 WHERE guild_id=$2",
            False,
            ctx.guild.id,
        )
        self.clear_config_cache(ctx.guild.id)
        await ctx.send(f"{self.bot.yes} Auto-mod disabled.")

    @automod.command(name="modules")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def automod_modules(self, ctx: Context):
        """Configure automod modules interactively."""

        if not ctx.guild or not self.bot.db:
            return

        config = await self.get_automod_config(ctx.guild.id)
        current_modules = config["modules"] if config else AVAILABLE_MODULES

        em = normal_embed(
            title="AutoMod Modules",
            description="Click buttons to toggle modules on/off. Press **Next** when done.",
        )
        for mod in AVAILABLE_MODULES:
            em.add_field(
                name=f"{MODULE_EMOJIS.get(mod, '•')} {mod.replace('_', ' ').title()}",
                value=MODULE_DESCRIPTIONS[mod],
                inline=True,
            )

        view = AutoModModulesView(ctx, current_modules)
        msg = await ctx.send(embed=em, view=view)

        await view.wait()

        if not view.done:
            return await msg.edit(content="Setup cancelled.", view=None)

        modules_list = list(view.selected_modules)
        await self.bot.db.execute(
            "UPDATE automod SET modules=$1 WHERE guild_id=$2",
            modules_list,
            ctx.guild.id,
        )
        self.clear_config_cache(ctx.guild.id)

        enabled_str = ", ".join(modules_list)
        await msg.edit(
            content=f"{self.bot.yes} AutoMod modules updated: **{enabled_str}**",
            view=None,
        )

    @automod.command(name="warnsetup")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @commands.cooldown(1, 30, commands.BucketType.user)
    @premium(Tier.BASIC)
    async def automod_warnsetup(self, ctx: Context):
        """Configure warn threshold and action <:cooldiamond:1497276086210527242>"""

        if not ctx.guild or not self.bot.db:
            return

        config = await self.get_automod_config(ctx.guild.id)
        current_action = config["warn_action"] if config else "none"
        current_threshold = config["warn_threshold"] if config else 0

        em = normal_embed(
            title="Warn Threshold Setup",
            description=(
                f"Current action: **{current_action.title()}**\n"
                f"Current threshold: **{current_threshold} warns**\n\n"
                "Select an action below, then click **Next**."
            ),
        )

        view = AutoModView(ctx)
        msg = await ctx.send(embed=em, view=view)

        await view.wait()

        if not view.done:
            return await msg.edit(content="Setup cancelled.", view=None)

        await msg.edit(
            content="Now enter the number of warns before the action triggers.\nType a number (e.g. `3`) or `cancel`.",
            view=None,
        )

        m = await wait_for_msg(ctx, 60, msg)
        if m == "pain":
            return

        try:
            threshold = int(m.content)  # type: ignore
            if threshold < 0:
                return await msg.edit(
                    content=f"{self.bot.no} Threshold cannot be negative."
                )
        except ValueError:
            return await msg.edit(content=f"{self.bot.no} Please enter a valid number.")

        if threshold > 0 and view.warn_action == "none":
            return await msg.edit(
                content=f"{self.bot.no} You must select a warn action if threshold is greater than 0."
            )

        await self.bot.db.execute(
            "UPDATE automod SET warn_action=$1, warn_threshold=$2 WHERE guild_id=$3",
            view.warn_action,
            threshold,
            ctx.guild.id,
        )
        self.clear_config_cache(ctx.guild.id)

        action_display = (
            view.warn_action.title() if view.warn_action != "none" else "None"
        )
        await msg.edit(
            content=f"{self.bot.yes} Warn setup complete. Action: **{action_display}** | Threshold: **{threshold} warns**"
        )


async def setup(bot):
    await bot.add_cog(AutoModeration(bot))
