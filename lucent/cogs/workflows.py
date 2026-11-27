"""Mention commands for creating and managing automation workflows.

This cog is a thin management surface: validation, persistence, tier limits and
execution all live in the ``workflows`` package. Definitions can be installed
from inline JSON, an attachment, a template, or an exported file. The setup
hub provides a simpler guided builder for common cases.
"""

from __future__ import annotations

import io
import json
from typing import Any, Callable

import discord
from discord.ext import commands
from discord.ext.commands import Context

from core.bot import Lucent
from core.cog import Cog
from utils.embed import ctx_embed, green_embed, orange_embed, red_embed
from workflows import (
    CURRENT_SCHEMA_VERSION,
    WorkflowRepository,
    WorkflowValidationError,
    enforce_tier_limits,
    export_workflow,
    import_workflow,
    resolve_tier,
    validate_supported_workflow,
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

UNAVAILABLE_TEMPLATES = {
    "auto_responder": "requires the Message Content intent",
}

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


class Workflows(Cog, emoji="\N{GEAR}"):
    """Create, inspect and manage workflows through mention commands."""

    def __init__(self, bot: Lucent):
        self.bot = bot
        self.repo = WorkflowRepository(bot.db)

    @commands.group(name="workflow", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def workflow(self, ctx: Context) -> None:
        """Manage automation workflows."""
        if ctx.invoked_subcommand is None:
            await ctx.send(
                embed=green_embed(
                    description=(
                        "Use `@Lucent workflow <command>`. Options: `list`, `view`, "
                        "`toggle`, `delete`, `create`, `import`, `export`, "
                        "`templates`, `status`."
                    )
                )
            )

    @workflow.command(name="list")
    async def workflow_list(self, ctx: Context) -> None:
        """List all workflows and their current status."""

        if not self.repo.available or ctx.guild is None:
            return await self._no_db(ctx)
        tier = await self._tier(ctx.guild.id)
        rows = await self.repo.list_all(ctx.guild.id)
        em = await self._base_embed(ctx, title="Workflows")
        em.description = f"**Tier:** {tier.name}\n\n"
        if not rows:
            em.description += (
                "No workflows yet. Use `@Lucent workflow templates` to add one."
            )
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
        await ctx.send(embed=em)

    @workflow.command(name="view")
    async def workflow_view(self, ctx: Context, workflow_id: int) -> None:
        """Show one definition as portable JSON."""

        if not self.repo.available or ctx.guild is None:
            return await self._no_db(ctx)
        row = await self.repo.get(ctx.guild.id, workflow_id)
        if row is None:
            return await self._not_found(ctx, workflow_id)
        document = json.dumps(export_workflow(row), indent=2, ensure_ascii=False)
        em = await self._base_embed(ctx, title=f"Workflow #{workflow_id}")
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
        await ctx.send(embed=em)

    @workflow.command(name="status")
    async def workflow_status(self, ctx: Context) -> None:
        """Show workflow support and limits for this server."""
        if ctx.guild is None:
            return
        tier = await self._tier(ctx.guild.id)
        rows = await self.repo.list_all(ctx.guild.id)
        em = green_embed(title="Workflow Support", timestamp=True)
        em.add_field(name="Tier", value=tier.name, inline=True)
        em.add_field(name="Workflows", value=str(len(rows)), inline=True)
        em.add_field(
            name="Message content",
            value="supported" if self.bot.can_read_message_content else "not available",
            inline=True,
        )
        em.add_field(
            name="Unsupported",
            value=(
                "Text triggers (`message_create` with `contains_text`), "
                "`contains_text`/`contains_link` conditions, `{content}` and "
                "`from_message` actions."
                if not self.bot.can_read_message_content
                else "None"
            ),
            inline=False,
        )
        await ctx.send(embed=em)

    @workflow.command(name="toggle")
    async def workflow_toggle(self, ctx: Context, workflow_id: int) -> None:
        """Toggle a workflow's enabled state."""

        if not self.repo.available or ctx.guild is None:
            return await self._no_db(ctx)
        row = await self.repo.get(ctx.guild.id, workflow_id)
        if row is None:
            return await self._not_found(ctx, workflow_id)
        new_state = not row["enabled"]
        if new_state:
            try:
                validate_supported_workflow(
                    row, can_read_message_content=self.bot.can_read_message_content
                )
            except WorkflowValidationError as exc:
                return await self._error(ctx, exc)
        try:
            await enforce_tier_limits(
                self.bot,
                ctx.guild.id,
                actions=row["actions"],
                enabled=new_state,
                workflow_id=workflow_id,
            )
        except WorkflowValidationError as exc:
            return await self._error(ctx, exc)
        await self.repo.toggle(ctx.guild.id, workflow_id, new_state)
        await self._invalidated(ctx.guild.id)
        await ctx.send(
            embed=green_embed(
                description=(
                    f"{self.bot.yes} `{row['name']}` is now "
                    f"**{'enabled' if new_state else 'disabled'}**."
                )
            )
        )

    @workflow.command(name="delete")
    async def workflow_delete(self, ctx: Context, workflow_id: int) -> None:
        """Delete a workflow and its persisted state."""

        if not self.repo.available or ctx.guild is None:
            return await self._no_db(ctx)
        if not await self.repo.delete(ctx.guild.id, workflow_id):
            return await self._not_found(ctx, workflow_id)
        await self.repo.clear_state(ctx.guild.id, workflow_id)
        await self.repo.cancel_pending_schedule(ctx.guild.id, workflow_id)
        await self._invalidated(ctx.guild.id)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Workflow `#{workflow_id}` was deleted."
            )
        )

    @workflow.command(name="create")
    async def workflow_create(
        self, ctx: Context, *, definition: str | None = None
    ) -> None:
        """Create a validated workflow from JSON text or an attached file."""

        if not self.repo.available or ctx.guild is None:
            return await self._no_db(ctx)
        raw = definition
        if raw is None and ctx.message.attachments:
            raw = await self._attachment_json(ctx.message.attachments[0])
        await self._install_document(ctx, raw)

    @workflow.command(name="import")
    async def workflow_import(
        self, ctx: Context, *, document: str | None = None
    ) -> None:
        """Import a portable definition, dropping the source guild's IDs."""

        if not self.repo.available or ctx.guild is None:
            return await self._no_db(ctx)
        raw = document
        if raw is None and ctx.message.attachments:
            raw = await self._attachment_json(ctx.message.attachments[0])
        await self._install_document(ctx, raw, portable=True)

    @workflow.command(name="export")
    async def workflow_export(self, ctx: Context, workflow_id: int) -> None:
        """Download a guild-independent JSON definition."""

        if not self.repo.available or ctx.guild is None:
            return await self._no_db(ctx)
        row = await self.repo.get(ctx.guild.id, workflow_id)
        if row is None:
            return await self._not_found(ctx, workflow_id)
        document = json.dumps(export_workflow(row), indent=2, ensure_ascii=False)
        file = discord.File(
            io.BytesIO(document.encode("utf-8")),
            filename=f"workflow-{workflow_id}.json",
        )
        await ctx.send(
            embed=green_embed(
                title=f"Exported: {row['name']}",
                description="Attach this file to `@Lucent workflow import` on another server.",
            ),
            file=file,
        )

    @workflow.command(name="templates")
    async def workflow_templates(
        self,
        ctx: Context,
        template: str | None = None,
        role: discord.Role | None = None,
        *,
        timezone: str = "UTC",
    ) -> None:
        """Show or install a starter workflow."""

        if not self.repo.available or ctx.guild is None:
            return await self._no_db(ctx)
        if template is None:
            em = await self._base_embed(ctx, title="Starter Workflow Templates")
            em.description = (
                "Pick one with `@Lucent workflow templates <name>`. "
                "Custom triggers such as `reaction_add`, `message_delete` and "
                "`ticket_created` can be installed with `@Lucent workflow create`."
            )
            for key, (name, description, _builder) in STARTER_TEMPLATES.items():
                em.add_field(name=f"`{key}` — {name}", value=description, inline=False)
            em.add_field(
                name="Unavailable",
                value=(
                    "Text-based templates require the Message Content intent: "
                    + ", ".join(UNAVAILABLE_TEMPLATES)
                ),
                inline=False,
            )
            await ctx.send(embed=em)
            return
        if template in UNAVAILABLE_TEMPLATES:
            return await self._error(
                ctx,
                WorkflowValidationError(
                    f"Template `{template}` {UNAVAILABLE_TEMPLATES[template]}."
                ),
            )
        entry = STARTER_TEMPLATES.get(template)
        if entry is None:
            return await self._error(ctx, WorkflowValidationError("Unknown template."))
        target = ctx.channel
        await self._install_document(
            ctx,
            entry[2](
                target.id if isinstance(target, discord.TextChannel) else None,
                role.id if role else None,
                timezone,
            ),
        )

    async def _tier(self, guild_id: int):
        service = getattr(self.bot, "entitlements", None)
        if service is not None:
            return await service.tier_for(guild_id)
        return await resolve_tier(self.bot.db, guild_id)

    async def _attachment_json(self, attachment: discord.Attachment) -> str:
        if attachment.size > 65536:
            raise WorkflowValidationError("Attachment is too large (max 64 KiB).")
        try:
            return (await attachment.read()).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WorkflowValidationError("Attachment must be UTF-8 JSON.") from exc

    async def _install_document(
        self,
        ctx: Context,
        raw: str | None,
        *,
        portable: bool = False,
    ) -> None:
        if ctx.guild is None:
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
            definition = (
                import_workflow(payload) if portable else validate_workflow(payload)
            )
            validate_supported_workflow(
                definition, can_read_message_content=self.bot.can_read_message_content
            )
            tier = await enforce_tier_limits(
                self.bot,
                ctx.guild.id,
                actions=definition["actions"],
                enabled=definition["enabled"],
            )
            created = await self.repo.create(ctx.guild.id, definition, ctx.author.id)
        except WorkflowValidationError as exc:
            return await self._error(ctx, exc)
        if created is None:
            return await self._error(
                ctx,
                WorkflowValidationError("Could not create the workflow."),
            )
        await self._invalidated(ctx.guild.id)
        em = green_embed(
            title=f"Installed: {created['name']}",
            description=(
                "Trigger → Conditions → Actions\n"
                f"**Trigger:** `{created['trigger_type']}`\n"
                f"**Conditions:** `{len(created['conditions'])}`\n"
                f"**Actions:** `{len(created['actions'])}`\n\n"
                f"Tier: **{tier.name}**\n"
                "Use `@Lucent workflow list` to manage it."
            ),
        )
        await ctx.send(embed=em)

    async def _invalidated(self, guild_id: int) -> None:
        runner = self.bot.get_cog("WorkflowRunner")
        clear = getattr(runner, "clear_cache", None)
        if callable(clear):
            clear(guild_id)
            engine = getattr(runner, "engine", None)
            ensure = getattr(engine, "ensure_schedules", None)
            if callable(ensure):
                await ensure(guild_id)

    async def _base_embed(self, ctx: Context, *, title: str) -> discord.Embed:
        return await ctx_embed(ctx, title=title, timestamp=True)

    async def _no_db(self, ctx: Context) -> None:
        await ctx.send(embed=red_embed(description="Database is not available."))

    async def _not_found(self, ctx: Context, workflow_id: int) -> None:
        await ctx.send(
            embed=red_embed(description=f"Workflow `#{workflow_id}` was not found.")
        )

    async def _error(self, ctx: Context, exc: Exception) -> None:
        await ctx.send(embed=red_embed(description=str(exc)))


async def setup(bot: Lucent) -> None:
    await bot.add_cog(Workflows(bot))
