"""User-facing workflow commands.

Contains the ``/workflow`` command group for creating, listing, toggling,
deleting, and instantiating Trigger -> Condition -> Action workflows.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import discord
from discord import app_commands

from core.bot import Tier, Zync
from core.cog import Cog
from utils.embed import green_embed, orange_embed, red_embed
from utils.workflow_schema import (
    WorkflowValidationError,
    enforce_tier_limits,
    get_guild_tier,
    limits_for_tier,
    parse_jsonb,
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
    if channel_id and len(actions) < 2:
        actions.append(
            {
                "type": "log_channel",
                "channel_id": channel_id,
                "message": "🛡️ New account {user} ({user.id}) joined — shielded automatically.",
            }
        )
    return {
        "name": "New-Account Raid Shield",
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
        "message": "Hi {user.mention}! 👋 Thanks for pinging — a staff member will be with you shortly.",
    }
    if channel_id:
        action["channel_id"] = channel_id
    return {
        "name": "Auto-Responder",
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
        "name": "Welcome & Onboarding Flow",
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


def _starboard(
    channel_id: int | None, role_id: int | None, timezone: str
) -> dict[str, Any]:
    action: dict[str, Any] = {
        "type": "send_embed",
        "title": "Highlight Reel",
        "content": "⭐ **{emoji_count}** | {channel}",
        "color": "#FFD700",
        "from_message": True,
        "dedupe": True,
    }
    if channel_id:
        action["channel_id"] = channel_id
    return {
        "name": "Starboard / Highlight Reel",
        "trigger_type": "reaction_add",
        "trigger_config": {"emoji": "⭐", "min_reactions": 5},
        "conditions": [
            {"type": "reaction_count_gte", "count": 5},
            {"type": "not_self_react", "enabled": True},
        ],
        "actions": [action],
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
        "name": "Scheduled Reminder (timezone-aware)",
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
    "starboard": (
        "Starboard / Highlight Reel",
        "Repost messages that reach 5 ⭐ reactions (updates the existing post).",
        _starboard,
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
    "message_create": "Message Creates",
    "reaction_add": "Reaction Added",
    "role_update": "Role Updated",
    "schedule": "Schedule",
    "safety_alert": "Safety Alert",
}


class Workflows(Cog, emoji="\N{GEAR}"):
    """Create, list and manage workflows through slash commands."""

    def __init__(self, bot: Zync):
        self.bot: Zync = bot

    workflow = app_commands.Group(
        name="workflow",
        description="Manage automation workflows",
        guild_only=True,
    )

    @workflow.command(name="list", description="List this server's workflows")
    @app_commands.guild_only()
    async def workflow_list(self, interaction: discord.Interaction) -> None:
        """List all workflows and their current status."""
        if self.bot.db is None or interaction.guild is None:
            await interaction.response.send_message(
                embed=red_embed(description="Database is not available."),
                ephemeral=True,
            )
            return

        tier = await get_guild_tier(self.bot.db, interaction.guild.id)
        limits = limits_for_tier(tier)
        rows = await self.bot.db.fetch(
            "SELECT id, name, enabled, trigger_type, "
            "jsonb_array_length(actions) AS action_count "
            "FROM workflows WHERE guild_id=$1 ORDER BY id",
            interaction.guild.id,
        )
        em = await self._base_embed(interaction, title="Workflows")
        em.description = f"**Tier:** {tier.name} — {limits.describe()}\n\n"
        if not rows:
            em.description += "No workflows yet. Use `/workflow templates` to add one."
        else:
            for row in rows:
                status = "🟢" if row["enabled"] else "🔴"
                em.add_field(
                    name=f"{status} `#{row['id']}` {row['name']}",
                    value=(
                        f"Trigger: `{_TRIGGER_LABELS.get(row['trigger_type'], row['trigger_type'])}`"
                        f" • Actions: `{row['action_count']}`"
                    ),
                    inline=False,
                )
        await interaction.response.send_message(embed=em)

    @workflow.command(name="toggle", description="Enable or disable a workflow")
    @app_commands.describe(workflow_id="Workflow ID from /workflow list")
    @app_commands.guild_only()
    async def workflow_toggle(
        self, interaction: discord.Interaction, workflow_id: int
    ) -> None:
        """Toggle a workflow's enabled state."""
        if self.bot.db is None or interaction.guild is None:
            await interaction.response.send_message(
                embed=red_embed(description="Database is not available."),
                ephemeral=True,
            )
            return
        row = await self.bot.db.fetchrow(
            "SELECT id, name, enabled, actions FROM workflows WHERE id=$1 AND guild_id=$2",
            workflow_id,
            interaction.guild.id,
        )
        if row is None:
            await interaction.response.send_message(
                embed=red_embed(
                    description=f"Workflow `#{workflow_id}` was not found."
                ),
                ephemeral=True,
            )
            return

        new_state = not row["enabled"]
        try:
            await enforce_tier_limits(
                self.bot.db,
                interaction.guild.id,
                actions=list(parse_jsonb(row["actions"]) or []),
                enabled=new_state,
                workflow_id=workflow_id,
            )
        except WorkflowValidationError as exc:
            await interaction.response.send_message(
                embed=red_embed(description=str(exc)), ephemeral=True
            )
            return

        await self.bot.db.execute(
            "UPDATE workflows SET enabled=$1, updated_at=NOW() WHERE id=$2 AND guild_id=$3",
            new_state,
            workflow_id,
            interaction.guild.id,
        )
        self._clear_runner_cache(interaction.guild.id)
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
    async def workflow_delete(
        self, interaction: discord.Interaction, workflow_id: int
    ) -> None:
        """Delete a workflow."""
        if self.bot.db is None or interaction.guild is None:
            await interaction.response.send_message(
                embed=red_embed(description="Database is not available."),
                ephemeral=True,
            )
            return
        result = await self.bot.db.execute(
            "DELETE FROM workflows WHERE id=$1 AND guild_id=$2",
            workflow_id,
            interaction.guild.id,
        )
        if result == "DELETE 0":
            await interaction.response.send_message(
                embed=red_embed(
                    description=f"Workflow `#{workflow_id}` was not found."
                ),
                ephemeral=True,
            )
            return
        self._clear_runner_cache(interaction.guild.id)
        await interaction.response.send_message(
            embed=green_embed(
                description=f"{self.bot.yes} Workflow `#{workflow_id}` was deleted."
            )
        )

    @workflow.command(
        name="templates", description="Install a ready-made workflow in one click"
    )
    @app_commands.describe(
        template="Starter workflow to install",
        channel="Channel used by the workflow (defaults to this channel)",
        role="Role used by the New-Account Raid Shield (optional)",
        timezone="IANA timezone for scheduled reminders (default UTC)",
    )
    @app_commands.choices(template=TEMPLATE_CHOICES)
    @app_commands.guild_only()
    async def workflow_templates(
        self,
        interaction: discord.Interaction,
        template: str | None = None,
        channel: discord.TextChannel | None = None,
        role: discord.Role | None = None,
        timezone: str = "UTC",
    ) -> None:
        """Show or install one of the five starter workflows."""
        if interaction.guild is None or self.bot.db is None:
            await interaction.response.send_message(
                embed=red_embed(description="Database is not available."),
                ephemeral=True,
            )
            return

        if template is None:
            em = await self._base_embed(interaction, title="Starter Workflow Templates")
            em.description = (
                "Pick one with `/workflow templates template:<name>`. "
                "Optionally pass `channel`, `role` and `timezone`."
            )
            for key, (name, description, _builder) in STARTER_TEMPLATES.items():
                em.add_field(name=f"`{key}` — {name}", value=description, inline=False)
            await interaction.response.send_message(embed=em)
            return

        builder = STARTER_TEMPLATES.get(template)
        if builder is None:
            await interaction.response.send_message(
                embed=red_embed(description="Unknown template."), ephemeral=True
            )
            return

        target = channel
        if target is None and isinstance(interaction.channel, discord.TextChannel):
            target = interaction.channel
        try:
            payload = builder[2](
                target.id if target else None,
                role.id if role else None,
                timezone,
            )
            workflow_data = validate_workflow(payload)
            tier = await enforce_tier_limits(
                self.bot.db,
                interaction.guild.id,
                actions=workflow_data["actions"],
                enabled=True,
                tier=await get_guild_tier(self.bot.db, interaction.guild.id),
            )
        except WorkflowValidationError as exc:
            await interaction.response.send_message(
                embed=red_embed(description=str(exc)), ephemeral=True
            )
            return

        await self.bot.db.execute(
            "INSERT INTO workflows "
            "(guild_id, name, enabled, trigger_type, trigger_config, conditions, actions, "
            "created_at, updated_at) "
            "VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, NOW(), NOW())",
            interaction.guild.id,
            workflow_data["name"],
            True,
            workflow_data["trigger_type"],
            json.dumps(workflow_data["trigger_config"]),
            json.dumps(workflow_data["conditions"]),
            json.dumps(workflow_data["actions"]),
        )
        self._clear_runner_cache(interaction.guild.id)
        em = green_embed(
            title=f"Installed: {workflow_data['name']}",
            description=(
                "Trigger → Conditions → Actions\n"
                f"**Trigger:** `{workflow_data['trigger_type']}`\n"
                f"**Conditions:** `{len(workflow_data['conditions'])}`\n"
                f"**Actions:** `{len(workflow_data['actions'])}`\n\n"
                f"Tier: **{tier.name}** — {limits_for_tier(tier).describe()}\n"
                "Use `/workflow list` to manage it."
            ),
        )
        await interaction.response.send_message(embed=em)

    # ── helpers ───────────────────────────────────────────────────────────────

    async def _base_embed(
        self, interaction: discord.Interaction, *, title: str
    ) -> discord.Embed:
        if interaction.guild and self.bot.db:
            from utils.embed import guild_embed

            return await guild_embed(self.bot.db, interaction.guild.id, title=title)
        return orange_embed(title=title)

    def _clear_runner_cache(self, guild_id: int) -> None:
        runner = self.bot.get_cog("WorkflowRunner")
        clear = getattr(runner, "clear_cache", None)
        if callable(clear):
            clear(guild_id)


async def setup(bot: Zync) -> None:
    await bot.add_cog(Workflows(bot))
