"""Strict validation for workflow trigger/condition/action JSONB.

This module is the single source of truth for the workflow schema. Both the
``/workflow`` slash commands and an external web dashboard can validate,
normalize and persist workflow payloads through it.

A workflow payload has this shape::

    {
      "name": "Welcome",
      "enabled": true,
      "trigger_type": "member_join",
      "trigger_config": {},
      "conditions": [{"type": "account_age_lt", "days": 7}],
      "actions": [{"type": "add_role", "role_id": 123}]
    }
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.bot import Tier
from utils.custom_checks import _tier_cache

TRIGGER_TYPES = (
    "member_join",
    "message_create",
    "reaction_add",
    "role_update",
    "schedule",
    "safety_alert",
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
)

MATCH_MODES = ("contains", "exact", "starts_with", "regex")
SCHEDULE_FREQUENCIES = ("interval", "daily")
SAFETY_SOURCES = ("antialt", "automod", "any")
ROLE_EVENTS = ("added", "removed")
COOLDOWN_SCOPES = ("user", "guild", "workflow")

_MAX_SHORT = 100
_MAX_TEXT = 2000
_MAX_DESCRIPTION = 4096
_MAX_ACTIONS = 20
_MAX_CONDITIONS = 20


class WorkflowValidationError(ValueError):
    """Raised when a workflow payload violates the strict schema or tier limits."""

    def __init__(self, message: str, *, field: str | None = None):
        self.field = field
        super().__init__(message)


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


# ── primitive checks ──────────────────────────────────────────────────────────


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
    if not isinstance(value, list):
        raise WorkflowValidationError(
            f"`{field}` must be an array of IDs.", field=field
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


def _pattern(value: Any, field: str) -> str:
    text = _string(value, field, maximum=_MAX_TEXT)
    try:
        re.compile(text)
    except re.error as exc:
        raise WorkflowValidationError(
            f"`{field}` is not a valid regular expression: {exc}", field=field
        ) from exc
    return text


def _emoji(value: Any, field: str) -> str:
    return _string(value, field, maximum=64)


# ── trigger validation ───────────────────────────────────────────────────────


def _validate_member_join(config: dict[str, Any]) -> dict[str, Any]:
    _keys(config, allowed=set(), required=set(), field="trigger_config")
    return {}


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


_TRIGGER_VALIDATORS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "member_join": _validate_member_join,
    "message_create": _validate_message_create,
    "reaction_add": _validate_reaction_add,
    "role_update": _validate_role_update,
    "schedule": _validate_schedule,
    "safety_alert": _validate_safety_alert,
}


def validate_trigger(trigger_type: Any, config: Any) -> dict[str, Any]:
    """Validate a trigger type and its config, returning a normalized dict."""
    name = _choice(trigger_type, "trigger_type", TRIGGER_TYPES)
    return _TRIGGER_VALIDATORS[name](_object(config, "trigger_config"))


# ── condition validation ─────────────────────────────────────────────────────


def _validate_condition(raw: Any, index: int) -> dict[str, Any]:
    field = f"conditions[{index}]"
    condition = _object(raw, field)
    if "type" not in condition:
        raise WorkflowValidationError(f"`{field}` is missing `type`.", field=field)
    kind = _choice(condition["type"], f"{field}.type", CONDITION_TYPES)

    schemas: dict[str, tuple[set[str], set[str]]] = {
        "account_age_lt": ({"days"}, {"days"}),
        "contains_link": ({"negate"}, set()),
        "contains_text": ({"text", "match", "negate"}, {"text"}),
        "has_role": ({"role_id", "negate"}, {"role_id"}),
        "channel_in": ({"channel_ids", "negate"}, {"channel_ids"}),
        "cooldown_sec": ({"seconds", "scope"}, {"seconds"}),
        "is_bot": ({"value"}, {"value"}),
        "emoji_is": ({"emoji"}, {"emoji"}),
        "reaction_count_gte": ({"count"}, {"count"}),
        "not_self_react": ({"enabled"}, set()),
    }
    allowed, required = schemas[kind]
    _keys(
        condition, allowed=allowed | {"type"}, required=required | {"type"}, field=field
    )
    out: dict[str, Any] = {"type": kind}

    if kind == "account_age_lt":
        out["days"] = _integer(
            condition["days"], f"{field}.days", minimum=1, maximum=36500
        )
    elif kind == "contains_link":
        out["negate"] = _boolean(condition.get("negate", False), f"{field}.negate")
    elif kind == "contains_text":
        out["text"] = _string(condition["text"], f"{field}.text", maximum=_MAX_TEXT)
        out["match"] = _choice(
            condition.get("match", "contains"), f"{field}.match", MATCH_MODES
        )
        out["negate"] = _boolean(condition.get("negate", False), f"{field}.negate")
        if out["match"] == "regex":
            _pattern(out["text"], f"{field}.text")
    elif kind == "has_role":
        out["role_id"] = _snowflake(condition["role_id"], f"{field}.role_id")
        out["negate"] = _boolean(condition.get("negate", False), f"{field}.negate")
    elif kind == "channel_in":
        ids = _id_list(condition["channel_ids"], f"{field}.channel_ids")
        if not ids:
            raise WorkflowValidationError(
                f"`{field}.channel_ids` must not be empty.",
                field=f"{field}.channel_ids",
            )
        out["channel_ids"] = ids
        out["negate"] = _boolean(condition.get("negate", False), f"{field}.negate")
    elif kind == "cooldown_sec":
        out["seconds"] = _integer(
            condition["seconds"], f"{field}.seconds", minimum=0, maximum=86400
        )
        out["scope"] = _choice(
            condition.get("scope", "user"), f"{field}.scope", COOLDOWN_SCOPES
        )
    elif kind == "is_bot":
        out["value"] = _boolean(condition["value"], f"{field}.value")
    elif kind == "emoji_is":
        out["emoji"] = _emoji(condition["emoji"], f"{field}.emoji")
    elif kind == "reaction_count_gte":
        out["count"] = _integer(
            condition["count"], f"{field}.count", minimum=1, maximum=1000
        )
    elif kind == "not_self_react":
        out["enabled"] = _boolean(condition.get("enabled", True), f"{field}.enabled")

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


# ── action validation ────────────────────────────────────────────────────────


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


# ── full workflow validation ─────────────────────────────────────────────────


def validate_workflow(
    payload: Any, *, allow_row_fields: bool = False
) -> dict[str, Any]:
    """Validate/normalize a complete workflow payload for JSONB persistence."""
    data = _object(payload, "workflow")
    allowed = {
        "name",
        "enabled",
        "trigger_type",
        "trigger_config",
        "conditions",
        "actions",
    }
    if allow_row_fields:
        allowed |= {"id", "guild_id", "created_at", "updated_at"}
    _keys(
        data,
        allowed=allowed,
        required={"name", "trigger_type", "trigger_config", "conditions", "actions"},
        field="workflow",
    )
    return {
        "name": _string(data["name"], "name", maximum=_MAX_SHORT),
        "enabled": _boolean(data.get("enabled", True), "enabled"),
        "trigger_type": _choice(data["trigger_type"], "trigger_type", TRIGGER_TYPES),
        "trigger_config": validate_trigger(
            data["trigger_type"], data["trigger_config"]
        ),
        "conditions": validate_conditions(data["conditions"]),
        "actions": validate_actions(data["actions"]),
    }


# ── tier limits (Polar/premium integration) ──────────────────────────────────


@dataclass(frozen=True)
class WorkflowLimits:
    max_active: int | None
    max_actions: int | None

    def describe(self) -> str:
        active = "unlimited" if self.max_active is None else str(self.max_active)
        actions = "unlimited" if self.max_actions is None else str(self.max_actions)
        return f"{active} active workflows, {actions} actions per workflow"


def limits_for_tier(tier: Tier) -> WorkflowLimits:
    """Free: 5 active / 2 actions. Pro: unlimited. Basic: 25 / 5."""
    if tier >= Tier.PRO:
        return WorkflowLimits(None, None)
    if tier >= Tier.BASIC:
        return WorkflowLimits(25, 5)
    return WorkflowLimits(5, 2)


async def get_guild_tier(pool: Any, guild_id: int) -> Tier:
    """Resolve a guild's tier using the existing premium check cache."""
    cached = _tier_cache.get(guild_id)
    if cached is not None:
        return cached
    tier = Tier.FREE
    if pool is not None:
        row = await pool.fetchrow(
            "SELECT tier FROM premium WHERE guild_id=$1", guild_id
        )
        if row:
            tier = Tier(row["tier"])
    _tier_cache[guild_id] = tier
    return tier


async def count_active_workflows(
    pool: Any, guild_id: int, *, exclude_id: int | None = None
) -> int:
    """Count enabled workflows for a guild (excluding one being toggled)."""
    if pool is None:
        return 0
    if exclude_id is None:
        return int(
            await pool.fetchval(
                "SELECT COUNT(*) FROM workflows WHERE guild_id=$1 AND enabled=TRUE",
                guild_id,
            )
            or 0
        )
    return int(
        await pool.fetchval(
            "SELECT COUNT(*) FROM workflows WHERE guild_id=$1 AND enabled=TRUE AND id<>$2",
            guild_id,
            exclude_id,
        )
        or 0
    )


async def enforce_tier_limits(
    pool: Any,
    guild_id: int,
    *,
    actions: list[dict[str, Any]],
    enabled: bool = True,
    workflow_id: int | None = None,
    tier: Tier | None = None,
) -> Tier:
    """Enforce tier limits before an insert/update. Raises on violation."""
    tier = tier or await get_guild_tier(pool, guild_id)
    limits = limits_for_tier(tier)

    if limits.max_actions is not None and len(actions) > limits.max_actions:
        raise WorkflowValidationError(
            f"The {tier.name} tier allows at most {limits.max_actions} actions per "
            f"workflow (got {len(actions)}). Upgrade with `/premium`.",
            field="actions",
        )

    if enabled and limits.max_active is not None:
        used = await count_active_workflows(pool, guild_id, exclude_id=workflow_id)
        if used >= limits.max_active:
            raise WorkflowValidationError(
                f"The {tier.name} tier allows at most {limits.max_active} active "
                f"workflows (already have {used}). Disable or delete one first, "
                "or upgrade with `/premium`.",
                field="enabled",
            )

    return tier
