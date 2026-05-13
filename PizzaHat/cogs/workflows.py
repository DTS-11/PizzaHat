from __future__ import annotations

import time

import discord
from discord.ext import commands
from discord.ext.commands import Context

from core.bot import PizzaHat
from core.cog import Cog
from utils.embed import ctx_embed, green_embed, orange_embed, red_embed

SESSION_TIMEOUT = 600  # seconds

VALID_TRIGGERS: dict[str, str] = {
    "member_join": "Member joins the server",
    "member_leave": "Member leaves the server",
    "message_contains": "Message contains specific text",
    "discord_invite": "Message contains a Discord invite link",
}

VALID_ACTIONS: dict[str, str] = {
    "send_message": "Send a message to a channel",
    "give_role": "Give a role to the user",
    "remove_role": "Remove a role from the user",
    "dm_user": "Send a DM to the user",
    "delete_message": "Delete the triggering message",
    "warn": "Warn the user",
    "timeout": "Timeout the user for N minutes",
    "kick": "Kick the user",
    "ban": "Ban the user",
    "log": "Log the action to a channel",
}

# Only valid when triggered by a message event
MESSAGE_ONLY_ACTIONS = {"delete_message"}

# Require the member to still be in the server
MEMBER_LEAVE_BLOCKED = {"give_role", "remove_role", "timeout", "kick", "ban"}

# Triggers that involve a message
MESSAGE_TRIGGERS = {"message_contains", "discord_invite"}


def _action_summary(action_type: str, config: dict) -> str:
    if action_type == "send_message":
        ch = f"<#{config.get('channel_id', '?')}>"
        msg = config.get("message", "")[:50]
        return f"in {ch}: `{msg}`"
    if action_type in ("give_role", "remove_role"):
        return f"<@&{config.get('role_id', '?')}>"
    if action_type == "dm_user":
        return f"`{config.get('message', '')[:50]}`"
    if action_type == "delete_message":
        return "—"
    if action_type == "warn":
        return config.get("reason", "Workflow automation")[:50]
    if action_type == "timeout":
        return f"{config.get('duration', 0) // 60} minute(s)"
    if action_type in ("kick", "ban"):
        return config.get("reason", "Workflow automation")[:50]
    if action_type == "log":
        ch = f"<#{config.get('channel_id', '?')}>"
        return f"in {ch}: `{config.get('message', '')[:50]}`"
    return "—"


async def _resolve_channel(ctx: Context, text: str) -> discord.TextChannel | None:
    if not ctx.guild:
        return None
    text = text.strip().lstrip("<#").rstrip(">")
    try:
        ch = ctx.guild.get_channel(int(text))
        return ch if isinstance(ch, discord.TextChannel) else None
    except (ValueError, TypeError):
        return None


async def _resolve_role(ctx: Context, text: str) -> discord.Role | None:
    if not ctx.guild:
        return None
    text = text.strip().lstrip("<@&").rstrip(">")
    try:
        return ctx.guild.get_role(int(text))
    except (ValueError, TypeError):
        return None


class WorkflowCommands(Cog, emoji="⚙️"):
    """Create automated workflows and server automation rules."""

    def __init__(self, bot: PizzaHat):
        self.bot = bot
        self._sessions: dict[tuple[int, int], dict] = {}

    # ── session helpers ──────────────────────────────────────────────────────

    def _get_session(self, guild_id: int, user_id: int) -> dict | None:
        key = (guild_id, user_id)
        session = self._sessions.get(key)
        if not session:
            return None
        if time.monotonic() - session["_ts"] > SESSION_TIMEOUT:
            del self._sessions[key]
            return None
        return session

    def _put_session(self, guild_id: int, user_id: int, data: dict) -> None:
        data["_ts"] = time.monotonic()
        self._sessions[(guild_id, user_id)] = data

    def _drop_session(self, guild_id: int, user_id: int) -> None:
        self._sessions.pop((guild_id, user_id), None)

    def _clear_workflow_cache(self, guild_id: int) -> None:
        cog = self.bot.get_cog("WorkflowEvents")
        if cog and hasattr(cog, "clear_cache"):
            cog.clear_cache(guild_id)  # type: ignore

    # ── command group ────────────────────────────────────────────────────────

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def workflow(self, ctx: Context):
        """Workflow and automation system hub."""

        if not ctx.guild:
            return

        count = 0
        if self.bot.db:
            count = await self.bot.db.fetchval(
                "SELECT COUNT(*) FROM workflows WHERE guild_id=$1", ctx.guild.id
            ) or 0

        session = self._get_session(ctx.guild.id, ctx.author.id)
        session_line = ""
        if session:
            trigger = session.get("trigger_type") or "not set"
            n = len(session.get("actions", []))
            session_line = (
                f"\n\n**Active session:** `{session['name']}` — "
                f"trigger: `{trigger}`, {n} action(s)\n"
                f"Run `{ctx.prefix}workflow save` to save or `{ctx.prefix}workflow cancel` to discard."
            )

        em = await ctx_embed(
            ctx,
            title="⚙️  Workflow & Automation",
            description=f"Active workflows: **{count}**{session_line}",
        )
        em.add_field(
            name="Build a Workflow",
            value=(
                f"`{ctx.prefix}workflow create <name>`\n"
                f"`{ctx.prefix}workflow trigger <type> [value]`\n"
                f"`{ctx.prefix}workflow action <type> [args]`\n"
                f"`{ctx.prefix}workflow save` / `{ctx.prefix}workflow cancel`"
            ),
            inline=False,
        )
        em.add_field(
            name="Manage Workflows",
            value=(
                f"`{ctx.prefix}workflow list`\n"
                f"`{ctx.prefix}workflow show <id>`\n"
                f"`{ctx.prefix}workflow enable/disable <id>`\n"
                f"`{ctx.prefix}workflow delete <id>`"
            ),
            inline=False,
        )
        em.add_field(
            name="Triggers",
            value="\n".join(f"`{t}` — {d}" for t, d in VALID_TRIGGERS.items()),
            inline=False,
        )
        em.add_field(
            name="Actions",
            value="\n".join(f"`{a}` — {d}" for a, d in VALID_ACTIONS.items()),
            inline=False,
        )
        em.add_field(
            name="Template Variables",
            value="`{user}` `{user.mention}` `{user.name}` `{user.id}` `{guild}` `{channel}`",
            inline=False,
        )
        await ctx.send(embed=em)

    # ── create ───────────────────────────────────────────────────────────────

    @workflow.command(name="create")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def workflow_create(self, ctx: Context, *, name: str):
        """Start a new workflow session with the given name."""

        if not ctx.guild:
            return

        existing = self._get_session(ctx.guild.id, ctx.author.id)
        if existing:
            return await ctx.send(
                embed=orange_embed(
                    description=(
                        f"{self.bot.no} You already have an active session for **{existing['name']}**.\n"
                        f"Run `{ctx.prefix}workflow save` to save it or `{ctx.prefix}workflow cancel` to discard."
                    )
                )
            )

        self._put_session(ctx.guild.id, ctx.author.id, {
            "name": name,
            "trigger_type": None,
            "trigger_config": {},
            "actions": [],
        })
        await ctx.send(
            embed=green_embed(
                description=(
                    f"{self.bot.yes} Started **{name}**.\n"
                    f"Set a trigger: `{ctx.prefix}workflow trigger <type>`\n"
                    f"Available: {', '.join(f'`{t}`' for t in VALID_TRIGGERS)}"
                )
            )
        )

    # ── trigger ──────────────────────────────────────────────────────────────

    @workflow.command(name="trigger")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def workflow_trigger(self, ctx: Context, trigger_type: str, *, value: str = ""):
        """Set the trigger for the active workflow session."""

        if not ctx.guild:
            return

        session = self._get_session(ctx.guild.id, ctx.author.id)
        if not session:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} No active session. Run `{ctx.prefix}workflow create <name>` first."
                )
            )

        trigger_type = trigger_type.lower()
        if trigger_type not in VALID_TRIGGERS:
            return await ctx.send(
                embed=red_embed(
                    description=(
                        f"{self.bot.no} Unknown trigger `{trigger_type}`.\n"
                        f"Available: {', '.join(f'`{t}`' for t in VALID_TRIGGERS)}"
                    )
                )
            )

        trigger_config: dict = {}
        if trigger_type == "message_contains":
            if not value.strip():
                return await ctx.send(
                    embed=red_embed(
                        description=f"{self.bot.no} Provide the text to match: `{ctx.prefix}workflow trigger message_contains <text>`"
                    )
                )
            trigger_config = {"text": value.strip(), "ignore_case": True}

        session["trigger_type"] = trigger_type
        session["trigger_config"] = trigger_config
        self._put_session(ctx.guild.id, ctx.author.id, session)

        label = VALID_TRIGGERS[trigger_type]
        if trigger_config.get("text"):
            label += f": `{trigger_config['text']}`"

        await ctx.send(
            embed=green_embed(
                description=(
                    f"{self.bot.yes} Trigger set: **{label}**\n"
                    f"Add actions: `{ctx.prefix}workflow action <type> [args]`\n"
                    f"Then `{ctx.prefix}workflow save` when done."
                )
            )
        )

    # ── action ───────────────────────────────────────────────────────────────

    @workflow.command(name="action")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def workflow_action(self, ctx: Context, action_type: str, *, args: str = ""):
        """Add an action to the active workflow session."""

        if not ctx.guild:
            return

        session = self._get_session(ctx.guild.id, ctx.author.id)
        if not session:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} No active session. Run `{ctx.prefix}workflow create <name>` first."
                )
            )

        if not session.get("trigger_type"):
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Set a trigger first: `{ctx.prefix}workflow trigger <type>`"
                )
            )

        action_type = action_type.lower()
        if action_type not in VALID_ACTIONS:
            return await ctx.send(
                embed=red_embed(
                    description=(
                        f"{self.bot.no} Unknown action `{action_type}`.\n"
                        f"Available: {', '.join(f'`{a}`' for a in VALID_ACTIONS)}"
                    )
                )
            )

        trigger = session["trigger_type"]

        if action_type in MESSAGE_ONLY_ACTIONS and trigger not in MESSAGE_TRIGGERS:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} `{action_type}` requires a message-based trigger (`message_contains` or `discord_invite`)."
                )
            )

        if action_type in MEMBER_LEAVE_BLOCKED and trigger == "member_leave":
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} `{action_type}` cannot be used with `member_leave` — the member has already left."
                )
            )

        config, error = await self._parse_args(ctx, action_type, args)
        if error:
            return await ctx.send(embed=red_embed(description=f"{self.bot.no} {error}"))

        session["actions"].append({"type": action_type, "config": config})
        self._put_session(ctx.guild.id, ctx.author.id, session)

        n = len(session["actions"])
        await ctx.send(
            embed=green_embed(
                description=(
                    f"{self.bot.yes} Action **{action_type}** added ({n} total).\n"
                    f"Add more or run `{ctx.prefix}workflow save` to finish."
                )
            )
        )

    async def _parse_args(
        self, ctx: Context, action_type: str, args: str
    ) -> tuple[dict, str | None]:
        args = args.strip()

        if action_type == "send_message":
            parts = args.split(" ", 1)
            if len(parts) < 2 or not parts[1].strip():
                return {}, "Usage: `workflow action send_message #channel <message>`"
            ch = await _resolve_channel(ctx, parts[0])
            if not ch:
                return {}, f"Channel `{parts[0]}` not found."
            return {"channel_id": ch.id, "message": parts[1].strip()}, None

        if action_type in ("give_role", "remove_role"):
            if not args:
                return {}, f"Usage: `workflow action {action_type} @role`"
            role = await _resolve_role(ctx, args)
            if not role:
                return {}, f"Role `{args}` not found."
            return {"role_id": role.id}, None

        if action_type == "dm_user":
            if not args:
                return {}, "Usage: `workflow action dm_user <message>`"
            return {"message": args}, None

        if action_type == "delete_message":
            return {}, None

        if action_type == "warn":
            return {"reason": args or "Workflow automation"}, None

        if action_type == "timeout":
            if not args:
                return {}, "Usage: `workflow action timeout <minutes>`"
            try:
                minutes = int(args)
                if minutes <= 0:
                    raise ValueError
            except ValueError:
                return {}, "Duration must be a positive integer (minutes)."
            return {"duration": minutes * 60}, None

        if action_type in ("kick", "ban"):
            return {"reason": args or "Workflow automation"}, None

        if action_type == "log":
            parts = args.split(" ", 1)
            if not parts[0]:
                return {}, "Usage: `workflow action log #channel [message]`"
            ch = await _resolve_channel(ctx, parts[0])
            if not ch:
                return {}, f"Channel `{parts[0]}` not found."
            msg = parts[1].strip() if len(parts) > 1 else "Workflow action triggered."
            return {"channel_id": ch.id, "message": msg}, None

        return {}, f"Unknown action `{action_type}`."

    # ── save / cancel ─────────────────────────────────────────────────────────

    @workflow.command(name="save")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def workflow_save(self, ctx: Context):
        """Save the active workflow session to the database."""

        if not ctx.guild or not self.bot.db:
            return

        session = self._get_session(ctx.guild.id, ctx.author.id)
        if not session:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} No active session. Run `{ctx.prefix}workflow create <name>` first."
                )
            )

        if not session.get("trigger_type"):
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Set a trigger first: `{ctx.prefix}workflow trigger <type>`"
                )
            )

        if not session.get("actions"):
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Add at least one action: `{ctx.prefix}workflow action <type>`"
                )
            )

        row = await self.bot.db.fetchrow(
            "INSERT INTO workflows (guild_id, name, trigger_type, trigger_config, actions, created_by) "
            "VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
            ctx.guild.id,
            session["name"],
            session["trigger_type"],
            session["trigger_config"],
            session["actions"],
            ctx.author.id,
        )

        self._drop_session(ctx.guild.id, ctx.author.id)
        self._clear_workflow_cache(ctx.guild.id)

        await ctx.send(
            embed=green_embed(
                description=(
                    f"{self.bot.yes} Workflow **{session['name']}** saved! (ID: `{row['id']}`)\n"
                    f"Trigger: `{session['trigger_type']}` — {len(session['actions'])} action(s)"
                )
            )
        )

    @workflow.command(name="cancel")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def workflow_cancel(self, ctx: Context):
        """Discard the active workflow session."""

        if not ctx.guild:
            return

        session = self._get_session(ctx.guild.id, ctx.author.id)
        if not session:
            return await ctx.send(embed=orange_embed(description="No active session to cancel."))

        name = session["name"]
        self._drop_session(ctx.guild.id, ctx.author.id)
        await ctx.send(
            embed=green_embed(description=f"{self.bot.yes} Session for **{name}** discarded.")
        )

    # ── list / show ───────────────────────────────────────────────────────────

    @workflow.command(name="list")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def workflow_list(self, ctx: Context):
        """List all workflows for this server."""

        if not ctx.guild or not self.bot.db:
            return

        rows = await self.bot.db.fetch(
            "SELECT id, name, trigger_type, enabled, COALESCE(jsonb_array_length(actions), 0) AS action_count "
            "FROM workflows WHERE guild_id=$1 ORDER BY id",
            ctx.guild.id,
        )

        if not rows:
            return await ctx.send(
                embed=orange_embed(
                    description=f"No workflows found. Create one with `{ctx.prefix}workflow create <name>`."
                )
            )

        lines = [
            f"{'✅' if r['enabled'] else '❌'} `#{r['id']}` **{r['name']}** — "
            f"trigger: `{r['trigger_type']}`, {r['action_count']} action(s)"
            for r in rows
        ]
        em = await ctx_embed(ctx, title="⚙️  Workflows", description="\n".join(lines))
        await ctx.send(embed=em)

    @workflow.command(name="show")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def workflow_show(self, ctx: Context, workflow_id: int):
        """Show full details of a workflow."""

        if not ctx.guild or not self.bot.db:
            return

        row = await self.bot.db.fetchrow(
            "SELECT * FROM workflows WHERE id=$1 AND guild_id=$2",
            workflow_id,
            ctx.guild.id,
        )
        if not row:
            return await ctx.send(
                embed=red_embed(description=f"{self.bot.no} Workflow `#{workflow_id}` not found.")
            )

        status = "✅ Enabled" if row["enabled"] else "❌ Disabled"
        trigger_cfg = dict(row["trigger_config"]) if row["trigger_config"] else {}
        trigger_label = VALID_TRIGGERS.get(row["trigger_type"], row["trigger_type"])
        if trigger_cfg.get("text"):
            trigger_label += f": `{trigger_cfg['text']}`"

        actions = list(row["actions"]) if row["actions"] else []
        action_lines = [
            f"`{i}.` **{a['type']}** — {_action_summary(a['type'], a.get('config', {}))}"
            for i, a in enumerate(actions, 1)
        ]

        creator = ctx.guild.get_member(row["created_by"])
        creator_str = str(creator) if creator else f"<@{row['created_by']}>"

        em = await ctx_embed(ctx, title=f"⚙️  Workflow: {row['name']}")
        em.add_field(name="Status", value=status, inline=True)
        em.add_field(name="ID", value=f"`#{row['id']}`", inline=True)
        em.add_field(name="Trigger", value=trigger_label, inline=False)
        em.add_field(
            name=f"Actions ({len(actions)})",
            value="\n".join(action_lines) or "None",
            inline=False,
        )
        em.set_footer(text=f"Created by {creator_str}")
        await ctx.send(embed=em)

    # ── enable / disable / delete ─────────────────────────────────────────────

    @workflow.command(name="enable")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def workflow_enable(self, ctx: Context, workflow_id: int):
        """Enable a workflow."""

        if not ctx.guild or not self.bot.db:
            return

        row = await self.bot.db.fetchrow(
            "SELECT id, name FROM workflows WHERE id=$1 AND guild_id=$2",
            workflow_id,
            ctx.guild.id,
        )
        if not row:
            return await ctx.send(
                embed=red_embed(description=f"{self.bot.no} Workflow `#{workflow_id}` not found.")
            )

        await self.bot.db.execute("UPDATE workflows SET enabled=true WHERE id=$1", workflow_id)
        self._clear_workflow_cache(ctx.guild.id)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Workflow **{row['name']}** (`#{workflow_id}`) enabled."
            )
        )

    @workflow.command(name="disable")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def workflow_disable(self, ctx: Context, workflow_id: int):
        """Disable a workflow without deleting it."""

        if not ctx.guild or not self.bot.db:
            return

        row = await self.bot.db.fetchrow(
            "SELECT id, name FROM workflows WHERE id=$1 AND guild_id=$2",
            workflow_id,
            ctx.guild.id,
        )
        if not row:
            return await ctx.send(
                embed=red_embed(description=f"{self.bot.no} Workflow `#{workflow_id}` not found.")
            )

        await self.bot.db.execute("UPDATE workflows SET enabled=false WHERE id=$1", workflow_id)
        self._clear_workflow_cache(ctx.guild.id)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Workflow **{row['name']}** (`#{workflow_id}`) disabled."
            )
        )

    @workflow.command(name="delete")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def workflow_delete(self, ctx: Context, workflow_id: int):
        """Permanently delete a workflow."""

        if not ctx.guild or not self.bot.db:
            return

        row = await self.bot.db.fetchrow(
            "SELECT id, name FROM workflows WHERE id=$1 AND guild_id=$2",
            workflow_id,
            ctx.guild.id,
        )
        if not row:
            return await ctx.send(
                embed=red_embed(description=f"{self.bot.no} Workflow `#{workflow_id}` not found.")
            )

        await self.bot.db.execute("DELETE FROM workflows WHERE id=$1", workflow_id)
        self._clear_workflow_cache(ctx.guild.id)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Workflow **{row['name']}** (`#{workflow_id}`) deleted."
            )
        )


async def setup(bot: PizzaHat) -> None:
    await bot.add_cog(WorkflowCommands(bot))
