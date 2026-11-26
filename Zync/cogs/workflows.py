"""Slash commands for creating and managing automation workflows.

This cog is a thin management surface: validation, persistence, tier limits and
execution all live in the ``workflows`` package. Definitions can be installed
from a JSON modal, inline text, an attachment, a template, or an exported file.
"""

from __future__ import annotations

import io
import json
from typing import Any, Callable

import discord
from discord import app_commands

from core.bot import Zync
from core.cog import Cog
from utils.embed import green_embed, orange_embed, red_embed
from workflows import (
    CURRENT_SCHEMA_VERSION,
    WorkflowRepository,
    WorkflowValidationError,
    enforce_tier_limits,
    export_workflow,
    import_workflow,
    resolve_tier,
    validate_workflow,
)

Builder = Callable[[int | None, int | None, str], dict[str, Any]]


def _raid_shield(
    channel_id: int | None, role_id: int | None, timezone: str
) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    if role_id:
        actions.append({"type": "add_role", "role_id": role_id})
    actions.append({"type": "timeout_member", "minutes": 60})
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "name": "New-Account Raid Shield",
        "description": "Restrict and time out accounts younger than seven days.",
        "trigger_type": "member_join",
        "trigger_config": {},
        "conditions": [{"type": "account_age_lt", "days": 7}],
        "actions": actions,
    }


def _auto_responder(
    channel_id: int | None, role_id: int | None, timezone: str
) -> dict[str, Any]:
    action: dict[str, Any] = {
        "type": "send_message",
        "message": "Hi {user.mention}! 👋 A staff member will be with you shortly.",
    }
    if channel_id:
        action["channel_id"] = channel_id
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "name": "Auto-Responder",
        "description": "Reply to !hello at most once per user every 30 seconds.",
        "trigger_type": "message_create",
        "trigger_config": {"contains_text": "!hello", "match": "contains"},
        "conditions": [
            {"type": "contains_text", "text": "!hello", "match": "contains"},
            {"type": "cooldown_sec", "seconds": 30, "scope": "user"},
        ],
        "actions": [action],
    }


def _welcome(
    channel_id: int | None, role_id: int | None, timezone: str
) -> dict[str, Any]:
    embed_action: dict[str, Any] = {
        "type": "send_embed",
        "title": "Welcome to {guild}!",
        "description": (
            "Welcome {user.mention} 🎉\n\n"
            "Introduce yourself, grab a role from the role menu, and check the rules."
        ),
        "color": "#57F287",
    }
    if channel_id:
        embed_action["channel_id"] = channel_id
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "name": "Welcome & Onboarding Flow",
        "description": "Post a welcome embed in a channel and DM the new member.",
        "trigger_type": "member_join",
        "trigger_config": {},
        "conditions": [],
        "actions": [
            embed_action,
            {
                "type": "send_dm",
                "message": "Welcome to {guild}, {user}! We're glad you're here.",
            },
        ],
    }


def _scheduled_reminder(
    channel_id: int | None, role_id: int | None, timezone: str
) -> dict[str, Any]:
    action: dict[str, Any] = {
        "type": "send_embed",
        "title": "Daily Reminder",
        "description": "It's 09:00 in **{timezone}** — here's your daily check-in reminder!",
        "color": "#FAA61A",
    }
    if channel_id:
        action["channel_id"] = channel_id
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "name": "Scheduled Reminder (timezone-aware)",
        "description": "Send a daily 09:00 reminder in your chosen IANA timezone.",
        "trigger_type": "schedule",
        "trigger_config": {
            "frequency": "daily",
            "hour": 9,
            "minute": 0,
            "timezone": timezone,
        },
        "conditions": [],
        "actions": [action],
    }


STARTER_TEMPLATES: dict[str, tuple[str, str, Builder]] = {
    "raid_shield": (
        "New-Account Raid Shield",
        "Flag joins younger than 7 days; assign a restricted role and time them out.",
        _raid_shield,
    ),
    "auto_responder": (
        "Auto-Responder",
        "Reply to `!hello` with an on-call ping, at most once per user every 30s.",
        _auto_responder,
    ),
    "welcome_onboarding": (
        "Welcome & Onboarding Flow",
        "Post a welcome embed in a channel and DM the new member.",
        _welcome,
    ),
    "scheduled_reminder": (
        "Scheduled Reminder (timezone-aware)",
        "Send a daily 09:00 reminder in your chosen IANA timezone.",
        _scheduled_reminder,
    ),
}

TEMPLATE_CHOICES = [
    app_commands.Choice(name=f"{index}. {name}", value=key)
    for index, (key, (name, _description, _builder)) in enumerate(
        STARTER_TEMPLATES.items(), start=1
    )
]

_TRIGGER_LABELS = {
    "member_join": "Member Join",
    "member_leave": "Member Leave",
    "message_create": "Message Created",
    "message_delete": "Message Deleted",
    "reaction_add": "Reaction Added",
    "role_update": "Role Updated",
    "schedule": "Schedule",
    "safety_alert": "Safety Alert",
    "moderation_event": "Moderation Event",
    "ticket_created": "Ticket Created",
}


class WorkflowJSONModal(discord.ui.Modal, title="Workflow JSON"):
    """Small JSON editor for definitions too long for a slash option."""

    definition = discord.ui.TextInput(
        label="Workflow JSON",
        style=discord.TextStyle.long,
        max_length=4000,
        placeholder='{"name":"...","trigger_type":"message_create",...}',
    )

    def __init__(self, cog: Workflows) -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog._install_document(interaction, self.definition.value, ephemeral=True)


class Workflows(Cog, emoji="\N{GEAR}"):
    """Create, inspect and manage workflows through slash commands."""

    workflow = app_commands.Group(
        name="workflow",
        description="Manage automation workflows",
        guild_only=True,
    )

    def __init__(self, bot: Zync):
        self.bot = bot
        self.repo = WorkflowRepository(bot.db)

    # ── listing / inspection ────────────────────────────────────────────────

    @workflow.command(name="list", description="List this server's workflows")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def workflow_list(self, interaction: discord.Interaction) -> None:
        """List all workflows and their current status."""

        if not self.repo.available or interaction.guild is None:
            return await self._no_db(interaction)
        tier = await self._tier(interaction.guild.id)
        rows = await self.repo.list_all(interaction.guild.id)
        em = await self._base_embed(interaction, title="Workflows")
        em.description = f"**Tier:** {tier.name}\n\n"
        if not rows:
            em.description += "No workflows yet. Use `/workflow templates` to add one."
        for row in rows:
            status = "🟢" if row["enabled"] else "🔴"
            em.add_field(
                name=f"{status} `#{row['id']}` {row['name']}",
                value=(
                    f"Trigger: `{_TRIGGER_LABELS.get(row['trigger_type'], row['trigger_type'])}`"
                    f" • Actions: `{len(row['actions'])}` • Revision: `{row['revision']}`"
                ),
                inline=False,
            )
        await interaction.response.send_message(embed=em)

    @workflow.command(name="view", description="Inspect a workflow definition")
    @app_commands.describe(workflow_id="Workflow ID from /workflow list")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def workflow_view(
        self, interaction: discord.Interaction, workflow_id: int
    ) -> None:
        """Show one definition as portable JSON."""

        if not self.repo.available or interaction.guild is None:
            return await self._no_db(interaction)
        row = await self.repo.get(interaction.guild.id, workflow_id)
        if row is None:
            return await self._not_found(interaction, workflow_id)
        document = json.dumps(export_workflow(row), indent=2, ensure_ascii=False)
        em = await self._base_embed(interaction, title=f"Workflow #{workflow_id}")
        em.add_field(name="Name", value=row["name"], inline=False)
        em.add_field(name="Description", value=row["description"] or "—", inline=False)
        em.add_field(
            name="Status",
            value="🟢 Enabled" if row["enabled"] else "🔴 Disabled",
            inline=True,
        )
        em.add_field(
            name="Revision",
            value=f"v{row['schema_version']} / r{row['revision']}",
            inline=True,
        )
        em.add_field(
            name="Definition",
            value=f"```json\n{document[:3800]}\n```",
            inline=False,
        )
        await interaction.response.send_message(embed=em, ephemeral=True)

    # ── lifecycle ───────────────────────────────────────────────────────────

    @workflow.command(name="toggle", description="Enable or disable a workflow")
    @app_commands.describe(workflow_id="Workflow ID from /workflow list")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def workflow_toggle(
        self, interaction: discord.Interaction, workflow_id: int
    ) -> None:
        """Toggle a workflow's enabled state."""

        if not self.repo.available or interaction.guild is None:
            return await self._no_db(interaction)
        row = await self.repo.get(interaction.guild.id, workflow_id)
        if row is None:
            return await self._not_found(interaction, workflow_id)
        new_state = not row["enabled"]
        try:
            await enforce_tier_limits(
                self.bot,
                interaction.guild.id,
                actions=row["actions"],
                enabled=new_state,
                workflow_id=workflow_id,
            )
        except WorkflowValidationError as exc:
            return await self._error(interaction, exc)
        await self.repo.toggle(interaction.guild.id, workflow_id, new_state)
        await self._invalidated(interaction.guild.id)
        await interaction.response.send_message(
            embed=green_embed(
                description=(
                    f"{self.bot.yes} `{row['name']}` is now "
                    f"**{'enabled' if new_state else 'disabled'}**."
                )
            )
        )

    @workflow.command(name="delete", description="Permanently delete a workflow")
    @app_commands.describe(workflow_id="Workflow ID from /workflow list")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def workflow_delete(
        self, interaction: discord.Interaction, workflow_id: int
    ) -> None:
        """Delete a workflow and its persisted state."""

        if not self.repo.available or interaction.guild is None:
            return await self._no_db(interaction)
        if not await self.repo.delete(interaction.guild.id, workflow_id):
            return await self._not_found(interaction, workflow_id)
        await self.repo.clear_state(interaction.guild.id, workflow_id)
        await self.repo.cancel_pending_schedule(interaction.guild.id, workflow_id)
        await self._invalidated(interaction.guild.id)
        await interaction.response.send_message(
            embed=green_embed(
                description=f"{self.bot.yes} Workflow `#{workflow_id}` was deleted."
            )
        )

    # ── creation / portability ──────────────────────────────────────────────

    @workflow.command(name="create", description="Create a workflow from JSON")
    @app_commands.describe(
        definition='Workflow JSON, e.g. {"name":"Ping","trigger_type":"message_create",...}',
        attachment="Optional .json attachment containing the definition",
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def workflow_create(
        self,
        interaction: discord.Interaction,
        definition: str | None = None,
        attachment: discord.Attachment | None = None,
    ) -> None:
        """Create a validated workflow from text, a file or a modal."""

        if not self.repo.available or interaction.guild is None:
            return await self._no_db(interaction)
        if definition is None and attachment is None:
            await interaction.response.send_modal(WorkflowJSONModal(self))
            return
        raw = definition
        if attachment is not None:
            if attachment.size > 65536:
                return await self._error(
                    interaction, WorkflowValidationError("Attachment is too large (max 64 KiB).")
                )
            try:
                raw = (await attachment.read()).decode("utf-8")
            except UnicodeDecodeError:
                return await self._error(
                    interaction, WorkflowValidationError("Attachment must be UTF-8 JSON.")
                )
        await self._install_document(interaction, raw, ephemeral=False)

    @workflow.command(name="import", description="Import a workflow export")
    @app_commands.describe(
        document="Portable workflow JSON from /workflow export",
        attachment="Optional .json attachment containing the export",
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def workflow_import(
        self,
        interaction: discord.Interaction,
        document: str | None = None,
        attachment: discord.Attachment | None = None,
    ) -> None:
        """Import a portable definition, dropping the source guild's IDs."""

        if not self.repo.available or interaction.guild is None:
            return await self._no_db(interaction)
        raw = document
        if attachment is not None:
            if attachment.size > 65536:
                return await self._error(
                    interaction, WorkflowValidationError("Attachment is too large (max 64 KiB).")
                )
            try:
                raw = (await attachment.read()).decode("utf-8")
            except UnicodeDecodeError:
                return await self._error(
                    interaction, WorkflowValidationError("Attachment must be UTF-8 JSON.")
                )
        await self._install_document(interaction, raw, ephemeral=False, portable=True)

    @workflow.command(name="export", description="Export a workflow as JSON")
    @app_commands.describe(workflow_id="Workflow ID from /workflow list")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def workflow_export(
        self, interaction: discord.Interaction, workflow_id: int
    ) -> None:
        """Download a guild-independent JSON definition."""

        if not self.repo.available or interaction.guild is None:
            return await self._no_db(interaction)
        row = await self.repo.get(interaction.guild.id, workflow_id)
        if row is None:
            return await self._not_found(interaction, workflow_id)
        document = json.dumps(export_workflow(row), indent=2, ensure_ascii=False)
        file = discord.File(
            io.BytesIO(document.encode("utf-8")),
            filename=f"workflow-{workflow_id}.json",
        )
        await interaction.response.send_message(
            embed=green_embed(
                title=f"Exported: {row['name']}",
                description="Attach this file to `/workflow import` on another server.",
            ),
            file=file,
            ephemeral=True,
        )

    @workflow.command(
        name="templates", description="Install a ready-made workflow"
    )
    @app_commands.describe(
        template="Starter workflow to install",
        channel="Channel used by the workflow (defaults to this channel)",
        role="Role used by the New-Account Raid Shield (optional)",
        timezone="IANA timezone for scheduled reminders (default UTC)",
    )
    @app_commands.choices(template=TEMPLATE_CHOICES)
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def workflow_templates(
        self,
        interaction: discord.Interaction,
        template: str | None = None,
        channel: discord.TextChannel | None = None,
        role: discord.Role | None = None,
        timezone: str = "UTC",
    ) -> None:
        """Show or install a starter workflow."""

        if not self.repo.available or interaction.guild is None:
            return await self._no_db(interaction)
        if template is None:
            em = await self._base_embed(interaction, title="Starter Workflow Templates")
            em.description = (
                "Pick one with `/workflow templates template:<name>`. "
                "Custom triggers such as `reaction_add`, `message_delete` and "
                "`ticket_created` can be installed with `/workflow create`."
            )
            for key, (name, description, _builder) in STARTER_TEMPLATES.items():
                em.add_field(name=f"`{key}` — {name}", value=description, inline=False)
            await interaction.response.send_message(embed=em)
            return
        entry = STARTER_TEMPLATES.get(template)
        if entry is None:
            return await self._error(interaction, WorkflowValidationError("Unknown template."))
        target = channel
        if target is None and isinstance(interaction.channel, discord.TextChannel):
            target = interaction.channel
        await self._install_document(
            interaction,
            entry[2](target.id if target else None, role.id if role else None, timezone),
            ephemeral=False,
        )

    # ── helpers ─────────────────────────────────────────────────────────────

    async def _tier(self, guild_id: int):
        service = getattr(self.bot, "entitlements", None)
        if service is not None:
            return await service.tier_for(guild_id)
        return await resolve_tier(self.bot.db, guild_id)

    async def _install_document(
        self,
        interaction: discord.Interaction,
        raw: str | None,
        *,
        ephemeral: bool,
        portable: bool = False,
    ) -> None:
        if interaction.guild is None:
            return
        try:
            if not raw:
                raise WorkflowValidationError("No workflow JSON was provided.")
            try:
                payload = json.loads(raw)
            except (TypeError, ValueError) as exc:
                raise WorkflowValidationError(
                    f"Invalid JSON: {exc}", field="workflow"
                ) from exc
            definition = import_workflow(payload) if portable else validate_workflow(payload)
            tier = await enforce_tier_limits(
                self.bot,
                interaction.guild.id,
                actions=definition["actions"],
                enabled=definition["enabled"],
            )
            created = await self.repo.create(
                interaction.guild.id, definition, interaction.user.id
            )
        except WorkflowValidationError as exc:
            return await self._error(interaction, exc, ephemeral=ephemeral)
        if created is None:
            return await self._error(
                interaction,
                WorkflowValidationError("Could not create the workflow."),
                ephemeral=ephemeral,
            )
        await self._invalidated(interaction.guild.id)
        em = green_embed(
            title=f"Installed: {created['name']}",
            description=(
                "Trigger → Conditions → Actions\n"
                f"**Trigger:** `{created['trigger_type']}`\n"
                f"**Conditions:** `{len(created['conditions'])}`\n"
                f"**Actions:** `{len(created['actions'])}`\n\n"
                f"Tier: **{tier.name}**\n"
                "Use `/workflow list` to manage it."
            ),
        )
        if ephemeral and interaction.response.is_done():
            await interaction.followup.send(embed=em, ephemeral=True)
        elif ephemeral:
            await interaction.response.send_message(embed=em, ephemeral=True)
        else:
            await interaction.response.send_message(embed=em)

    async def _invalidated(self, guild_id: int) -> None:
        runner = self.bot.get_cog("WorkflowRunner")
        clear = getattr(runner, "clear_cache", None)
        if callable(clear):
            clear(guild_id)
            engine = getattr(runner, "engine", None)
            ensure = getattr(engine, "ensure_schedules", None)
            if callable(ensure):
                await ensure(guild_id)

    async def _base_embed(
        self, interaction: discord.Interaction, *, title: str
    ) -> discord.Embed:
        if interaction.guild and self.bot.db:
            from utils.embed import guild_embed

            return await guild_embed(self.bot.db, interaction.guild.id, title=title)
        return orange_embed(title=title)

    async def _no_db(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=red_embed(description="Database is not available."), ephemeral=True
        )

    async def _not_found(
        self, interaction: discord.Interaction, workflow_id: int
    ) -> None:
        await interaction.response.send_message(
            embed=red_embed(description=f"Workflow `#{workflow_id}` was not found."),
            ephemeral=True,
        )

    async def _error(
        self,
        interaction: discord.Interaction,
        exc: Exception,
        *,
        ephemeral: bool = True,
    ) -> None:
        embed = red_embed(description=str(exc))
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: Zync) -> None:
    await bot.add_cog(Workflows(bot))
