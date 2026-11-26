"""Discord action registry for workflows.

All handlers are deterministic, check Discord permissions and role hierarchy,
and avoid duplicate side effects where an identifier is available. No action
evaluates user-provided code; template variables are plain string substitution.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

import discord

from workflows.repository import WorkflowRepository
from workflows.triggers import WorkflowContext

logger = logging.getLogger("bot")

_TASK_NAMESPACE = uuid.UUID("5d4f0e7a-8c31-4d0b-9f2b-6a11e2d0c4ad")
_MAX_RENDER = 2000


@dataclass(frozen=True)
class ActionResult:
    index: int
    type: str
    status: str  # success | skipped | failed
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "type": self.type,
            "status": self.status,
            "detail": self.detail[:200],
        }


def render(text: str, variables: dict[str, str]) -> str:
    """Replace ``{name}`` placeholders without evaluating anything."""

    out = str(text or "")
    for key, value in variables.items():
        out = out.replace("{" + key + "}", str(value))
    return out[:_MAX_RENDER]


def build_variables(ctx: WorkflowContext, config: dict[str, Any] | None = None) -> dict[str, str]:
    """Build the small, fixed set of template variables available to actions."""

    config = config or {}
    variables: dict[str, str] = {
        "guild": ctx.guild.name,
        "guild.id": str(ctx.guild.id),
        "timezone": str(config.get("timezone") or ctx.timezone or "UTC"),
        "trigger": ctx.trigger_type,
    }
    user = ctx.user
    if user is not None:
        variables.update(
            {
                "user": str(user),
                "user.mention": user.mention,
                "user.name": getattr(user, "name", str(user)),
                "user.id": str(user.id),
            }
        )
    if ctx.channel is not None:
        variables["channel"] = getattr(ctx.channel, "mention", str(ctx.channel))
        variables["channel.id"] = str(getattr(ctx.channel, "id", ""))
    if ctx.message is not None:
        variables["content"] = str(ctx.message.content or "")[:_MAX_RENDER]
        variables["message_url"] = ctx.message.jump_url
    if ctx.emoji is not None:
        variables["emoji"] = str(ctx.emoji)
    variables["emoji_count"] = str(ctx.reaction_count)
    for source in (ctx.alert, ctx.event):
        if source:
            for key in ("source", "module", "action_type", "reason", "thread_id"):
                if key in source:
                    variables[key] = str(source[key])[:200]
    variables.update({key: str(value) for key, value in ctx.extra.items() if isinstance(key, str)})
    return variables


class ActionRegistry:
    """Executes validated workflow actions against Discord and owned services."""

    def __init__(self, bot: Any, repository: WorkflowRepository | None = None) -> None:
        self.bot = bot
        self.repo = repository or WorkflowRepository(getattr(bot, "db", None))

    def _me(self, ctx: WorkflowContext) -> discord.Member | None:
        me = ctx.guild.me
        if me is None and getattr(self.bot, "user", None) is not None:
            me = ctx.guild.get_member(self.bot.user.id)
        return me

    def _channel(
        self, ctx: WorkflowContext, action: dict[str, Any], *, embed_links: bool = False
    ) -> discord.abc.Messageable | None:
        channel_id = action.get("channel_id")
        channel: Any = None
        if channel_id:
            channel = ctx.guild.get_channel(channel_id) or ctx.guild.get_thread(channel_id)
        else:
            channel = ctx.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return None
        me = self._me(ctx)
        if me is None:
            return None
        permissions = channel.permissions_for(me)
        if not permissions.send_messages or (embed_links and not permissions.embed_links):
            return None
        return channel

    async def execute(
        self,
        action: dict[str, Any],
        ctx: WorkflowContext,
        variables: dict[str, str],
        *,
        workflow: dict[str, Any] | None = None,
        index: int = 0,
    ) -> ActionResult:
        kind = str(action.get("type", ""))
        handler = getattr(self, f"_action_{kind}", None)
        if handler is None or kind.startswith("_"):
            return ActionResult(index, kind, "skipped", "unknown action")
        try:
            result = handler(action, ctx, variables, workflow or {}, index)
            if hasattr(result, "__await__"):
                result = await result
            return result if isinstance(result, ActionResult) else ActionResult(index, kind, "success")
        except discord.HTTPException as exc:
            # Rate limits are retried by the engine with the server's delay.
            if exc.status == 429:
                raise
            logger.warning("Workflow action %s failed: %s", kind, exc)
            return ActionResult(index, kind, "failed", f"{type(exc).__name__}: {exc}")
        except (discord.Forbidden, discord.NotFound) as exc:
            logger.warning("Workflow action %s failed: %s", kind, exc)
            return ActionResult(index, kind, "failed", f"{type(exc).__name__}: {exc}")
        except Exception as exc:
            logger.warning("Workflow action %s failed: %s", kind, exc, exc_info=True)
            return ActionResult(index, kind, "failed", f"{type(exc).__name__}: {exc}")

    # ── role and member actions ──────────────────────────────────────────────

    def _role_target(
        self, ctx: WorkflowContext, role_id: int
    ) -> tuple[discord.Member | None, discord.Role | None, discord.Member | None]:
        member = ctx.member if isinstance(ctx.member, discord.Member) else None
        role = ctx.guild.get_role(role_id)
        me = self._me(ctx)
        if member is None or role is None or me is None:
            return None, None, None
        if member == me or role.is_default() or role.managed:
            return None, None, None
        if not me.guild_permissions.manage_roles:
            return None, None, None
        if me.top_role is None or role >= me.top_role:
            return None, None, None
        if member.top_role >= me.top_role:
            return None, None, None
        return member, role, me

    async def _action_add_role(
        self,
        action: dict[str, Any],
        ctx: WorkflowContext,
        variables: dict[str, str],
        workflow: dict[str, Any],
        index: int,
    ) -> ActionResult:
        kind = action["type"]
        member, role, _ = self._role_target(ctx, int(action["role_id"]))
        if member is None or role is None:
            return ActionResult(index, kind, "skipped", "permission or hierarchy")
        has_role = any(item.id == role.id for item in member.roles)
        if kind == "add_role" and has_role:
            return ActionResult(index, kind, "skipped", "already applied")
        if kind == "remove_role" and not has_role:
            return ActionResult(index, kind, "skipped", "not applied")
        if kind == "add_role":
            await member.add_roles(role, reason=f"Workflow: {ctx.trigger_type}")
        else:
            await member.remove_roles(role, reason=f"Workflow: {ctx.trigger_type}")
        return ActionResult(index, kind, "success", role.name)

    # Both role actions share the same hierarchy/idempotency guard.
    _action_remove_role = _action_add_role

    async def _action_timeout_member(
        self,
        action: dict[str, Any],
        ctx: WorkflowContext,
        variables: dict[str, str],
        workflow: dict[str, Any],
        index: int,
    ) -> ActionResult:
        member = ctx.member if isinstance(ctx.member, discord.Member) else None
        me = self._me(ctx)
        if member is None or me is None or member == me:
            return ActionResult(index, "timeout_member", "skipped", "no target")
        if not me.guild_permissions.moderate_members:
            return ActionResult(index, "timeout_member", "skipped", "missing permission")
        if member.top_role >= me.top_role:
            return ActionResult(index, "timeout_member", "skipped", "hierarchy")
        until = discord.utils.utcnow() + datetime.timedelta(minutes=int(action["minutes"]))
        is_timed_out = getattr(member, "is_timed_out", None)
        if callable(is_timed_out) and is_timed_out():
            current = getattr(member, "timed_out_until", None)
            if current is not None and current >= until:
                return ActionResult(index, "timeout_member", "skipped", "already timed out")
        await member.timeout(until, reason=f"Workflow: {ctx.trigger_type}")
        return ActionResult(index, "timeout_member", "success", until.isoformat())

    async def _action_send_dm(
        self,
        action: dict[str, Any],
        ctx: WorkflowContext,
        variables: dict[str, str],
        workflow: dict[str, Any],
        index: int,
    ) -> ActionResult:
        user = ctx.user
        if not isinstance(user, (discord.Member, discord.User)):
            return ActionResult(index, "send_dm", "skipped", "no user")
        await user.send(render(action["message"], variables))
        return ActionResult(index, "send_dm", "success", str(user.id))

    # ── message actions ──────────────────────────────────────────────────────

    async def _action_send_message(
        self,
        action: dict[str, Any],
        ctx: WorkflowContext,
        variables: dict[str, str],
        workflow: dict[str, Any],
        index: int,
    ) -> ActionResult:
        channel = self._channel(ctx, action)
        if channel is None:
            return ActionResult(index, "send_message", "skipped", "no channel")
        await channel.send(render(action["message"], variables))
        return ActionResult(index, "send_message", "success", str(channel.id))

    def _build_embed(
        self, action: dict[str, Any], ctx: WorkflowContext, variables: dict[str, str]
    ) -> discord.Embed:
        if action.get("from_message") and ctx.message is not None:
            source = ctx.message
            title = action.get("title") or f"Message by {source.author}"
            description = action.get("description") or (source.content or "")
            em = discord.Embed(
                title=render(title, variables)[:256],
                description=render(description, variables)[:4096],
                color=int(action.get("color", 0x456DD4)),
                timestamp=source.created_at,
            )
            em.set_author(name=str(source.author), icon_url=source.author.display_avatar.url)
            em.add_field(name="Source", value=f"[Jump to message]({source.jump_url})")
            if source.attachments:
                em.set_image(url=source.attachments[0].url)
            em.set_footer(text=f"ID: {source.id}")
            return em
        em = discord.Embed(
            title=render(action.get("title", ""), variables)[:256] or None,
            description=render(action.get("description", ""), variables)[:4096] or None,
            color=int(action.get("color", 0x456DD4)),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        return em

    async def _action_send_embed(
        self,
        action: dict[str, Any],
        ctx: WorkflowContext,
        variables: dict[str, str],
        workflow: dict[str, Any],
        index: int,
    ) -> ActionResult:
        channel = self._channel(ctx, action, embed_links=True)
        if channel is None:
            return ActionResult(index, "send_embed", "skipped", "no channel")
        em = self._build_embed(action, ctx, variables)
        content = render(action.get("content", ""), variables) or None
        if action.get("dedupe") and ctx.message is not None:
            bot_msg_id = await self.repo.get_dedupe(ctx.guild.id, ctx.message.id)
            if bot_msg_id:
                try:
                    existing = await channel.fetch_message(bot_msg_id)
                    await existing.edit(content=content, embed=em)
                    return ActionResult(index, "send_embed", "success", f"updated {bot_msg_id}")
                except discord.NotFound:
                    pass
        sent = await channel.send(content=content, embed=em)
        if action.get("dedupe") and ctx.message is not None:
            await self.repo.set_dedupe(ctx.guild.id, ctx.message.id, sent.id)
        return ActionResult(index, "send_embed", "success", str(sent.id))

    async def _action_log_channel(
        self,
        action: dict[str, Any],
        ctx: WorkflowContext,
        variables: dict[str, str],
        workflow: dict[str, Any],
        index: int,
    ) -> ActionResult:
        channel = action.get("channel_id")
        target: Any = None
        if channel:
            target = ctx.guild.get_channel(int(channel))
        elif self.repo.pool is not None:
            channel_id = await self.repo.pool.fetchval(
                "SELECT log_channel_id FROM guild_config WHERE guild_id=$1", ctx.guild.id
            )
            if channel_id:
                target = ctx.guild.get_channel(int(channel_id))
        if not isinstance(target, discord.TextChannel):
            return ActionResult(index, "log_channel", "skipped", "no log channel")
        me = self._me(ctx)
        if me is None:
            return ActionResult(index, "log_channel", "skipped", "no bot member")
        permissions = target.permissions_for(me)
        if not permissions.send_messages:
            return ActionResult(index, "log_channel", "skipped", "missing permission")
        em = discord.Embed(
            description=render(action["message"], variables)[:4096],
            color=0x456DD4,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        send_log = getattr(self.bot, "send_log", None)
        if callable(send_log):
            await send_log(target, embed=em)
        else:
            await target.send(embed=em)
        return ActionResult(index, "log_channel", "success", str(target.id))

    async def _action_open_ticket(
        self,
        action: dict[str, Any],
        ctx: WorkflowContext,
        variables: dict[str, str],
        workflow: dict[str, Any],
        index: int,
    ) -> ActionResult:
        channel = self._channel(ctx, action)
        member = ctx.member if isinstance(ctx.member, discord.Member) else None
        me = self._me(ctx)
        if not isinstance(channel, discord.TextChannel) or member is None or me is None:
            return ActionResult(index, "open_ticket", "skipped", "no channel or member")
        permissions = channel.permissions_for(me)
        if not (me.guild_permissions.manage_threads or permissions.create_private_threads):
            return ActionResult(index, "open_ticket", "skipped", "missing thread permission")

        if self.repo.pool is not None:
            existing = await self.repo.pool.fetchval(
                "SELECT thread_id FROM tickets "
                "WHERE guild_id=$1 AND creator_id=$2 AND status='open'",
                ctx.guild.id,
                member.id,
            )
            if existing:
                thread = ctx.guild.get_thread(int(existing))
                if thread is not None:
                    return ActionResult(index, "open_ticket", "skipped", f"existing {thread.id}")

        thread = await channel.create_thread(
            name=f"ticket-{member.display_name}"[:90],
            reason=f"Workflow ticket: {ctx.trigger_type}",
            invitable=False,
        )
        await thread.add_user(member)
        if self.repo.pool is not None:
            await self.repo.pool.execute(
                "INSERT INTO tickets (guild_id, thread_id, creator_id, subject) "
                "VALUES ($1, $2, $3, $4) ON CONFLICT (thread_id) DO NOTHING",
                ctx.guild.id,
                thread.id,
                member.id,
                render(action.get("panel_name", "Support"), variables)[:200],
            )
        content = member.mention
        support_role_id = action.get("support_role_id")
        if support_role_id:
            role = ctx.guild.get_role(int(support_role_id))
            if role is not None:
                content += f" {role.mention}"
        em = discord.Embed(
            title=render(action.get("panel_name", "Support"), variables)[:256],
            description=(
                f"Welcome, {member.mention}! A workflow opened this ticket. "
                "Please describe your issue."
            ),
            color=0x57F287,
        )
        from utils.ui import TicketSettings  # local import keeps startup light

        await thread.send(content=content, embed=em, view=TicketSettings(thread.id, self.bot))
        return ActionResult(index, "open_ticket", "success", str(thread.id))

    # ── service-backed actions ───────────────────────────────────────────────

    async def _action_create_moderation_case(
        self,
        action: dict[str, Any],
        ctx: WorkflowContext,
        variables: dict[str, str],
        workflow: dict[str, Any],
        index: int,
    ) -> ActionResult:
        kind = "create_moderation_case"
        if self.repo.pool is None:
            return ActionResult(index, kind, "skipped", "database unavailable")
        target_id = ctx.user_id
        if target_id is None:
            return ActionResult(index, kind, "skipped", "no subject")
        action_type = str(action["action_type"])
        me = self._me(ctx)
        needed = {
            "timeout": "moderate_members",
            "kick": "kick_members",
            "ban": "ban_members",
            "unban": "ban_members",
            "autoban": "ban_members",
            "automod": "moderate_members",
            "antialt": "moderate_members",
        }.get(action_type)
        if needed and (me is None or not getattr(me.guild_permissions, needed, False)):
            return ActionResult(index, kind, "skipped", "missing permission")
        moderator_id = int(action.get("moderator_user_id") or getattr(self.bot.user, "id", 0))
        reason = render(action.get("reason", "Workflow action"), variables)
        digest_source = (
            f"{workflow.get('id', 0)}:{ctx.trigger_type}:{target_id}:{action_type}:"
            f"{ctx.event_key or ctx.extra.get('event_digest', '')}"
        )
        idempotency_key = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:32]
        case_id = await self.repo.pool.fetchval(
            "INSERT INTO moderation_cases "
            "(case_id, guild_id, subject_user_id, moderator_user_id, action_type, "
            "source, reason, duration_seconds, status, metadata, idempotency_key) "
            "VALUES ($1::uuid, $2, $3, $4, $5, 'workflow', $6, $7, 'active', "
            "$8::jsonb, $9) ON CONFLICT (idempotency_key) DO NOTHING RETURNING case_id",
            str(uuid.uuid4()),
            ctx.guild.id,
            target_id,
            moderator_id,
            action_type,
            reason[:2000],
            action.get("duration_seconds"),
            json.dumps(
                {
                    "workflow_id": workflow.get("id"),
                    "trigger_type": ctx.trigger_type,
                    "event_key": ctx.event_key,
                }
            ),
            idempotency_key,
        )
        if case_id is None:
            return ActionResult(index, kind, "skipped", "duplicate case")
        return ActionResult(index, kind, "success", str(case_id))

    async def _action_set_scheduled_task(
        self,
        action: dict[str, Any],
        ctx: WorkflowContext,
        variables: dict[str, str],
        workflow: dict[str, Any],
        index: int,
    ) -> ActionResult:
        kind = "set_scheduled_task"
        if self.repo.pool is None:
            return ActionResult(index, kind, "skipped", "database unavailable")
        task_kind = str(action["kind"])
        if "run_at" in action:
            run_at = datetime.datetime.fromisoformat(
                str(action["run_at"]).replace("Z", "+00:00")
            )
            if run_at.tzinfo is None:
                run_at = run_at.replace(tzinfo=datetime.timezone.utc)
        else:
            run_at = discord.utils.utcnow() + datetime.timedelta(
                seconds=int(action["delay_seconds"])
            )
        payload = dict(action.get("payload") or {})
        payload.update(
            {
                "workflow_id": workflow.get("id"),
                "definition_id": workflow.get("definition_id"),
                "trigger_type": ctx.trigger_type,
                "event_key": ctx.event_key,
            }
        )
        task_id = str(
            uuid.uuid5(
                _TASK_NAMESPACE,
                f"{ctx.guild.id}:{workflow.get('id', 0)}:{ctx.event_key or ''}:{index}",
            )
        )
        created = await self.repo.create_task(
            ctx.guild.id, task_kind, payload, run_at, task_id=task_id
        )
        if created is None:
            return ActionResult(index, kind, "skipped", "duplicate task")
        if task_kind == "workflow_schedule" and workflow.get("id") is not None:
            slot = str(payload.get("slot") or task_id)
            await self.repo.set_state(
                int(workflow["id"]),
                ctx.guild.id,
                "schedule",
                run_at,
                {"kind": "schedule", "slot": slot},
            )
        return ActionResult(index, kind, "success", created)
