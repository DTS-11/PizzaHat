"""Interactive configuration hub for Lucent.

``/setup`` is the single Discord-native entry point for enabling modules and
building simple Trigger → Condition → Action workflows. Advanced configuration
remains available through the mention commands surfaced by ``/help`` and
``/view_setup``.
"""

from __future__ import annotations

import json
from typing import Any

import discord
from discord import ButtonStyle, Interaction, SelectOption, app_commands, ui
from discord.ext import commands
from discord.ext.commands import Context

from core.bot import Lucent
from core.cog import Cog
from core.entitlements import Tier
from services import get_logs, get_protection, get_tickets
from services.protection import ALL_MODULES, CONTENT_MODULES
from utils.embed import green_embed, orange_embed, red_embed
from workflows import (
    CURRENT_SCHEMA_VERSION,
    WorkflowRepository,
    WorkflowValidationError,
    enforce_tier_limits,
    validate_supported_workflow,
    validate_workflow,
)

TRIGGERS: dict[str, str] = {
    "member_join": "A member joins",
    "member_leave": "A member leaves",
    "schedule": "A daily schedule runs (09:00 UTC)",
    "safety_alert": "A safety alert fires",
    "moderation_event": "A moderation action happens",
    "ticket_created": "A ticket is created",
}
CONDITIONS: dict[str, str] = {
    "none": "No condition — always run",
    "account_age_lt": "Account is younger than N days",
    "cooldown_sec": "At most once per N seconds",
    "is_bot": "User is a bot (true/false)",
    "safety_source": "Safety source (antialt/automod/any)",
    "safety_module": "Safety module name",
    "moderation_action": "Moderation action name",
}
ACTIONS: dict[str, str] = {
    "send_message": "Send a channel message",
    "send_dm": "DM the user",
    "timeout_member": "Timeout a member (minutes)",
    "log_channel": "Log a message",
    "open_ticket": "Open a ticket",
    "add_role": "Add a role (by ID)",
    "remove_role": "Remove a role (by ID)",
}


class _ReasonModal(ui.Modal):
    def __init__(self, title: str, label: str, default: str = "") -> None:
        super().__init__(title=title[:45])
        self.value = ui.TextInput(
            label=label[:45], default=default[:100], max_length=100
        )
        self.add_item(self.value)

    async def on_submit(self, interaction: Interaction) -> None:
        await interaction.response.defer(ephemeral=True)


class SetupView(discord.ui.View):
    """Base view restricting controls to the user who opened the setup."""

    def __init__(self, user_id: int, timeout: float = 300) -> None:
        super().__init__(timeout=timeout)
        self.user_id = user_id

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(
            "This setup menu belongs to the person who opened it.", ephemeral=True
        )
        return False


class WorkflowBuilder:
    """In-memory state for a simple workflow built through /setup."""

    def __init__(self, guild_id: int) -> None:
        self.guild_id = guild_id
        self.name = "My workflow"
        self.trigger = "member_join"
        self.condition = "none"
        self.condition_value = ""
        self.action = "send_message"
        self.action_value = "Hello from Lucent!"

    @staticmethod
    def _integer(value: str, label: str, default: int) -> int:
        try:
            return int(value or str(default))
        except (TypeError, ValueError) as exc:
            raise WorkflowValidationError(f"`{label}` must be a whole number.") from exc

    def definition(self) -> dict[str, Any]:
        trigger_config: dict[str, Any]
        if self.trigger == "schedule":
            trigger_config = {
                "frequency": "daily",
                "hour": 9,
                "minute": 0,
                "timezone": "UTC",
            }
        elif self.trigger == "safety_alert":
            trigger_config = {"source": "any"}
        elif self.trigger == "moderation_event":
            trigger_config = {"actions": [], "sources": []}
        else:
            trigger_config = {}

        conditions: list[dict[str, Any]] = []
        if self.condition != "none":
            condition: dict[str, Any] = {"type": self.condition}
            if self.condition == "account_age_lt":
                condition["days"] = self._integer(
                    self.condition_value, "condition days", 7
                )
            elif self.condition == "cooldown_sec":
                condition["seconds"] = self._integer(
                    self.condition_value, "condition seconds", 60
                )
            elif self.condition == "is_bot":
                condition["value"] = self.condition_value.casefold() == "true"
            elif self.condition == "safety_source":
                condition["source"] = self.condition_value or "any"
            elif self.condition == "safety_module":
                condition["module"] = self.condition_value or "automod"
            elif self.condition == "moderation_action":
                condition["action"] = self.condition_value or "warn"
            conditions.append(condition)

        action: dict[str, Any] = {"type": self.action}
        if self.action in {"send_message", "send_dm", "log_channel"}:
            action["message"] = self.action_value or "Workflow action"
        elif self.action == "timeout_member":
            action["minutes"] = self._integer(self.action_value, "action minutes", 10)
        elif self.action == "open_ticket":
            action["panel_name"] = self.action_value or "Support"
        elif self.action in {"add_role", "remove_role"}:
            action["role_id"] = self._integer(self.action_value, "action role ID", 0)

        return {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "name": self.name,
            "trigger_type": self.trigger,
            "trigger_config": trigger_config,
            "conditions": conditions,
            "actions": [action],
        }


class SetupHubView(SetupView):
    """Top-level module and workflow setup hub."""

    def __init__(self, cog: Setup, guild_id: int, user_id: int) -> None:
        super().__init__(user_id)
        self.cog = cog
        self.guild_id = guild_id
        self.workflow = WorkflowBuilder(guild_id)

    def embed(self) -> discord.Embed:
        em = green_embed(title="Lucent Setup", timestamp=True)
        em.description = (
            "Bring your server operations together in one place. "
            "Use `@Lucent help` for the full command guide."
        )
        if not self.cog.bot.can_read_message_content:
            em.description += (
                " Text-based automod and content workflow triggers are unavailable "
                "because the Message Content intent is off."
            )
        em.add_field(
            name="🛡️  Safety",
            value="Configure Anti-Alt and metadata-based AutoMod protection.",
            inline=False,
        )
        em.add_field(
            name="⚙️  Workflows",
            value="Create an automation with a trigger, optional conditions, and an action.",
            inline=False,
        )
        em.add_field(
            name="📨  Channels",
            value="Choose where Lucent sends server audit logs.",
            inline=False,
        )
        return em

    @ui.button(label="Safety", emoji="\N{SHIELD}", style=ButtonStyle.primary)
    async def safety(self, interaction: Interaction, button: ui.Button) -> None:
        await interaction.response.edit_message(
            embed=await self.cog.safety_embed(self.guild_id),
            view=SetupSafetyView(self),
        )

    @ui.button(label="Workflows", emoji="\N{GEAR}", style=ButtonStyle.primary)
    async def workflows(self, interaction: Interaction, button: ui.Button) -> None:
        view = WorkflowTypeView(self)
        await interaction.response.edit_message(
            embed=self.cog.workflow_embed(self.workflow), view=view
        )

    @ui.button(label="Channels", emoji="\N{ENVELOPE}", style=ButtonStyle.secondary)
    async def channels(self, interaction: Interaction, button: ui.Button) -> None:
        await interaction.response.edit_message(
            embed=await self.cog.channels_embed(self.guild_id),
            view=SetupChannelsView(self),
        )


class SetupSafetyView(SetupView):
    def __init__(self, parent: SetupHubView) -> None:
        super().__init__(parent.user_id)
        self.parent = parent

    @ui.select(
        placeholder="Toggle a safety module…",
        options=[
            SelectOption(label=module, value=module) for module in ALL_MODULES[:25]
        ],
    )
    async def module(self, interaction: Interaction, select: ui.Select) -> None:
        module = select.values[0]
        if (
            module in CONTENT_MODULES
            and not self.parent.cog.bot.can_read_message_content
        ):
            await interaction.response.send_message(
                embed=red_embed(
                    description=(
                        f"{self.parent.cog.bot.no} `{module}` needs the Message Content "
                        "intent, which is not enabled."
                    )
                ),
                ephemeral=True,
            )
            return
        tier = await self.parent.cog.tier(self.parent.guild_id)
        required = self.parent.cog.protection.required_tier(module)
        if tier < required:
            await interaction.response.send_message(
                embed=red_embed(
                    description=f"{self.parent.cog.bot.no} `{module}` requires {required.name}."
                ),
                ephemeral=True,
            )
            return

        current = await self.parent.cog.protection.module_enabled(
            self.parent.guild_id, module
        )

        def mutate(config: dict[str, Any]) -> None:
            entry = dict(config.get(module) or {})
            entry["enabled"] = not current
            config[module] = entry
            config["enabled"] = True

        await self.parent.cog.protection.update(self.parent.guild_id, "automod", mutate)
        state = "enabled" if not current else "disabled"
        await interaction.response.edit_message(
            embed=orange_embed(
                description=f"{self.parent.cog.bot.yes} `{module}` {state}."
            ),
            view=self,
        )

    @ui.button(label="Back", style=ButtonStyle.gray)
    async def back(self, interaction: Interaction, button: ui.Button) -> None:
        await interaction.response.edit_message(
            embed=self.parent.embed(), view=self.parent
        )


class WorkflowTypeView(SetupView):
    def __init__(self, parent: SetupHubView) -> None:
        super().__init__(parent.user_id)
        self.parent = parent

    @ui.select(
        placeholder="Trigger…",
        options=[
            SelectOption(label=label, value=value) for value, label in TRIGGERS.items()
        ],
    )
    async def trigger(self, interaction: Interaction, select: ui.Select) -> None:
        self.parent.workflow.trigger = select.values[0]
        await interaction.response.edit_message(
            embed=self.parent.cog.workflow_embed(self.parent.workflow), view=self
        )

    @ui.select(
        placeholder="Condition…",
        options=[
            SelectOption(label=label, value=value)
            for value, label in CONDITIONS.items()
        ],
    )
    async def condition(self, interaction: Interaction, select: ui.Select) -> None:
        self.parent.workflow.condition = select.values[0]
        if self.parent.workflow.condition != "none":
            modal = _ReasonModal("Condition value", "Value for this condition")
            await interaction.response.send_modal(modal)
            await modal.wait()
            self.parent.workflow.condition_value = str(modal.value.value)
            await interaction.edit_original_response(
                embed=self.parent.cog.workflow_embed(self.parent.workflow), view=self
            )
        else:
            await interaction.response.edit_message(
                embed=self.parent.cog.workflow_embed(self.parent.workflow), view=self
            )

    @ui.select(
        placeholder="Action…",
        options=[
            SelectOption(label=label, value=value) for value, label in ACTIONS.items()
        ],
    )
    async def action(self, interaction: Interaction, select: ui.Select) -> None:
        self.parent.workflow.action = select.values[0]
        modal = _ReasonModal(
            "Action value",
            "Message, minutes, or role ID",
            self.parent.workflow.action_value,
        )
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.parent.workflow.action_value = str(modal.value.value)
        await interaction.edit_original_response(
            embed=self.parent.cog.workflow_embed(self.parent.workflow), view=self
        )

    @ui.button(label="Name", style=ButtonStyle.secondary)
    async def name(self, interaction: Interaction, button: ui.Button) -> None:
        modal = _ReasonModal("Workflow name", "Name", self.parent.workflow.name)
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.parent.workflow.name = str(modal.value.value) or "My workflow"
        await interaction.edit_original_response(
            embed=self.parent.cog.workflow_embed(self.parent.workflow), view=self
        )

    @ui.button(label="Review", style=ButtonStyle.primary)
    async def review(self, interaction: Interaction, button: ui.Button) -> None:
        try:
            definition = self.parent.cog.prepare_workflow(
                self.parent.workflow.definition()
            )
        except WorkflowValidationError as exc:
            await interaction.response.send_message(
                embed=red_embed(description=f"{self.parent.cog.bot.no} {exc}"),
                ephemeral=True,
            )
            return
        preview = json.dumps(definition, indent=2)[:900]
        embed = green_embed(title="Review workflow", timestamp=True)
        embed.description = f"```json\n{preview}\n```"
        await interaction.response.edit_message(
            embed=embed, view=WorkflowReviewView(self.parent)
        )

    @ui.button(label="Back", style=ButtonStyle.gray)
    async def back(self, interaction: Interaction, button: ui.Button) -> None:
        await interaction.response.edit_message(
            embed=self.parent.embed(), view=self.parent
        )


class WorkflowReviewView(SetupView):
    def __init__(self, parent: SetupHubView) -> None:
        super().__init__(parent.user_id)
        self.parent = parent

    @ui.button(label="Enable", style=ButtonStyle.success)
    async def enable(self, interaction: Interaction, button: ui.Button) -> None:
        try:
            definition = self.parent.cog.prepare_workflow(
                self.parent.workflow.definition()
            )
            repo = self.parent.cog.repo
            if not repo.available:
                raise WorkflowValidationError("Workflow storage is unavailable.")
            await enforce_tier_limits(
                self.parent.cog.bot,
                self.parent.guild_id,
                actions=definition["actions"],
                enabled=True,
            )
            created = await repo.create(
                self.parent.guild_id, definition, interaction.user.id
            )
            if created is None:
                raise WorkflowValidationError("Could not create the workflow.")
            await self.parent.cog.invalidate_workflows(self.parent.guild_id)
        except WorkflowValidationError as exc:
            await interaction.response.send_message(
                embed=red_embed(description=f"{self.parent.cog.bot.no} {exc}"),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=green_embed(
                description=f"{self.parent.cog.bot.yes} Workflow enabled."
            ),
            ephemeral=True,
        )

    @ui.button(label="Back", style=ButtonStyle.gray)
    async def back(self, interaction: Interaction, button: ui.Button) -> None:
        await interaction.response.edit_message(
            embed=self.parent.cog.workflow_embed(self.parent.workflow),
            view=WorkflowTypeView(self.parent),
        )


class _LogChannelSelect(ui.ChannelSelect):
    def __init__(self, parent: SetupHubView) -> None:
        super().__init__(
            placeholder="Choose a log channel…",
            channel_types=[discord.ChannelType.text],
        )
        self.parent = parent

    async def callback(self, interaction: Interaction) -> None:
        channel = self.values[0]
        await self.parent.cog.logs.set_channel(
            self.parent.guild_id, channel.id, modules=["all"]
        )
        guild_logs = self.parent.cog.bot.get_cog("GuildLogs")
        clear = getattr(guild_logs, "clear_config_cache", None)
        if callable(clear):
            clear(self.parent.guild_id)
        await interaction.response.edit_message(
            embed=green_embed(
                description=f"{self.parent.cog.bot.yes} Log channel set to {channel.mention}."
            ),
            view=self.view,
        )


class SetupChannelsView(SetupView):
    def __init__(self, parent: SetupHubView) -> None:
        super().__init__(parent.user_id)
        self.parent = parent
        self.add_item(_LogChannelSelect(parent))

    @ui.button(label="Back", style=ButtonStyle.gray)
    async def back(self, interaction: Interaction, button: ui.Button) -> None:
        await interaction.response.edit_message(
            embed=self.parent.embed(), view=self.parent
        )


class SetupCategorySelect(ui.Select):
    def __init__(self, cog: Setup, guild_id: int) -> None:
        self.cog = cog
        self.guild_id = guild_id
        super().__init__(
            placeholder="Choose a configuration area…",
            options=[
                SelectOption(
                    label="Safety and AutoMod",
                    value="safety",
                    description="Anti-Alt and metadata-only safety modules",
                ),
                SelectOption(
                    label="Workflows",
                    value="workflows",
                    description="Automations and tier limits",
                ),
                SelectOption(
                    label="Logging",
                    value="logging",
                    description="Audit log channel and modules",
                ),
                SelectOption(
                    label="Tickets",
                    value="tickets",
                    description="Ticket panels and open threads",
                ),
            ],
        )

    async def callback(self, interaction: Interaction) -> None:
        await interaction.response.defer()
        value = self.values[0]
        if value == "safety":
            embed = await self.cog.safety_embed(self.guild_id)
        elif value == "workflows":
            embed = await self.cog.workflow_status_embed(self.guild_id)
        elif value == "logging":
            embed = await self.cog.channels_embed(self.guild_id)
        else:
            embed = await self.cog.tickets_embed(self.guild_id)
        await interaction.edit_original_response(embed=embed, view=self.view)


class ViewSetupView(SetupView):
    def __init__(self, cog: Setup, guild_id: int, user_id: int) -> None:
        super().__init__(user_id)
        self.cog = cog
        self.guild_id = guild_id
        self.add_item(SetupCategorySelect(cog, guild_id))

    @ui.button(label="Refresh", style=ButtonStyle.secondary)
    async def refresh(self, interaction: Interaction, button: ui.Button) -> None:
        await interaction.response.defer()
        await interaction.edit_original_response(
            embed=await self.cog.overview_embed(self.guild_id), view=self
        )


class Setup(Cog, emoji="\N{GEAR}"):
    """Discord-native configuration surfaces."""

    def __init__(self, bot: Lucent) -> None:
        self.bot = bot
        self.protection = get_protection(bot)
        self.logs = get_logs(bot)
        self.tickets = get_tickets(bot)
        self.repo = WorkflowRepository(bot.db)

    async def tier(self, guild_id: int) -> Tier:
        service = getattr(self.bot, "entitlements", None)
        if service is not None:
            return await service.tier_for(guild_id)
        return Tier.FREE

    def prepare_workflow(self, definition: dict[str, Any]) -> dict[str, Any]:
        """Validate a workflow and reject content-dependent features."""
        validated = validate_workflow(definition)
        validate_supported_workflow(
            validated, can_read_message_content=self.bot.can_read_message_content
        )
        return validated

    async def invalidate_workflows(self, guild_id: int) -> None:
        """Mirror the workflow cog's cache invalidation after a creation."""

        runner = self.bot.get_cog("WorkflowRunner")
        clear = getattr(runner, "clear_cache", None)
        if callable(clear):
            clear(guild_id)
        engine = getattr(runner, "engine", None)
        ensure = getattr(engine, "ensure_schedules", None)
        if callable(ensure):
            await ensure(guild_id)

    async def safety_embed(self, guild_id: int) -> discord.Embed:
        automod = await self.protection.automod(guild_id)
        antialt = await self.protection.antialt(guild_id)
        enabled = [
            name for name in ALL_MODULES if (automod.get(name) or {}).get("enabled")
        ]
        em = green_embed(title="Safety Configuration", timestamp=True)
        em.add_field(
            name="AutoMod",
            value=f"Status: `{'enabled' if automod.get('enabled') else 'disabled'}`\n"
            f"Modules: `{', '.join(enabled) or 'none'}`",
            inline=False,
        )
        em.add_field(
            name="Anti-Alt",
            value=f"Status: `{'enabled' if antialt.get('enabled') else 'disabled'}`\n"
            f"Level: `{antialt.get('level', 1)}`",
            inline=False,
        )
        if not self.bot.can_read_message_content:
            em.add_field(
                name="Unsupported",
                value=f"Message-content modules: `{', '.join(CONTENT_MODULES)}`.",
                inline=False,
            )
        return em

    def workflow_embed(self, workflow: WorkflowBuilder) -> discord.Embed:
        em = green_embed(title="Workflow Builder", timestamp=True)
        em.description = "Build a simple workflow, then review and enable it."
        em.add_field(name="Name", value=workflow.name, inline=True)
        em.add_field(name="Trigger", value=TRIGGERS[workflow.trigger], inline=True)
        em.add_field(
            name="Condition", value=CONDITIONS[workflow.condition], inline=True
        )
        action = ACTIONS[workflow.action]
        if workflow.action_value:
            action += f"\n`{workflow.action_value}`"
        em.add_field(name="Action", value=action, inline=False)
        return em

    async def workflow_status_embed(self, guild_id: int) -> discord.Embed:
        tier = await self.tier(guild_id)
        rows = await self.repo.list_all(guild_id)
        em = green_embed(title="Workflow Configuration", timestamp=True)
        em.add_field(name="Tier", value=tier.name, inline=True)
        em.add_field(name="Workflows", value=str(len(rows)), inline=True)
        em.add_field(
            name="Message content",
            value="supported" if self.bot.can_read_message_content else "not available",
            inline=True,
        )
        em.add_field(
            name="Advanced setup",
            value="Use `@Lucent workflow list` and related mention commands.",
            inline=False,
        )
        return em

    async def channels_embed(self, guild_id: int) -> discord.Embed:
        config = await self.logs.get(guild_id)
        channel_id = config.get("log_channel_id")
        channel = self.bot.get_channel(channel_id) if channel_id else None
        em = green_embed(title="Channel Configuration", timestamp=True)
        em.add_field(
            name="Log channel", value=channel.mention if channel else "not set"
        )
        em.add_field(
            name="Log modules",
            value=", ".join(config.get("log_modules") or []) or "none",
        )
        return em

    async def tickets_embed(self, guild_id: int) -> discord.Embed:
        panels = await self.tickets.list_panels(guild_id)
        em = green_embed(title="Ticket Configuration", timestamp=True)
        em.add_field(name="Panels", value=str(len(panels)), inline=True)
        em.add_field(
            name="Manage panels",
            value="Use `@Lucent tsetup`, `@Lucent tpanels` and `@Lucent tdelete`.",
            inline=False,
        )
        return em

    async def overview_embed(self, guild_id: int) -> discord.Embed:
        em = green_embed(title="Lucent Configuration", timestamp=True)
        automod = await self.protection.automod(guild_id)
        antialt = await self.protection.antialt(guild_id)
        rows = await self.repo.list_all(guild_id)
        panels = await self.tickets.list_panels(guild_id)
        em.description = "Pick a configuration area from the menu below."
        em.add_field(
            name="Safety",
            value=f"AutoMod: `{'on' if automod.get('enabled') else 'off'}`\n"
            f"Anti-Alt: `{'on' if antialt.get('enabled') else 'off'}`",
            inline=True,
        )
        em.add_field(name="Workflows", value=str(len(rows)), inline=True)
        em.add_field(name="Ticket panels", value=str(len(panels)), inline=True)
        return em

    @app_commands.command(name="setup", description="Open the interactive setup hub")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def setup_command(self, interaction: discord.Interaction) -> None:
        """Open the interactive configuration hub."""
        assert interaction.guild is not None
        perms = interaction.user.guild_permissions if interaction.user else None
        if perms is None or not perms.manage_guild:
            await interaction.response.send_message(
                embed=red_embed(description="You need Manage Server to use /setup."),
                ephemeral=True,
            )
            return
        view = SetupHubView(self, interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            embed=view.embed(),
            view=view,
            ephemeral=True,
        )

    @app_commands.command(
        name="view_setup", description="Review this server's configuration"
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def view_setup(self, interaction: discord.Interaction) -> None:
        """Browse the current configuration for this server."""
        assert interaction.guild is not None
        perms = interaction.user.guild_permissions if interaction.user else None
        if perms is None or not perms.manage_guild:
            await interaction.response.send_message(
                embed=red_embed(
                    description="You need Manage Server to use /view_setup."
                ),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(
            embed=await self.overview_embed(interaction.guild.id),
            view=ViewSetupView(self, interaction.guild.id, interaction.user.id),
            ephemeral=True,
        )

    @commands.command(name="setup", hidden=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setup_prefix(self, ctx: Context) -> None:
        """Open the same setup hub from a mention command."""
        assert ctx.guild is not None
        view = SetupHubView(self, ctx.guild.id, ctx.author.id)
        await ctx.send(embed=view.embed(), view=view)

    @commands.command(name="view_setup", hidden=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def view_setup_prefix(self, ctx: Context) -> None:
        """Review the current server configuration."""
        assert ctx.guild is not None
        await ctx.send(
            embed=await self.overview_embed(ctx.guild.id),
            view=ViewSetupView(self, ctx.guild.id, ctx.author.id),
        )


async def setup(bot: Lucent) -> None:
    await bot.add_cog(Setup(bot))
