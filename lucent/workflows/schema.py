"""Portable, versioned workflow definitions and strict validation.

A definition is plain JSON so it can be shipped in an export file, validated by
commands, persisted as JSONB and validated again when loaded from the database.
Validation is deliberately strict: unknown fields, oversized strings and
invalid identifiers are rejected instead of being silently normalised away.

The module has no Discord imports; tier limits are resolved through
:class:`core.entitlements.EntitlementService` or an explicit tier argument.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.entitlements import EntitlementService, Tier

logger = logging.getLogger("bot")

#: Definitions produced by this package. Older (version 1) definitions remain
#: readable so a database written by the previous engine can still be loaded.
CURRENT_SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = (1, 2)

TRIGGER_TYPES = (
    "member_join",
    "member_leave",
    "message_create",
    "message_delete",
    "reaction_add",
    "role_update",
    "schedule",
    "safety_alert",
    "moderation_event",
    "ticket_created",
)

CONDITION_TYPES = (
    "account_age_lt",
    "contains_link",
    "contains_text",
    "has_role",
    "channel_in",
    "cooldown_sec",
    "is_bot",
    "emoji_is",
    "reaction_count_gte",
    "not_self_react",
    "safety_source",
    "safety_module",
    "moderation_action",
)

ACTION_TYPES = (
    "add_role",
    "remove_role",
    "send_embed",
    "send_message",
    "send_dm",
    "timeout_member",
    "open_ticket",
    "log_channel",
    "create_moderation_case",
    "set_scheduled_task",
)

MESSAGE_CONTENT_TRIGGERS = frozenset({"message_create"})
MESSAGE_CONTENT_TRIGGER_KEYS = frozenset({"contains_text", "match", "regex"})
MESSAGE_CONTENT_CONDITIONS = frozenset({"contains_link", "contains_text"})

MATCH_MODES = ("contains", "exact", "starts_with", "regex")
SCHEDULE_FREQUENCIES = ("interval", "daily")
SAFETY_SOURCES = ("antialt", "automod", "any")
ROLE_EVENTS = ("added", "removed")
COOLDOWN_SCOPES = ("user", "guild", "workflow")
MODERATION_ACTIONS = (
    "warn",
    "timeout",
    "kick",
    "ban",
    "unban",
    "autoban",
    "automod",
    "antialt",
)
SCHEDULED_TASK_KINDS = (
    "unban",
    "restore_verification",
    "workflow_schedule",
    "workflow_cooldown",
)

_MAX_SHORT = 100
_MAX_TEXT = 2000
_MAX_PATTERN = 200
_MAX_DESCRIPTION = 4096
_MAX_ACTIONS = 20
_MAX_CONDITIONS = 20
_MAX_PAYLOAD_ENTRIES = 20

_CUSTOM_NAME = re.compile(r"^[a-z][a-z0-9_]{1,49}$")


class WorkflowValidationError(ValueError):
    """Raised when a workflow payload violates the schema or tier limits."""

    def __init__(self, message: str, *, field: str | None = None):
        self.field = field
        super().__init__(message)


_CUSTOM_TRIGGERS: dict[str, Callable[[Any, str], dict[str, Any]]] = {}


def is_custom_trigger_name(name: str) -> bool:
    """Return whether ``name`` is a safe, programmatically registered event."""

    return bool(isinstance(name, str) and _CUSTOM_NAME.fullmatch(name))


def register_custom_trigger(
    name: str, validator: Callable[[Any, str], dict[str, Any]]
) -> None:
    """Register a custom trigger validator (no code strings are accepted)."""

    if not is_custom_trigger_name(name):
        raise WorkflowValidationError(
            "Custom trigger names must be 2-50 lowercase letters, digits or underscores "
            "and start with a letter.",
            field="trigger_type",
        )
    if not callable(validator):
        raise WorkflowValidationError(
            "A custom trigger validator must be callable.", field="trigger_type"
        )
    _CUSTOM_TRIGGERS[name] = validator


def unregister_custom_trigger(name: str) -> None:
    _CUSTOM_TRIGGERS.pop(name, None)


def parse_jsonb(value: Any) -> Any:
    """Decode a JSONB value returned by asyncpg (which emits raw text by default)."""

    if isinstance(value, (str, bytes, bytearray)):
        try:
            return json.loads(value)
        except (TypeError, ValueError) as exc:
            raise WorkflowValidationError(
                "Stored workflow JSON is malformed.", field="jsonb"
            ) from exc
    return value


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkflowValidationError(f"`{field}` must be a JSON object.", field=field)
    return value


def _keys(
    value: dict[str, Any],
    *,
    allowed: set[str],
    required: set[str],
    field: str,
) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise WorkflowValidationError(
            f"`{field}` has unknown field(s): {', '.join(sorted(unknown))}.",
            field=field,
        )
    missing = required - set(value)
    if missing:
        raise WorkflowValidationError(
            f"`{field}` is missing required field(s): {', '.join(sorted(missing))}.",
            field=field,
        )


def _string(
    value: Any,
    field: str,
    *,
    minimum: int = 1,
    maximum: int = _MAX_SHORT,
) -> str:
    if not isinstance(value, str):
        raise WorkflowValidationError(f"`{field}` must be a string.", field=field)
    if not minimum <= len(value) <= maximum:
        raise WorkflowValidationError(
            f"`{field}` must be {minimum}-{maximum} characters long.", field=field
        )
    return value


def _integer(
    value: Any,
    field: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkflowValidationError(f"`{field}` must be an integer.", field=field)
    if value < minimum or (maximum is not None and value > maximum):
        suffix = f" and <= {maximum}" if maximum is not None else ""
        raise WorkflowValidationError(
            f"`{field}` must be >= {minimum}{suffix}.", field=field
        )
    return value


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise WorkflowValidationError(f"`{field}` must be a boolean.", field=field)
    return value


def _snowflake(value: Any, field: str) -> int:
    return _integer(value, field, minimum=1)


def _id_list(value: Any, field: str) -> list[int]:
    if not isinstance(value, list) or len(value) > 100:
        raise WorkflowValidationError(
            f"`{field}` must be an array of at most 100 IDs.", field=field
        )
    return [_snowflake(item, f"{field}[{index}]") for index, item in enumerate(value)]


def _choice(value: Any, field: str, choices: tuple[str, ...]) -> str:
    text = _string(value, field, maximum=_MAX_SHORT)
    if text not in choices:
        raise WorkflowValidationError(
            f"`{field}` must be one of: {', '.join(choices)}.", field=field
        )
    return text


def _color(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise WorkflowValidationError(
            f"`{field}` must be an integer or #hex color.", field=field
        )
    if isinstance(value, int):
        return _integer(value, field, minimum=0, maximum=0xFFFFFF)
    if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return int(value[1:], 16)
    raise WorkflowValidationError(
        f"`{field}` must be a 24-bit integer or a #RRGGBB string.", field=field
    )


def _timezone(value: Any, field: str) -> str:
    name = _string(value, field)
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        raise WorkflowValidationError(
            f"`{field}` must be a valid IANA timezone name.", field=field
        ) from None
    return name


def _pattern(value: Any, field: str, *, maximum: int = _MAX_PATTERN) -> str:
    text = _string(value, field, maximum=maximum)
    try:
        re.compile(text)
    except re.error as exc:
        raise WorkflowValidationError(
            f"`{field}` is not a valid regular expression: {exc}", field=field
        ) from exc
    return text


def _emoji(value: Any, field: str) -> str:
    return _string(value, field, maximum=64)


def _timestamp(value: Any, field: str) -> str:
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    text = _string(value, field, maximum=64)
    try:
        datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise WorkflowValidationError(
            f"`{field}` must be an ISO-8601 timestamp.", field=field
        ) from None
    return text


def _uuid(value: Any, field: str) -> str:
    text = _string(value, field, maximum=64)
    try:
        return str(uuid.UUID(text))
    except ValueError:
        raise WorkflowValidationError(
            f"`{field}` must be a UUID.", field=field
        ) from None


def _payload(value: Any, field: str) -> dict[str, Any]:
    data = _object(value, field)
    if len(data) > _MAX_PAYLOAD_ENTRIES:
        raise WorkflowValidationError(
            f"`{field}` may contain at most {_MAX_PAYLOAD_ENTRIES} entries.",
            field=field,
        )
    out: dict[str, Any] = {}
    for key, item in data.items():
        key_field = f"{field}.{key}"
        _string(key, f"{field} key", maximum=40)
        if isinstance(item, bool) or isinstance(item, (str, int, float)):
            if isinstance(item, str):
                _string(item, key_field, minimum=0, maximum=_MAX_TEXT)
            out[key] = item
        elif isinstance(item, list):
            out[key] = [
                _string(entry, f"{key_field}[{index}]", maximum=_MAX_SHORT)
                for index, entry in enumerate(item[:20])
            ]
        else:
            raise WorkflowValidationError(
                f"`{key_field}` must be a string, number, boolean or string array.",
                field=key_field,
            )
    return out


def _validate_empty(config: dict[str, Any]) -> dict[str, Any]:
    _keys(config, allowed=set(), required=set(), field="trigger_config")
    return {}


def _validate_channel_filter(config: dict[str, Any]) -> dict[str, Any]:
    _keys(
        config,
        allowed={"channel_ids", "ignore_bots"},
        required=set(),
        field="trigger_config",
    )
    return {
        "channel_ids": _id_list(config["channel_ids"], "trigger_config.channel_ids")
        if "channel_ids" in config
        else [],
        "ignore_bots": _boolean(
            config.get("ignore_bots", True), "trigger_config.ignore_bots"
        ),
    }


def _validate_message_create(config: dict[str, Any]) -> dict[str, Any]:
    _keys(
        config,
        allowed={"channel_ids", "contains_text", "match", "ignore_bots"},
        required=set(),
        field="trigger_config",
    )
    out: dict[str, Any] = {
        "channel_ids": _id_list(config["channel_ids"], "trigger_config.channel_ids")
        if "channel_ids" in config
        else [],
        "ignore_bots": _boolean(
            config.get("ignore_bots", True), "trigger_config.ignore_bots"
        ),
    }
    if "contains_text" in config:
        out["contains_text"] = _string(
            config["contains_text"], "trigger_config.contains_text", maximum=_MAX_TEXT
        )
        match = _choice(
            config.get("match", "contains"), "trigger_config.match", MATCH_MODES
        )
        out["match"] = match
        if match == "regex":
            _pattern(out["contains_text"], "trigger_config.contains_text")
    return out


def _validate_reaction_add(config: dict[str, Any]) -> dict[str, Any]:
    _keys(
        config,
        allowed={"emoji", "channel_ids", "min_reactions"},
        required={"emoji"},
        field="trigger_config",
    )
    return {
        "emoji": _emoji(config["emoji"], "trigger_config.emoji"),
        "channel_ids": _id_list(config["channel_ids"], "trigger_config.channel_ids")
        if "channel_ids" in config
        else [],
        "min_reactions": _integer(
            config.get("min_reactions", 1),
            "trigger_config.min_reactions",
            minimum=1,
            maximum=1000,
        ),
    }


def _validate_role_update(config: dict[str, Any]) -> dict[str, Any]:
    _keys(
        config,
        allowed={"role_id", "event"},
        required={"role_id", "event"},
        field="trigger_config",
    )
    return {
        "role_id": _snowflake(config["role_id"], "trigger_config.role_id"),
        "event": _choice(config["event"], "trigger_config.event", ROLE_EVENTS),
    }


def _validate_schedule(config: dict[str, Any]) -> dict[str, Any]:
    _keys(
        config,
        allowed={"frequency", "interval_minutes", "hour", "minute", "timezone"},
        required={"frequency"},
        field="trigger_config",
    )
    frequency = _choice(
        config["frequency"], "trigger_config.frequency", SCHEDULE_FREQUENCIES
    )
    out: dict[str, Any] = {
        "frequency": frequency,
        "timezone": _timezone(config.get("timezone", "UTC"), "trigger_config.timezone"),
    }
    if frequency == "interval":
        _keys(
            config,
            allowed={"frequency", "interval_minutes", "timezone"},
            required={"interval_minutes"},
            field="trigger_config",
        )
        out["interval_minutes"] = _integer(
            config["interval_minutes"],
            "trigger_config.interval_minutes",
            minimum=1,
            maximum=10080,
        )
    else:
        _keys(
            config,
            allowed={"frequency", "hour", "minute", "timezone"},
            required={"hour", "minute"},
            field="trigger_config",
        )
        out["hour"] = _integer(
            config["hour"], "trigger_config.hour", minimum=0, maximum=23
        )
        out["minute"] = _integer(
            config["minute"], "trigger_config.minute", minimum=0, maximum=59
        )
    return out


def _validate_safety_alert(config: dict[str, Any]) -> dict[str, Any]:
    _keys(config, allowed={"source"}, required=set(), field="trigger_config")
    return {
        "source": _choice(
            config.get("source", "any"), "trigger_config.source", SAFETY_SOURCES
        )
    }


def _validate_moderation_event(config: dict[str, Any]) -> dict[str, Any]:
    _keys(
        config,
        allowed={"actions", "sources"},
        required=set(),
        field="trigger_config",
    )
    actions = (
        [
            _choice(item, "trigger_config.actions[i]", MODERATION_ACTIONS)
            for item in config.get("actions", [])
        ]
        if isinstance(config.get("actions", []), list)
        else None
    )
    if actions is None:
        raise WorkflowValidationError(
            "`trigger_config.actions` must be an array.", field="trigger_config.actions"
        )
    sources = (
        [
            _choice(
                item,
                "trigger_config.sources[i]",
                ("manual", "workflow", "automod", "antialt"),
            )
            for item in config.get("sources", [])
        ]
        if isinstance(config.get("sources", []), list)
        else None
    )
    if sources is None:
        raise WorkflowValidationError(
            "`trigger_config.sources` must be an array.", field="trigger_config.sources"
        )
    return {"actions": actions, "sources": sources}


_TRIGGER_VALIDATORS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "member_join": _validate_empty,
    "member_leave": _validate_empty,
    "message_create": _validate_message_create,
    "message_delete": _validate_channel_filter,
    "reaction_add": _validate_reaction_add,
    "role_update": _validate_role_update,
    "schedule": _validate_schedule,
    "safety_alert": _validate_safety_alert,
    "moderation_event": _validate_moderation_event,
    "ticket_created": _validate_channel_filter,
}


def validate_trigger(trigger_type: Any, config: Any) -> dict[str, Any]:
    """Validate a trigger type and its config, returning a normalized dict."""

    name = _choice(trigger_type, "trigger_type", TRIGGER_TYPES)
    return _TRIGGER_VALIDATORS[name](_object(config, "trigger_config"))


def validate_custom_config(name: str, config: Any) -> dict[str, Any]:
    """Validate a registered custom trigger's config."""

    if not is_custom_trigger_name(name) or name not in _CUSTOM_TRIGGERS:
        raise WorkflowValidationError(
            f"`trigger_type` `{name}` is not a registered trigger.",
            field="trigger_type",
        )
    return _CUSTOM_TRIGGERS[name](_object(config, "trigger_config"), name)


def _validate_condition(raw: Any, index: int) -> dict[str, Any]:
    field = f"conditions[{index}]"
    condition = _object(raw, field)
    if "type" not in condition:
        raise WorkflowValidationError(f"`{field}` is missing `type`.", field=field)
    kind = _choice(condition["type"], f"{field}.type", CONDITION_TYPES)

    schemas: dict[str, tuple[set[str], set[str]]] = {
        "account_age_lt": ({"days", "negate"}, {"days"}),
        "contains_link": ({"negate"}, set()),
        "contains_text": ({"text", "match", "negate"}, {"text"}),
        "has_role": ({"role_id", "negate"}, {"role_id"}),
        "channel_in": ({"channel_ids", "negate"}, {"channel_ids"}),
        "cooldown_sec": ({"seconds", "scope", "negate"}, {"seconds"}),
        "is_bot": ({"value", "negate"}, {"value"}),
        "emoji_is": ({"emoji", "negate"}, {"emoji"}),
        "reaction_count_gte": ({"count", "negate"}, {"count"}),
        "not_self_react": ({"enabled", "negate"}, set()),
        "safety_source": ({"source", "negate"}, {"source"}),
        "safety_module": ({"module", "negate"}, {"module"}),
        "moderation_action": ({"action", "negate"}, {"action"}),
    }
    allowed, required = schemas[kind]
    _keys(
        condition, allowed=allowed | {"type"}, required=required | {"type"}, field=field
    )
    out: dict[str, Any] = {"type": kind}

    def negate() -> None:
        out["negate"] = _boolean(condition.get("negate", False), f"{field}.negate")

    if kind == "account_age_lt":
        out["days"] = _integer(
            condition["days"], f"{field}.days", minimum=1, maximum=36500
        )
        negate()
    elif kind == "contains_link":
        negate()
    elif kind == "contains_text":
        out["text"] = _string(condition["text"], f"{field}.text", maximum=_MAX_TEXT)
        out["match"] = _choice(
            condition.get("match", "contains"), f"{field}.match", MATCH_MODES
        )
        if out["match"] == "regex":
            _pattern(out["text"], f"{field}.text")
        negate()
    elif kind == "has_role":
        out["role_id"] = _snowflake(condition["role_id"], f"{field}.role_id")
        negate()
    elif kind == "channel_in":
        ids = _id_list(condition["channel_ids"], f"{field}.channel_ids")
        if not ids:
            raise WorkflowValidationError(
                f"`{field}.channel_ids` must not be empty.",
                field=f"{field}.channel_ids",
            )
        out["channel_ids"] = ids
        negate()
    elif kind == "cooldown_sec":
        out["seconds"] = _integer(
            condition["seconds"], f"{field}.seconds", minimum=0, maximum=86400
        )
        out["scope"] = _choice(
            condition.get("scope", "user"), f"{field}.scope", COOLDOWN_SCOPES
        )
        negate()
    elif kind == "is_bot":
        out["value"] = _boolean(condition["value"], f"{field}.value")
        negate()
    elif kind == "emoji_is":
        out["emoji"] = _emoji(condition["emoji"], f"{field}.emoji")
        negate()
    elif kind == "reaction_count_gte":
        out["count"] = _integer(
            condition["count"], f"{field}.count", minimum=1, maximum=1000
        )
        negate()
    elif kind == "not_self_react":
        out["enabled"] = _boolean(condition.get("enabled", True), f"{field}.enabled")
        negate()
    elif kind == "safety_source":
        out["source"] = _string(condition["source"], f"{field}.source", maximum=64)
        negate()
    elif kind == "safety_module":
        out["module"] = _string(condition["module"], f"{field}.module", maximum=64)
        negate()
    elif kind == "moderation_action":
        out["action"] = _choice(
            condition["action"], f"{field}.action", MODERATION_ACTIONS
        )
        negate()

    return out


def validate_conditions(conditions: Any) -> list[dict[str, Any]]:
    """Validate the ordered condition list (all conditions must pass)."""

    if not isinstance(conditions, list):
        raise WorkflowValidationError(
            "`conditions` must be an array.", field="conditions"
        )
    if len(conditions) > _MAX_CONDITIONS:
        raise WorkflowValidationError(
            f"`conditions` may contain at most {_MAX_CONDITIONS} entries.",
            field="conditions",
        )
    return [_validate_condition(raw, index) for index, raw in enumerate(conditions)]


def _validate_action(raw: Any, index: int) -> dict[str, Any]:
    field = f"actions[{index}]"
    action = _object(raw, field)
    if "type" not in action:
        raise WorkflowValidationError(f"`{field}` is missing `type`.", field=field)
    kind = _choice(action["type"], f"{field}.type", ACTION_TYPES)

    schemas: dict[str, tuple[set[str], set[str]]] = {
        "add_role": ({"role_id"}, {"role_id"}),
        "remove_role": ({"role_id"}, {"role_id"}),
        "send_embed": (
            {
                "channel_id",
                "title",
                "description",
                "color",
                "content",
                "from_message",
                "dedupe",
            },
            set(),
        ),
        "send_message": ({"channel_id", "message"}, {"message"}),
        "send_dm": ({"message"}, {"message"}),
        "timeout_member": ({"minutes"}, {"minutes"}),
        "open_ticket": ({"channel_id", "panel_name", "support_role_id"}, set()),
        "log_channel": ({"channel_id", "message"}, {"message"}),
        "create_moderation_case": (
            {"action_type", "reason", "duration_seconds", "moderator_user_id"},
            {"action_type"},
        ),
        "set_scheduled_task": (
            {"kind", "delay_seconds", "run_at", "payload"},
            {"kind"},
        ),
    }
    allowed, required = schemas[kind]
    _keys(action, allowed=allowed | {"type"}, required=required | {"type"}, field=field)
    out: dict[str, Any] = {"type": kind}

    if kind in ("add_role", "remove_role"):
        out["role_id"] = _snowflake(action["role_id"], f"{field}.role_id")
    elif kind == "send_embed":
        if "channel_id" in action:
            out["channel_id"] = _snowflake(action["channel_id"], f"{field}.channel_id")
        if "title" in action:
            out["title"] = _string(action["title"], f"{field}.title", maximum=256)
        if "description" in action:
            out["description"] = _string(
                action["description"], f"{field}.description", maximum=_MAX_DESCRIPTION
            )
        if "color" in action:
            out["color"] = _color(action["color"], f"{field}.color")
        if "content" in action:
            out["content"] = _string(
                action["content"], f"{field}.content", maximum=_MAX_TEXT
            )
        out["from_message"] = _boolean(
            action.get("from_message", False), f"{field}.from_message"
        )
        out["dedupe"] = _boolean(action.get("dedupe", False), f"{field}.dedupe")
    elif kind == "send_message":
        if "channel_id" in action:
            out["channel_id"] = _snowflake(action["channel_id"], f"{field}.channel_id")
        out["message"] = _string(
            action["message"], f"{field}.message", maximum=_MAX_TEXT
        )
    elif kind == "send_dm":
        out["message"] = _string(
            action["message"], f"{field}.message", maximum=_MAX_TEXT
        )
    elif kind == "timeout_member":
        out["minutes"] = _integer(
            action["minutes"], f"{field}.minutes", minimum=1, maximum=40320
        )
    elif kind == "open_ticket":
        if "channel_id" in action:
            out["channel_id"] = _snowflake(action["channel_id"], f"{field}.channel_id")
        if "support_role_id" in action:
            out["support_role_id"] = _snowflake(
                action["support_role_id"], f"{field}.support_role_id"
            )
        out["panel_name"] = _string(
            action.get("panel_name", "Support"), f"{field}.panel_name"
        )
    elif kind == "log_channel":
        if "channel_id" in action:
            out["channel_id"] = _snowflake(action["channel_id"], f"{field}.channel_id")
        out["message"] = _string(
            action["message"], f"{field}.message", maximum=_MAX_TEXT
        )
    elif kind == "create_moderation_case":
        out["action_type"] = _choice(
            action["action_type"], f"{field}.action_type", MODERATION_ACTIONS
        )
        out["reason"] = _string(
            action.get("reason", "Workflow action"),
            f"{field}.reason",
            maximum=_MAX_TEXT,
        )
        if "duration_seconds" in action:
            out["duration_seconds"] = _integer(
                action["duration_seconds"],
                f"{field}.duration_seconds",
                minimum=0,
                maximum=31536000,
            )
        if "moderator_user_id" in action:
            out["moderator_user_id"] = _snowflake(
                action["moderator_user_id"], f"{field}.moderator_user_id"
            )
    elif kind == "set_scheduled_task":
        out["kind"] = _choice(action["kind"], f"{field}.kind", SCHEDULED_TASK_KINDS)
        if ("delay_seconds" in action) == ("run_at" in action):
            raise WorkflowValidationError(
                f"`{field}` needs exactly one of `delay_seconds` or `run_at`.",
                field=field,
            )
        if "delay_seconds" in action:
            out["delay_seconds"] = _integer(
                action["delay_seconds"],
                f"{field}.delay_seconds",
                minimum=1,
                maximum=604800,
            )
        else:
            out["run_at"] = _timestamp(action["run_at"], f"{field}.run_at")
        out["payload"] = _payload(action.get("payload", {}), f"{field}.payload")

    return out


def validate_actions(actions: Any) -> list[dict[str, Any]]:
    """Validate the ordered action list and keep its execution order."""

    if not isinstance(actions, list):
        raise WorkflowValidationError("`actions` must be an array.", field="actions")
    if not actions:
        raise WorkflowValidationError("`actions` must not be empty.", field="actions")
    if len(actions) > _MAX_ACTIONS:
        raise WorkflowValidationError(
            f"`actions` may contain at most {_MAX_ACTIONS} entries.", field="actions"
        )
    return [_validate_action(raw, index) for index, raw in enumerate(actions)]


_TOP_LEVEL_FIELDS = {
    "name",
    "description",
    "enabled",
    "trigger_type",
    "trigger_config",
    "conditions",
    "actions",
    "schema_version",
    "workflow_id",
    "guild_id",
    "revision",
    "created_at",
    "updated_at",
}
_ROW_ONLY_FIELDS = {"id", "definition_id", "created_by"}
_REQUIRED_FIELDS = {"name", "trigger_type", "trigger_config", "conditions", "actions"}


def validate_workflow(
    payload: Any, *, allow_row_fields: bool = False
) -> dict[str, Any]:
    """Validate/normalize a complete workflow payload.

    The returned mapping always carries the versioned/portable metadata fields,
    using ``None`` for values that are not known yet. Row-only fields are kept
    when ``allow_row_fields`` is set so the runner can identify a stored row.
    """

    data = _object(payload, "workflow")
    allowed = set(_TOP_LEVEL_FIELDS)
    if allow_row_fields:
        allowed |= _ROW_ONLY_FIELDS
    _keys(data, allowed=allowed, required=_REQUIRED_FIELDS, field="workflow")

    trigger_type = _string(data["trigger_type"], "trigger_type", maximum=_MAX_SHORT)
    if trigger_type in _TRIGGER_VALIDATORS:
        trigger_config = validate_trigger(trigger_type, data["trigger_config"])
    else:
        trigger_config = validate_custom_config(trigger_type, data["trigger_config"])

    version = _integer(
        data.get("schema_version", CURRENT_SCHEMA_VERSION),
        "schema_version",
        minimum=1,
        maximum=100,
    )
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise WorkflowValidationError(
            "Unsupported workflow schema version "
            f"{version}; supported versions: {', '.join(map(str, SUPPORTED_SCHEMA_VERSIONS))}.",
            field="schema_version",
        )

    out: dict[str, Any] = {
        "name": _string(data["name"], "name", maximum=_MAX_SHORT),
        "description": _string(
            data.get("description", ""),
            "description",
            minimum=0,
            maximum=_MAX_DESCRIPTION,
        ),
        "enabled": _boolean(data.get("enabled", True), "enabled"),
        "trigger_type": trigger_type,
        "trigger_config": trigger_config,
        "conditions": validate_conditions(data["conditions"]),
        "actions": validate_actions(data["actions"]),
        "schema_version": version,
        "workflow_id": _uuid(data["workflow_id"], "workflow_id")
        if data.get("workflow_id") is not None
        else None,
        "guild_id": _snowflake(data["guild_id"], "guild_id")
        if data.get("guild_id") is not None
        else None,
        "revision": _integer(data["revision"], "revision", minimum=1, maximum=1000000)
        if data.get("revision") is not None
        else None,
        "created_at": _timestamp(data["created_at"], "created_at")
        if data.get("created_at") is not None
        else None,
        "updated_at": _timestamp(data["updated_at"], "updated_at")
        if data.get("updated_at") is not None
        else None,
    }
    if allow_row_fields:
        out["id"] = (
            _integer(data["id"], "id", minimum=1)
            if data.get("id") is not None
            else None
        )
        out["definition_id"] = (
            _uuid(data["definition_id"], "definition_id")
            if data.get("definition_id") is not None
            else None
        )
        out["created_by"] = (
            _snowflake(data["created_by"], "created_by")
            if data.get("created_by") is not None
            else None
        )
    return out


def _uses_content_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return "{content}" in value
    if isinstance(value, dict):
        return any(_uses_content_placeholder(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_uses_content_placeholder(item) for item in value)
    return False


def validate_supported_workflow(
    definition: dict[str, Any], *, can_read_message_content: bool
) -> None:
    """Reject workflows that depend on the Message Content privileged intent.

    This is enforced in code so an operator cannot configure a silently dead
    keyword/regex automation. Metadata-only triggers and conditions remain
    available when the intent is disabled.
    """

    if can_read_message_content:
        return
    trigger_type = definition.get("trigger_type")
    trigger_config = definition.get("trigger_config") or {}
    if trigger_type in MESSAGE_CONTENT_TRIGGERS and any(
        key in trigger_config for key in MESSAGE_CONTENT_TRIGGER_KEYS
    ):
        raise WorkflowValidationError(
            "Text-based message triggers require the Message Content intent, "
            "which is not enabled.",
            field="trigger_config",
        )
    for index, condition in enumerate(definition.get("conditions") or []):
        if (
            isinstance(condition, dict)
            and condition.get("type") in MESSAGE_CONTENT_CONDITIONS
        ):
            raise WorkflowValidationError(
                f"`conditions[{index}]` requires the Message Content intent, "
                "which is not enabled.",
                field=f"conditions[{index}]",
            )
    for index, action in enumerate(definition.get("actions") or []):
        if not isinstance(action, dict):
            continue
        if action.get("from_message"):
            raise WorkflowValidationError(
                f"`actions[{index}].from_message` requires the Message Content intent, "
                "which is not enabled.",
                field=f"actions[{index}]",
            )
        if _uses_content_placeholder(action):
            raise WorkflowValidationError(
                f"`actions[{index}]` uses `{{content}}`, which requires the Message "
                "Content intent and is not enabled.",
                field=f"actions[{index}]",
            )


@dataclass(frozen=True)
class WorkflowDefinition:
    """Portable representation of a validated workflow definition."""

    name: str
    trigger_type: str
    trigger_config: dict[str, Any]
    conditions: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    description: str = ""
    enabled: bool = True
    schema_version: int = CURRENT_SCHEMA_VERSION
    workflow_id: str | None = None
    guild_id: int | None = None
    revision: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
    id: int | None = None
    definition_id: str | None = None
    created_by: int | None = None

    @classmethod
    def from_mapping(
        cls, payload: Any, *, allow_row_fields: bool = False
    ) -> WorkflowDefinition:
        data = validate_workflow(payload, allow_row_fields=allow_row_fields)
        fields = {
            key: value for key, value in data.items() if key in cls.__dataclass_fields__
        }
        return cls(**fields)

    def to_mapping(self, *, portable: bool = False) -> dict[str, Any]:
        data = {
            "schema_version": self.schema_version,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "trigger_type": self.trigger_type,
            "trigger_config": dict(self.trigger_config),
            "conditions": [dict(item) for item in self.conditions],
            "actions": [dict(item) for item in self.actions],
        }
        if not portable:
            data.update(
                {
                    "workflow_id": self.workflow_id,
                    "guild_id": self.guild_id,
                    "revision": self.revision,
                    "id": self.id,
                    "definition_id": self.definition_id,
                    "created_at": self.created_at,
                    "updated_at": self.updated_at,
                    "created_by": self.created_by,
                }
            )
        return data


def export_workflow(payload: Any) -> dict[str, Any]:
    """Return a portable, guild-independent JSON document."""

    return WorkflowDefinition.from_mapping(payload, allow_row_fields=True).to_mapping(
        portable=True
    )


def import_workflow(payload: Any) -> dict[str, Any]:
    """Validate an imported document and drop database-specific identifiers."""

    return export_workflow(payload)


@dataclass(frozen=True)
class WorkflowLimits:
    max_active: int | None
    max_actions: int | None

    def describe(self) -> str:
        active = "unlimited" if self.max_active is None else str(self.max_active)
        actions = "unlimited" if self.max_actions is None else str(self.max_actions)
        return f"{active} active workflows, {actions} actions per workflow"


def limits_for_tier(tier: Tier) -> WorkflowLimits:
    """Free: 5 active / 2 actions. Basic: 25 / 5. Pro: unlimited."""

    if tier >= Tier.PRO:
        return WorkflowLimits(None, None)
    if tier >= Tier.BASIC:
        return WorkflowLimits(25, 5)
    return WorkflowLimits(5, 2)


async def resolve_tier(
    source: Any,
    guild_id: int,
    *,
    tier: Tier | None = None,
) -> Tier:
    """Resolve a guild tier from an explicit tier, bot, entitlement service or pool."""

    if tier is not None:
        return tier
    if isinstance(source, Tier):
        return source
    service: EntitlementService | None = None
    if isinstance(source, EntitlementService):
        service = source
    elif source is not None and isinstance(
        getattr(source, "entitlements", None), EntitlementService
    ):
        service = source.entitlements
    if service is not None:
        return await service.tier_for(guild_id)
    if source is None:
        return Tier.FREE
    nested = getattr(source, "db", None)
    if nested is not None and getattr(nested, "fetchrow", None) is not None:
        source = nested
    fetchrow = getattr(source, "fetchrow", None)
    if fetchrow is None:
        return Tier.FREE
    row = await fetchrow("SELECT tier, status FROM premium WHERE guild_id=$1", guild_id)
    if row is None or row["status"] != "active":
        return Tier.FREE
    try:
        return Tier(int(row["tier"]))
    except ValueError:
        return Tier.FREE


async def get_guild_tier(source: Any, guild_id: int) -> Tier:
    """Resolve a guild's tier through the single entitlement resolver."""

    return await resolve_tier(source, guild_id)


async def count_active_workflows(
    source: Any, guild_id: int, *, exclude_id: int | None = None
) -> int:
    """Count enabled workflows for a guild (excluding one being toggled)."""

    if source is None:
        return 0
    for candidate in (getattr(source, "repo", None), getattr(source, "database", None)):
        if callable(getattr(candidate, "count_active", None)):
            return int(await candidate.count_active(guild_id, exclude_id=exclude_id))
    nested = getattr(source, "db", None)
    if nested is not None and (
        callable(getattr(nested, "fetchval", None))
        or callable(getattr(nested, "count_active", None))
    ):
        source = nested
    count = getattr(source, "count_active", None)
    if callable(count):
        return int(await count(guild_id, exclude_id=exclude_id))
    fetchval = getattr(source, "fetchval", None)
    if fetchval is None:
        return 0
    if exclude_id is None:
        value = await fetchval(
            "SELECT COUNT(*) FROM workflow_definitions "
            "WHERE guild_id=$1 AND enabled=TRUE",
            guild_id,
        )
    else:
        value = await fetchval(
            "SELECT COUNT(*) FROM workflow_definitions "
            "WHERE guild_id=$1 AND enabled=TRUE AND id<>$2",
            guild_id,
            exclude_id,
        )
    return int(value or 0)


async def enforce_tier_limits(
    source: Any,
    guild_id: int,
    *,
    actions: list[dict[str, Any]],
    enabled: bool = True,
    workflow_id: int | None = None,
    tier: Tier | None = None,
) -> Tier:
    """Enforce tier limits before an insert/update. Raises on violation."""

    resolved = await resolve_tier(source, guild_id, tier=tier)
    limits = limits_for_tier(resolved)

    if limits.max_actions is not None and len(actions) > limits.max_actions:
        raise WorkflowValidationError(
            f"The {resolved.name} tier allows at most {limits.max_actions} actions per "
            f"workflow (got {len(actions)}). Upgrade with `@Lucent premium`.",
            field="actions",
        )

    if enabled and limits.max_active is not None:
        used = await count_active_workflows(source, guild_id, exclude_id=workflow_id)
        if used >= limits.max_active:
            raise WorkflowValidationError(
                f"The {resolved.name} tier allows at most {limits.max_active} active "
                f"workflows (already have {used}). Disable or delete one first, "
                "or upgrade with `@Lucent premium`.",
                field="enabled",
            )

    return resolved
