"""Typed trigger definitions and Discord event adapters.

The registry translates Discord events into a small, deterministic
:class:`WorkflowContext`. Trigger configs are validated by
:mod:`workflows.schema`; this module only filters already validated payloads.
Custom events are supported, but must be registered in code with an explicit
validator -- no code strings are ever interpreted.
"""

from __future__ import annotations

import datetime
import hashlib
import inspect
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import discord

from workflows import schema

logger = logging.getLogger("bot")

_MAX_TEXT_INPUT = 4000
_MAX_KEY_LENGTH = 300


@dataclass
class WorkflowContext:
    """Normalized event data shared by conditions, actions and the engine."""

    guild: discord.Guild
    trigger_type: str
    member: discord.Member | discord.User | None = None
    message: discord.Message | None = None
    channel: discord.abc.Messageable | None = None
    payload: Any = None
    alert: dict[str, Any] | None = None
    event: dict[str, Any] | None = None
    emoji: str | None = None
    reaction_count: int = 0
    role_event: str | None = None
    timezone: str = "UTC"
    extra: dict[str, Any] = field(default_factory=dict)
    # Engine-controlled recursion guards (not part of any persisted payload).
    depth: int = 0
    seen_workflows: set[int] = field(default_factory=set)
    event_key: str | None = None

    @property
    def user(self) -> discord.Member | discord.User | None:
        return self.member or (self.message.author if self.message else None)

    @property
    def user_id(self) -> int | None:
        user = self.user
        if user is not None:
            return int(getattr(user, "id", 0)) or None
        for key in ("user_id", "subject_user_id", "creator_id", "target_id"):
            raw = (self.event or {}).get(key, self.extra.get(key))
            if raw:
                try:
                    return int(raw)
                except (TypeError, ValueError):
                    continue
        return None

    def content(self) -> str:
        if self.message is not None:
            return str(self.message.content or "")
        for source in (self.alert, self.event):
            if source:
                text = source.get("content") or source.get("message")
                if text:
                    return str(text)[:_MAX_TEXT_INPUT]
        return ""


@dataclass(frozen=True)
class TriggerDefinition:
    """A named trigger with optional custom validation/filtering hooks."""

    name: str
    description: str
    builtin: bool = True
    context_builder: Callable[..., Any] | None = None
    event_filter: Callable[[dict[str, Any], WorkflowContext], bool] | None = None


@lru_cache(maxsize=256)
def _compiled_pattern(pattern: str) -> re.Pattern[str] | None:
    if len(pattern) > schema._MAX_PATTERN:  # noqa: SLF001 - schema owns the cap
        return None
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return None


def _matches_text(text: str, expected: str, match: str) -> bool:
    text = text[:_MAX_TEXT_INPUT]
    if match == "exact":
        return text.lower() == expected.lower()
    if match == "starts_with":
        return text.lower().startswith(expected.lower())
    if match == "regex":
        compiled = _compiled_pattern(expected)
        return bool(compiled and compiled.search(text))
    return expected.lower() in text.lower()


def _stable_digest(payload: Any) -> str:
    try:
        raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        raw = str(payload)
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:24]


def _empty_custom_config(value: Any, _name: str) -> dict[str, Any]:
    """Safe default validator: custom events take no configuration."""

    data = schema.parse_jsonb(value) if isinstance(value, (str, bytes, bytearray)) else value
    if not isinstance(data, dict) or data:
        raise schema.WorkflowValidationError(
            "This custom trigger accepts an empty trigger_config.",
            field="trigger_config",
        )
    return {}


class TriggerRegistry:
    """Registry of built-in and explicitly registered custom triggers."""

    def __init__(self) -> None:
        self._definitions: dict[str, TriggerDefinition] = {}
        for name in schema.TRIGGER_TYPES:
            self._definitions[name] = TriggerDefinition(
                name, name.replace("_", " ").title()
            )

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._definitions)

    def get(self, name: str) -> TriggerDefinition | None:
        return self._definitions.get(name)

    def register_custom(
        self,
        name: str,
        *,
        description: str = "",
        config_validator: Callable[[Any, str], dict[str, Any]] | None = None,
        context_builder: Callable[..., Any] | None = None,
        event_filter: Callable[[dict[str, Any], WorkflowContext], bool] | None = None,
    ) -> TriggerDefinition:
        """Register a custom event. Only explicit callables are accepted."""

        if not schema.is_custom_trigger_name(name) or name in self._definitions:
            raise schema.WorkflowValidationError(
                f"`{name}` is not a valid custom trigger name.", field="trigger_type"
            )
        validator = config_validator or _empty_custom_config
        schema.register_custom_trigger(name, validator)
        definition = TriggerDefinition(
            name=name,
            description=description or name.replace("_", " ").title(),
            builtin=False,
            context_builder=context_builder,
            event_filter=event_filter,
        )
        self._definitions[name] = definition
        return definition

    def unregister_custom(self, name: str) -> None:
        definition = self._definitions.get(name)
        if definition is not None and not definition.builtin:
            self._definitions.pop(name, None)
            schema.unregister_custom_trigger(name)

    async def build_custom_context(
        self, name: str, guild: discord.Guild, payload: Any = None, *, bot: Any = None
    ) -> WorkflowContext | None:
        """Build a context for a registered custom event."""

        definition = self.get(name)
        if definition is None or definition.builtin:
            return None
        builder = definition.context_builder
        if builder is None:
            return self.from_event(
                guild,
                name,
                payload if isinstance(payload, dict) else {"value": payload},
            )
        try:
            result = builder(guild, payload, bot)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:  # custom adapters must not break event loops
            logger.warning("Custom workflow trigger %s failed to build context: %s", name, exc)
            return None
        if isinstance(result, WorkflowContext):
            result.trigger_type = name
            return result
        if isinstance(result, dict):
            return self.from_event(guild, name, result)
        return None

    # ── context adapters ─────────────────────────────────────────────────────

    @staticmethod
    def from_message(message: discord.Message, trigger: str = "message_create") -> WorkflowContext:
        return WorkflowContext(
            guild=message.guild,  # type: ignore[arg-type]
            trigger_type=trigger,
            member=message.author if isinstance(message.author, discord.Member) else message.author,
            message=message,
            channel=message.channel,
            extra={"message_id": str(message.id)},
        )

    @staticmethod
    def from_member(member: discord.Member, trigger: str) -> WorkflowContext:
        return WorkflowContext(
            guild=member.guild,
            trigger_type=trigger,
            member=member,
            channel=member.guild.system_channel,
            extra={"member_id": str(member.id)},
        )

    @staticmethod
    def from_reaction(
        guild: discord.Guild,
        payload: discord.RawReactionActionEvent,
        *,
        message: discord.Message | None = None,
        channel: discord.abc.Messageable | None = None,
        count: int = 1,
    ) -> WorkflowContext:
        return WorkflowContext(
            guild=guild,
            trigger_type="reaction_add",
            member=payload.member,
            message=message,
            channel=channel,
            payload=payload,
            emoji=str(payload.emoji),
            reaction_count=count,
            extra={
                "message_id": str(payload.message_id),
                "channel_id": str(payload.channel_id),
                "user_id": str(payload.user_id),
            },
        )

    @staticmethod
    def from_role_update(
        member: discord.Member, role_id: int, event: str
    ) -> WorkflowContext:
        return WorkflowContext(
            guild=member.guild,
            trigger_type="role_update",
            member=member,
            channel=member.guild.system_channel,
            role_event=event,
            extra={"role_id": str(role_id)},
        )

    @staticmethod
    def from_event(
        guild: discord.Guild, trigger: str, event: dict[str, Any]
    ) -> WorkflowContext:
        data = dict(event)
        member_id = data.get("user_id") or data.get("subject_user_id") or data.get("creator_id")
        member = guild.get_member(int(member_id)) if member_id else None
        channel = None
        channel_id = data.get("channel_id")
        if channel_id:
            try:
                channel = guild.get_channel(int(channel_id))
            except (TypeError, ValueError):
                channel = None
        source = str(data.get("source", ""))
        module = str(data.get("module", ""))
        return WorkflowContext(
            guild=guild,
            trigger_type=trigger,
            member=member,
            channel=channel or guild.system_channel,
            alert=data if trigger == "safety_alert" else None,
            event=data,
            timezone=str(data.get("timezone", "UTC")),
            extra={"event_digest": _stable_digest(data)},
        )

    @staticmethod
    def from_schedule(
        guild: discord.Guild, *, slot: str, timezone: str = "UTC"
    ) -> WorkflowContext:
        return WorkflowContext(
            guild=guild,
            trigger_type="schedule",
            channel=guild.system_channel,
            timezone=timezone,
            extra={"slot": slot},
        )

    # ── filtering and event keys ─────────────────────────────────────────────

    def matches(self, workflow: dict[str, Any], ctx: WorkflowContext) -> bool:
        """Return whether a validated workflow should run for this context."""

        if workflow.get("trigger_type") != ctx.trigger_type:
            return False
        config = workflow.get("trigger_config") or {}
        trigger = ctx.trigger_type

        if trigger in ("message_create", "message_delete", "ticket_created"):
            if config.get("ignore_bots", True) and ctx.user is not None and getattr(ctx.user, "bot", False):
                return False
            channel_ids = config.get("channel_ids") or []
            channel_id = getattr(ctx.channel, "id", None)
            if channel_ids and channel_id not in channel_ids:
                return False
            if trigger == "message_create" and "contains_text" in config:
                return _matches_text(
                    ctx.content(),
                    config["contains_text"],
                    config.get("match", "contains"),
                )
            return True

        if trigger == "reaction_add":
            channel_ids = config.get("channel_ids") or []
            if channel_ids and getattr(ctx.channel, "id", None) not in channel_ids:
                return False
            if ctx.emoji != config.get("emoji"):
                return False
            return ctx.reaction_count >= int(config.get("min_reactions", 1))

        if trigger == "role_update":
            role_id = ctx.extra.get("role_id")
            try:
                role_id = int(role_id) if role_id is not None else None
            except (TypeError, ValueError):
                return False
            return ctx.role_event == config.get("event") and role_id == config.get("role_id")

        if trigger == "safety_alert":
            source = str((ctx.alert or ctx.event or {}).get("source", ""))
            return config.get("source", "any") in ("any", source)

        if trigger == "moderation_event":
            event = ctx.event or {}
            actions = config.get("actions") or []
            sources = config.get("sources") or []
            action = str(event.get("action_type") or event.get("action") or "")
            source = str(event.get("source", ""))
            if actions and action not in actions:
                return False
            if sources and source not in sources:
                return False
            return True

        definition = self.get(trigger)
        if definition is not None and definition.event_filter is not None:
            try:
                return bool(definition.event_filter(config, ctx))
            except Exception as exc:
                logger.warning("Custom workflow filter %s failed: %s", trigger, exc)
                return False
        return True

    def event_key(self, ctx: WorkflowContext) -> str:
        """Build a deterministic, bounded idempotency key for one event."""

        parts: list[str] = [str(ctx.guild.id), ctx.trigger_type]
        trigger = ctx.trigger_type
        if ctx.event_key:
            parts.append(ctx.event_key)
        elif ctx.message is not None:
            parts.extend(["message", str(ctx.message.id)])
        elif trigger == "reaction_add" and ctx.payload is not None:
            parts.extend(
                [
                    "reaction",
                    str(getattr(ctx.payload, "message_id", 0)),
                    str(getattr(ctx.payload, "user_id", 0)),
                    str(ctx.emoji or ""),
                ]
            )
        elif trigger in ("member_join", "member_leave"):
            parts.extend(["member", str(ctx.user_id or 0)])
        elif trigger == "role_update":
            parts.extend(
                ["role", str(ctx.user_id or 0), str(ctx.extra.get("role_id", "")), str(ctx.role_event)]
            )
        elif trigger == "schedule":
            parts.extend(["slot", str(ctx.extra.get("slot", ""))])
        else:
            data = dict(ctx.event or ctx.alert or ctx.extra)
            for key in ("id", "case_id", "thread_id", "event_id", "idempotency_key"):
                if data.get(key):
                    parts.extend([key, str(data[key])])
                    break
            else:
                parts.append(_stable_digest(data))
        key = ":".join(parts)
        if len(key) > _MAX_KEY_LENGTH:
            key = key[:_MAX_KEY_LENGTH - 24] + ":" + _stable_digest(key)
        return key


TRIGGERS = TriggerRegistry()


def utcnow() -> datetime.datetime:
    """Small helper used by schedule-aware adapters."""

    return datetime.datetime.now(datetime.timezone.utc)
