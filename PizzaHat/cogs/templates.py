from __future__ import annotations

import json
from typing import Optional

from discord.ext import commands
from discord.ext.commands import Context

from core.bot import PizzaHat
from core.cog import Cog
from utils.embed import (
    ctx_embed,
    embed_from_data,
    green_embed,
    orange_embed,
    red_embed,
    render_template_vars,
)


def _strip_codeblock(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.lstrip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.rstrip("`").strip()
    return text


class Templates(Cog, emoji=1497265635183431770):
    """Embed templates — store reusable rich embeds and link them to any module."""

    def __init__(self, bot: PizzaHat):
        self.bot = bot

    @commands.group(name="template", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def template(self, ctx: Context):
        """List all embed templates for this server."""
        if not ctx.guild or not self.bot.db:
            return

        rows = await self.bot.db.fetch(
            "SELECT id, name, created_at FROM embed_templates WHERE guild_id=$1 ORDER BY id",
            ctx.guild.id,
        )

        p = ctx.prefix
        if not rows:
            return await ctx.send(
                embed=orange_embed(
                    description=(
                        f"No embed templates yet.\n\n"
                        f"**Create one:**\n"
                        f'`{p}template create "My Template" {{"title":"Hello","description":"World","color":5793266}}`\n\n'
                        f"**Supported fields:** `title` `description` `color` (int or `#hex`) "
                        f"`url` `footer` `author` `image` `thumbnail` `fields`\n\n"
                        f"**Template variables:** `{{user}}` `{{user.mention}}` `{{user.name}}` `{{user.id}}` `{{guild}}`\n\n"
                        f"**Link to a module:**\n"
                        f"`{p}template link responder <id> <template_id>`\n"
                        f"`{p}template link schedule <id> <template_id>`\n"
                        f"`{p}template link join welcome <template_id>`\n"
                        f"`{p}template link join dm <template_id>`\n"
                        f"`{p}template link event <id> <template_id>`\n"
                        f"`{p}template link rolemenu <id> <template_id>`\n"
                        f"`{p}template link ticket <panel_id> <template_id>`"
                    )
                )
            )

        lines = [
            f"`#{r['id']}` **{r['name']}** — <t:{int(r['created_at'].timestamp())}:R>"
            for r in rows
        ]
        em = await ctx_embed(
            ctx,
            title="📋  Embed Templates",
            description=(
                f"**{len(rows)}** template(s)\n\n"
                + "\n".join(lines)
                + f"\n\nUse `{p}template preview <id>` to preview."
            ),
        )
        await ctx.send(embed=em)

    @template.command(name="create", aliases=["new", "add"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def template_create(self, ctx: Context, name: str, *, json_data: str):
        """Create an embed template from JSON. Wrap multi-word names in quotes.

        Example:
        template create "Welcome" {"title":"Hi {user}!","description":"Welcome to {guild}!","color":5793266}
        """
        if not ctx.guild or not self.bot.db:
            return

        json_data = _strip_codeblock(json_data)
        try:
            data = json.loads(json_data)
        except json.JSONDecodeError as e:
            return await ctx.send(
                embed=red_embed(description=f"{self.bot.no} Invalid JSON: `{e}`")
            )
        if not isinstance(data, dict):
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Template data must be a JSON object `{{}}`."
                )
            )
        try:
            embed_from_data(data)
        except Exception as e:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Couldn't build embed from that data: `{e}`"
                )
            )

        row = await self.bot.db.fetchrow(
            "INSERT INTO embed_templates (guild_id, name, data, created_by) VALUES ($1,$2,$3,$4) RETURNING id",
            ctx.guild.id,
            name,
            data,
            ctx.author.id,
        )
        p = ctx.prefix
        await ctx.send(
            embed=green_embed(
                description=(
                    f"{self.bot.yes} Template `#{row['id']}` **{name}** created!\n\n"
                    f"Preview: `{p}template preview {row['id']}`\n"
                    f"Link it: `{p}template link <module> ... {row['id']}`"
                )
            )
        )

    @template.command(name="edit", aliases=["update"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def template_edit(self, ctx: Context, template_id: int, *, json_data: str):
        """Replace a template's data with new JSON."""
        if not ctx.guild or not self.bot.db:
            return

        json_data = _strip_codeblock(json_data)
        try:
            data = json.loads(json_data)
        except json.JSONDecodeError as e:
            return await ctx.send(
                embed=red_embed(description=f"{self.bot.no} Invalid JSON: `{e}`")
            )
        if not isinstance(data, dict):
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Template data must be a JSON object `{{}}`."
                )
            )
        try:
            embed_from_data(data)
        except Exception as e:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Couldn't build embed from that data: `{e}`"
                )
            )

        result = await self.bot.db.execute(
            "UPDATE embed_templates SET data=$1 WHERE id=$2 AND guild_id=$3",
            data,
            template_id,
            ctx.guild.id,
        )
        if result == "UPDATE 0":
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Template `#{template_id}` not found."
                )
            )
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Template `#{template_id}` updated. Linked modules will use the new embed immediately."
            )
        )

    @template.command(name="delete", aliases=["del", "remove"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def template_delete(self, ctx: Context, template_id: int):
        """Delete a template. All linked modules fall back to their default embed automatically."""
        if not ctx.guild or not self.bot.db:
            return

        row = await self.bot.db.fetchrow(
            "DELETE FROM embed_templates WHERE id=$1 AND guild_id=$2 RETURNING name",
            template_id,
            ctx.guild.id,
        )
        if not row:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Template `#{template_id}` not found."
                )
            )
        await ctx.send(
            embed=green_embed(
                description=(
                    f"{self.bot.yes} Template `#{template_id}` (**{row['name']}**) deleted.\n"
                    f"Linked modules will fall back to their default embeds."
                )
            )
        )

    @template.command(name="preview", aliases=["show"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def template_preview(self, ctx: Context, template_id: int):
        """Preview a template embed with sample variable values."""
        if not ctx.guild or not self.bot.db:
            return

        row = await self.bot.db.fetchrow(
            "SELECT name, data FROM embed_templates WHERE id=$1 AND guild_id=$2",
            template_id,
            ctx.guild.id,
        )
        if not row or not row["data"]:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Template `#{template_id}` not found."
                )
            )

        try:
            em = embed_from_data(dict(row["data"]))
        except Exception as e:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Failed to render template: `{e}`"
                )
            )

        preview_vars = {
            "user": str(ctx.author),
            "user.mention": ctx.author.mention,
            "user.name": ctx.author.name,
            "user.id": str(ctx.author.id),
            "guild": ctx.guild.name,
            "guild.id": str(ctx.guild.id),
        }
        render_template_vars(em, **preview_vars)

        await ctx.send(
            content=f"Preview of template `#{template_id}` **{row['name']}** (vars filled with your info):",
            embed=em,
        )

    # ── Link subgroup ─────────────────────────────────────────────────────────

    @template.group(name="link", aliases=["set"], invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def template_link(self, ctx: Context):
        """Link a template to a module. Run a subcommand for the target module."""
        p = ctx.prefix
        em = await ctx_embed(
            ctx,
            title="📋  Template Linking",
            description=(
                f"`{p}template link responder <responder_id> [template_id]`\n"
                f"`{p}template link schedule <schedule_id> [template_id]`\n"
                f"`{p}template link join welcome [template_id]`\n"
                f"`{p}template link join dm [template_id]`\n"
                f"`{p}template link event <event_id> [template_id]`\n"
                f"`{p}template link rolemenu <menu_id> [template_id]`\n"
                f"`{p}template link ticket <panel_id> [template_id]`\n\n"
                f"Omit `template_id` to unlink."
            ),
        )
        await ctx.send(embed=em)

    async def _validate_template(self, ctx: Context, template_id: int) -> bool:
        """Returns True if template_id belongs to this guild."""
        if not self.bot.db or not ctx.guild:
            return False
        exists = await self.bot.db.fetchval(
            "SELECT 1 FROM embed_templates WHERE id=$1 AND guild_id=$2",
            template_id,
            ctx.guild.id,
        )
        if not exists:
            await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Template `#{template_id}` not found."
                )
            )
        return bool(exists)

    @template_link.command(name="responder", aliases=["ar"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def link_responder(
        self, ctx: Context, responder_id: int, template_id: Optional[int] = None
    ):
        """Link (or unlink) an embed template to an auto responder."""
        if not ctx.guild or not self.bot.db:
            return
        if template_id and not await self._validate_template(ctx, template_id):
            return

        result = await self.bot.db.execute(
            "UPDATE auto_responders SET template_id=$1 WHERE id=$2 AND guild_id=$3",
            template_id,
            responder_id,
            ctx.guild.id,
        )
        if result == "UPDATE 0":
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Responder `#{responder_id}` not found."
                )
            )
        cog = self.bot.get_cog("AutomationEvents")
        if cog and hasattr(cog, "clear_cache"):
            cog.clear_cache(ctx.guild.id)  # type: ignore
        verb = (
            f"linked template `#{template_id}`" if template_id else "unlinked template"
        )
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Responder `#{responder_id}` {verb}."
            )
        )

    @template_link.command(name="schedule", aliases=["sched"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def link_schedule(
        self, ctx: Context, schedule_id: int, template_id: Optional[int] = None
    ):
        """Link (or unlink) an embed template to a scheduled message."""
        if not ctx.guild or not self.bot.db:
            return
        if template_id and not await self._validate_template(ctx, template_id):
            return

        result = await self.bot.db.execute(
            "UPDATE scheduled_messages SET template_id=$1 WHERE id=$2 AND guild_id=$3",
            template_id,
            schedule_id,
            ctx.guild.id,
        )
        if result == "UPDATE 0":
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Schedule `#{schedule_id}` not found."
                )
            )
        verb = (
            f"linked template `#{template_id}`" if template_id else "unlinked template"
        )
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Schedule `#{schedule_id}` {verb}."
            )
        )

    @template_link.group(name="join", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def link_join(self, ctx: Context):
        """Link templates to join automation. Use `welcome` or `dm` subcommands."""
        p = ctx.prefix
        await ctx.send(
            embed=orange_embed(
                description=(
                    f"`{p}template link join welcome [template_id]` — welcome channel embed\n"
                    f"`{p}template link join dm [template_id]` — DM embed\n\n"
                    f"Omit `template_id` to unlink."
                )
            )
        )

    @link_join.command(name="welcome")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def link_join_welcome(self, ctx: Context, template_id: Optional[int] = None):
        """Link (or unlink) an embed template to the join welcome channel message."""
        if not ctx.guild or not self.bot.db:
            return
        if template_id and not await self._validate_template(ctx, template_id):
            return

        await self.bot.db.execute(
            "INSERT INTO join_automation (guild_id, welcome_template_id) VALUES ($1,$2) "
            "ON CONFLICT (guild_id) DO UPDATE SET welcome_template_id=$2",
            template_id,
            ctx.guild.id,
        )
        cog = self.bot.get_cog("AutomationEvents")
        if cog and hasattr(cog, "clear_cache"):
            cog.clear_cache(ctx.guild.id)  # type: ignore
        verb = (
            f"linked template `#{template_id}`" if template_id else "unlinked template"
        )
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Join welcome message {verb}."
            )
        )

    @link_join.command(name="dm")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def link_join_dm(self, ctx: Context, template_id: Optional[int] = None):
        """Link (or unlink) an embed template to the join welcome DM."""
        if not ctx.guild or not self.bot.db:
            return
        if template_id and not await self._validate_template(ctx, template_id):
            return

        await self.bot.db.execute(
            "INSERT INTO join_automation (guild_id, welcome_dm_template_id) VALUES ($1,$2) "
            "ON CONFLICT (guild_id) DO UPDATE SET welcome_dm_template_id=$2",
            template_id,
            ctx.guild.id,
        )
        cog = self.bot.get_cog("AutomationEvents")
        if cog and hasattr(cog, "clear_cache"):
            cog.clear_cache(ctx.guild.id)  # type: ignore
        verb = (
            f"linked template `#{template_id}`" if template_id else "unlinked template"
        )
        await ctx.send(
            embed=green_embed(description=f"{self.bot.yes} Join welcome DM {verb}.")
        )

    @template_link.command(name="event")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def link_event(
        self, ctx: Context, event_id: int, template_id: Optional[int] = None
    ):
        """Link (or unlink) an embed template to an event action (affects send/dm/log actions)."""
        if not ctx.guild or not self.bot.db:
            return
        if template_id and not await self._validate_template(ctx, template_id):
            return

        result = await self.bot.db.execute(
            "UPDATE event_actions SET template_id=$1 WHERE id=$2 AND guild_id=$3",
            template_id,
            event_id,
            ctx.guild.id,
        )
        if result == "UPDATE 0":
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Event action `#{event_id}` not found."
                )
            )
        cog = self.bot.get_cog("AutomationEvents")
        if cog and hasattr(cog, "clear_cache"):
            cog.clear_cache(ctx.guild.id)  # type: ignore
        verb = (
            f"linked template `#{template_id}`" if template_id else "unlinked template"
        )
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Event action `#{event_id}` {verb}."
            )
        )

    @template_link.command(name="rolemenu", aliases=["rm"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def link_rolemenu(
        self, ctx: Context, menu_id: int, template_id: Optional[int] = None
    ):
        """Link (or unlink) an embed template to a role menu panel."""
        if not ctx.guild or not self.bot.db:
            return
        if template_id and not await self._validate_template(ctx, template_id):
            return

        result = await self.bot.db.execute(
            "UPDATE role_menus SET template_id=$1 WHERE id=$2 AND guild_id=$3",
            template_id,
            menu_id,
            ctx.guild.id,
        )
        if result == "UPDATE 0":
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Role menu `#{menu_id}` not found."
                )
            )
        from cogs_hidden.role_menus import refresh_menu

        await refresh_menu(self.bot, menu_id)
        verb = (
            f"linked template `#{template_id}`" if template_id else "unlinked template"
        )
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Role menu `#{menu_id}` {verb}. Panel refreshed."
            )
        )

    @template_link.command(name="ticket")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def link_ticket(
        self, ctx: Context, panel_id: int, template_id: Optional[int] = None
    ):
        """Link (or unlink) an embed template to a ticket panel (shown when a ticket opens)."""
        if not ctx.guild or not self.bot.db:
            return
        if template_id and not await self._validate_template(ctx, template_id):
            return

        result = await self.bot.db.execute(
            "UPDATE ticket_panels SET template_id=$1 WHERE id=$2 AND guild_id=$3",
            template_id,
            panel_id,
            ctx.guild.id,
        )
        if result == "UPDATE 0":
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Ticket panel `#{panel_id}` not found."
                )
            )
        verb = (
            f"linked template `#{template_id}`" if template_id else "unlinked template"
        )
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Ticket panel `#{panel_id}` {verb}."
            )
        )


async def setup(bot: PizzaHat) -> None:
    await bot.add_cog(Templates(bot))
