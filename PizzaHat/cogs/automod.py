import traceback

import discord
from core.bot import PizzaHat
from core.cog import Cog
from discord import ui
from discord.ext import commands
from discord.ext.commands import Context
from utils.config import BANNED_WORDS


def actions_embed(ctx: Context):
    em = discord.Embed(
        title="Actions",
        description="Select an action to be taken when the rule is broken",
        color=ctx.bot.color,
        timestamp=ctx.message.created_at,
    )
    em.add_field(
        name="Action descriptions",
        value="`block:` Blocks the message from being sent.\n`timeout`: Timeout/mute the user\n`send alert`: Send an alert to the predefined channel",
    )
    view = ui.View()

    b1 = ui.Button(label="Block", style=discord.ButtonStyle.blurple)
    b2 = ui.Button(label="Timeout", style=discord.ButtonStyle.blurple)
    b3 = ui.Button(label="Send Alert", style=discord.ButtonStyle.blurple)

    view.add_item(b1).add_item(b2).add_item(b3)

    for child in view.children:
        if child == "Block":
            action = discord.AutoModRuleActionType.block_message
        elif child == "Timeout":
            action = discord.AutoModRuleActionType.timeout
        elif child == "Send Alert":
            action = discord.AutoModRuleActionType.send_alert_message

    return [em, action]


class AutoModDropdown(ui.Select):
    def __init__(self, ctx: Context):
        self.ctx = ctx
        options = []
        channel_list = [channel.name for channel in self.ctx.guild.channels if isinstance(channel, discord.TextChannel)]  # type: ignore
        role_list = [role.name for role in self.ctx.guild.roles if isinstance(role, discord.Role)]  # type: ignore

        options.extend(
            [
                discord.SelectOption(
                    label="Channels",
                    description="Which channels to ignore.",
                    value="".join(channel_list),
                ),
                discord.SelectOption(
                    label="Roles",
                    description="Which roles to ignore.",
                    value="".join(role_list),
                ),
            ]
        )

        super().__init__(
            placeholder="Choose an option...",
            min_values=0,
            max_values=20,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        em = discord.Embed(
            title="Automod",
            description="",
            color=discord.Color.blurple(),
            timestamp=self.ctx.message.created_at,
        )

        if self.values[0] == "Channels":
            em.description = "Choose which channels to ignore"

        if self.values[0] == "Roles":
            em.description = "Choose which roles to ignore"

        await interaction.response.edit_message(embed=em)


class AutoModView(ui.View):
    def __init__(self, ctx: Context):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.add_item(AutoModDropdown(ctx))

    @ui.button(
        label="Action", style=discord.ButtonStyle.blurple, custom_id="action_btn"
    )
    async def action(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(embed=actions_embed(self.ctx)[0])

    @ui.button(
        label="Ignored Channels",
        style=discord.ButtonStyle.blurple,
        custom_id="ignored_channels_btn",
    )
    async def ignored_channels(
        self, interaction: discord.Interaction, button: ui.Button
    ):
        await interaction.response.edit_message(
            content="Select channel(s) to be ignored from AutoMod", view=self
        )

    @ui.button(
        label="Ignored Roles",
        style=discord.ButtonStyle.blurple,
        custom_id="ignored_roles_btn",
    )
    async def ignored_roles(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(
            content="Select role(s) to be ignored from AutoMod", view=self
        )

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user == self.ctx.author:
            return True

        await interaction.response.send_message(
            content="Not your command ._.", ephemeral=True
        )


class AutoModeration(Cog, emoji=1207259153437949953):
    """Configure Auto-Moderation in the server."""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def automod(self, ctx: Context):
        """
        Automod configuration commands.

        To use this command, you need Manage Server permission.
        """

        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    @automod.command(name="enable")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def automod_enable(self, ctx: Context):
        """
        Enables bot auto-mod in the server.

        In order for this to work, the bot must have Manage Server permissions.

        To use this command, you must have Manage Server permission.
        """

        try:
            (
                await self.bot.db.execute(
                    "INSERT INTO automod (guild_id, enabled) VALUES ($1, $2)",
                    ctx.guild.id,
                    True,
                )
                if self.bot.db and ctx.guild
                else None
            )
            await ctx.send(f"{self.bot.yes} Auto-mod enabled.")

        except Exception as e:
            await ctx.send(f"{self.bot.no} Something went wrong...")
            print(f"Error in automod enable cmd: {e}")

    @automod.command(name="disable")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def automod_disable(self, ctx: Context):
        """
        Disables bot auto-mod in the server.

        In order for this to work, the bot must have Manage Server permissions.

        To use this command, you must have Manage Server permission.
        """

        try:
            (
                await self.bot.db.execute(
                    "DELETE FROM automod WHERE guild_id=$1", ctx.guild.id
                )
                if self.bot.db and ctx.guild
                else None
            )
            await ctx.send(f"{self.bot.yes} Auto-mod disabled.")

        except Exception as e:
            await ctx.send(f"{self.bot.no} Something went wrong...")
            print(f"Error in automod disable cmd: {e}")

    @automod.command(name="antislur")
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def automod_antislur(self, ctx: Context):
        """
        Create an automod rule for antislurs in the server.

        In order for this to work, the bot must have Manage Server permission.

        To use this command, you need Manage Server permission.
        """

        # @....command(...)
        # async def my_automod(ctx) -> None:
        #     await ctx.guild.create_automod_rule(
        #         name="Give it a name!",
        #         event_type=discord.AutoModRuleEventType.message_send # At the moment  this is the only event supported, also, this means that this automod rule will be called when a user sends a message
        #         trigger=discord.AutoModTrigger(
        #             type=discord.AutoModRuleTriggerType.keyword # for this example going to use keyword like triggers
        #             keyword_filter = ["your", "keywords"],
        #             regex_patterns [r"or your regex patterns"]
        #         ),
        #     actions = [discord.AutoModRuleAction(custom_message="No, don't use that kind of words")] # keep in mind only 1 keyword argument is allowed por each instance of discord.AutoModRuleAction
        #     )
        try:
            if ctx.guild is not None:
                await ctx.send(view=AutoModView(ctx))

                action = actions_embed(ctx)[1]
                exempt_channels = []
                exempt_roles = []

                await ctx.guild.create_automod_rule(
                    name="PizzaHat Anti-Slur Rule",
                    event_type=discord.AutoModRuleEventType.message_send,
                    trigger=discord.AutoModTrigger(
                        type=discord.AutoModRuleTriggerType.keyword,
                        keyword_filter=BANNED_WORDS,
                    ),
                    actions=[
                        action,
                        discord.AutoModRuleAction(
                            custom_message="Please refrain from using those words."
                        ),
                    ],
                    exempt_channels=exempt_channels,
                    exempt_roles=exempt_roles,
                    enabled=True,
                    reason=f"Anti-slur rule created by {ctx.author}",
                )

                await ctx.send(f"{self.bot.yes} Anti-slur rule created!")

        except Exception as e:
            await ctx.send("Something went wrong...")
            print("".join(traceback.format_exception(e, e, e.__traceback__)))  # type: ignore


async def setup(bot):
    await bot.add_cog(AutoModeration(bot))
