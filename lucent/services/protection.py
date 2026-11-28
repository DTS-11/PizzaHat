"""Central configuration for AutoMod, Anti-Alt and safety rules.

The command surface, event listeners and workflow engine all read protection
settings through this module. Thresholds and action defaults live here so no
listener carries a private copy of the numbers.
"""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from typing import Any, Callable

from core.entitlements import EntitlementService, Tier

FREE_MODULES = (
    "banned_words",
    "all_caps",
    "message_spam",
    "invites",
    "mass_mentions",
    "emoji_spam",
    "zalgo_text",
)
BASIC_MODULES = (
    "newline_spam",
    "repeated_chars",
    "scam_links",
    "username_filter",
    "default_avatar",
    "join_rate",
)
ALL_MODULES = FREE_MODULES + BASIC_MODULES

CONTENT_MODULES = frozenset(
    {
        "banned_words",
        "scam_links",
        "all_caps",
        "invites",
        "emoji_spam",
        "zalgo_text",
        "newline_spam",
        "repeated_chars",
    }
)

PRO_ACTIONS = frozenset({"tempban", "role_add", "role_remove"})
PRO_SETTINGS = frozenset({"lockdown_minutes"})
MODULE_TIERS: dict[str, Tier] = {
    **{module: Tier.FREE for module in FREE_MODULES},
    **{module: Tier.BASIC for module in BASIC_MODULES},
}

MODULE_DESCRIPTIONS = {
    "banned_words": "Delete messages containing blacklisted words",
    "all_caps": "Delete messages exceeding the caps % threshold",
    "message_spam": "Purge rapid repeated messages from one user",
    "invites": "Delete external Discord invite links",
    "mass_mentions": "Delete messages with excessive @mentions",
    "emoji_spam": "Delete messages with too many emojis",
    "zalgo_text": "Delete zalgo / corrupted unicode text",
    "newline_spam": "Delete messages with excessive line breaks  [Basic]",
    "repeated_chars": "Delete messages with repeated character runs  [Basic]",
    "scam_links": "Delete known phishing/scam domains  [Basic]",
    "username_filter": "Kick members with banned words or staff impersonation  [Basic]",
    "default_avatar": "Act on members who join with no avatar  [Basic]",
    "join_rate": "Detect mass joins and trigger auto-lockdown  [Basic]",
}

DEFAULT_MODULE_SETTINGS: dict[str, dict[str, Any]] = {
    "banned_words": {},
    "all_caps": {"threshold": 70, "min_length": 8},
    "message_spam": {"threshold": 5, "window_seconds": 6},
    "invites": {"whitelist": []},
    "mass_mentions": {"threshold": 4},
    "emoji_spam": {"threshold": 10},
    "zalgo_text": {},
    "newline_spam": {"threshold": 10},
    "repeated_chars": {"threshold": 15},
    "scam_links": {},
    "username_filter": {"impersonation_check": True, "similarity": 0.85},
    "default_avatar": {"action": "restrict"},
    "join_rate": {"threshold": 10, "window_seconds": 30, "lockdown_minutes": 15},
}

DEFAULT_AUTOMOD: dict[str, Any] = {
    "enabled": False,
    "thresholds": [],
    "overrides": {},
    "warn_decay_days": 0,
}
DEFAULT_ANTIALT: dict[str, Any] = {
    "enabled": False,
    "level": 1,
    "min_age": 7,
    "restricted_role": None,
}
DEFAULT_SAFETY: dict[str, Any] = {}

DEFAULT_THRESHOLD_SETTINGS: dict[str, Any] = {
    "duration": 3600,
    "unban_days": 1,
}

ANTIALT_LEVELS = {
    1: (
        "🚫",
        "Restrict",
        "Add the restricted role — user can't send messages or react.",
    ),
    2: ("👞", "Kick", "Kick the suspect. If they rejoin, they're kicked again."),
    3: ("🔨", "Ban", "Permanently ban the suspect."),
}

_SECTION_COLUMNS = {
    "automod": "automod",
    "antialt": "antialt",
    "safety": "safety",
}
_SECTION_DEFAULTS = {
    "automod": DEFAULT_AUTOMOD,
    "antialt": DEFAULT_ANTIALT,
    "safety": DEFAULT_SAFETY,
}


def module_defaults(module: str) -> dict[str, Any]:
    """Return a copy of the configured defaults for *module*."""

    return deepcopy(DEFAULT_MODULE_SETTINGS.get(module, {}))


def default_module_config(modules: tuple[str, ...] | list[str]) -> dict[str, Any]:
    """Build the initial module map used when AutoMod is enabled."""

    return {module: {"enabled": True, **module_defaults(module)} for module in modules}


def is_module_enabled(
    config: dict[str, Any], module: str, channel_id: int | None = None
) -> bool:
    """Resolve a module toggle, with channel overrides taking precedence."""

    if channel_id is not None:
        overrides = config.get("overrides") or {}
        override = (
            overrides.get(str(channel_id)) if isinstance(overrides, dict) else None
        )
        if isinstance(override, dict) and module in override:
            value = override[module]
            return (
                bool(value) if isinstance(value, bool) else bool(value.get("enabled"))
            )

    value = config.get(module, {})
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        return bool(value.get("enabled", False))
    return False


def _parse_jsonb(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return deepcopy(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _normalize(section: str, config: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = deepcopy(_SECTION_DEFAULTS.get(section, {}))
    result.update(deepcopy(config))

    if section == "automod":
        for module in ALL_MODULES:
            value = result.get(module, {})
            if not isinstance(value, dict):
                value = {"enabled": bool(value)}
            result[module] = {**module_defaults(module), **value}
        thresholds = result.get("thresholds")
        result["thresholds"] = (
            [dict(entry) for entry in thresholds if isinstance(entry, dict)]
            if isinstance(thresholds, list)
            else []
        )
        overrides = result.get("overrides")
        result["overrides"] = (
            {str(k): v for k, v in overrides.items()}
            if isinstance(overrides, dict)
            else {}
        )
        try:
            result["warn_decay_days"] = max(0, int(result.get("warn_decay_days") or 0))
        except (TypeError, ValueError):
            result["warn_decay_days"] = 0
        result["enabled"] = bool(result.get("enabled"))
    elif section == "antialt":
        for key in ("min_age", "level"):
            try:
                result[key] = max(1, int(result.get(key) or 1))
            except (TypeError, ValueError):
                result[key] = DEFAULT_ANTIALT[key]
        result["enabled"] = bool(result.get("enabled"))
    return result


class ProtectionService:
    """Read/write ``automation_config`` with one set of validated defaults."""

    def __init__(
        self,
        pool: Any | None,
        entitlements: EntitlementService | None = None,
    ) -> None:
        self.db = pool
        self.entitlements = entitlements
        self._cache: dict[tuple[int, str], dict[str, Any]] = {}

    def invalidate(self, guild_id: int | None = None) -> None:
        if guild_id is None:
            self._cache.clear()
        else:
            for key in [key for key in self._cache if key[0] == guild_id]:
                self._cache.pop(key, None)

    async def is_configured(self, guild_id: int, section: str) -> bool:
        """Whether the guild has any automation config persisted."""

        if section not in _SECTION_COLUMNS or self.db is None:
            return False
        return bool(
            await self.db.fetchval(
                "SELECT EXISTS(SELECT 1 FROM automation_config WHERE guild_id=$1)",
                guild_id,
            )
        )

    async def tier_for(self, guild_id: int) -> Tier:
        if self.entitlements is not None:
            return await self.entitlements.tier_for(guild_id)
        if self.db is None:
            return Tier.FREE
        row = await self.db.fetchrow(
            "SELECT tier, status FROM subscriptions WHERE guild_id=$1", guild_id
        )
        if row is None or row["status"] != "active":
            return Tier.FREE
        try:
            return Tier(int(row["tier"]))
        except ValueError:
            return Tier.FREE

    @staticmethod
    def required_tier(module: str, setting: str | None = None) -> Tier:
        if setting in PRO_SETTINGS:
            return Tier.PRO
        return MODULE_TIERS.get(module, Tier.BASIC)

    async def get(self, guild_id: int, section: str = "automod") -> dict[str, Any]:
        if section not in _SECTION_COLUMNS:
            raise ValueError(f"Unknown protection section: {section}")
        key = (guild_id, section)
        cached = self._cache.get(key)
        if cached is not None:
            return deepcopy(cached)

        config: dict[str, Any] = {}
        if self.db is not None:
            row = await self.db.fetchrow(
                "SELECT automod, antialt, safety FROM automation_config "
                "WHERE guild_id=$1",
                guild_id,
            )
            if row is not None:
                config = _parse_jsonb(row[section])

        normalized = _normalize(section, config)
        self._cache[key] = deepcopy(normalized)
        return normalized

    async def set(
        self, guild_id: int, section: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        column = _SECTION_COLUMNS.get(section)
        if column is None:
            raise ValueError(f"Unknown protection section: {section}")

        normalized = _normalize(section, config)
        if self.db is not None:
            await self.db.execute(
                f"""INSERT INTO automation_config (guild_id, {column}, version)
                    VALUES ($1, $2::jsonb, 1)
                    ON CONFLICT (guild_id) DO UPDATE
                    SET {column}=EXCLUDED.{column},
                        version=automation_config.version + 1,
                        updated_at=NOW()""",
                guild_id,
                json.dumps(normalized, default=str),
            )
        self.invalidate(guild_id)
        self._cache[(guild_id, section)] = deepcopy(normalized)
        return normalized

    async def update(
        self,
        guild_id: int,
        section: str,
        mutate: Callable[[dict[str, Any]], None | dict[str, Any]],
    ) -> dict[str, Any]:
        """Read-modify-write helper that keeps cached readers in sync."""

        config = await self.get(guild_id, section)
        result = mutate(config)
        if isinstance(result, dict):
            config = result
        return await self.set(guild_id, section, config)

    async def automod(self, guild_id: int) -> dict[str, Any]:
        return await self.get(guild_id, "automod")

    async def antialt(self, guild_id: int) -> dict[str, Any]:
        return await self.get(guild_id, "antialt")

    async def safety(self, guild_id: int) -> dict[str, Any]:
        return await self.get(guild_id, "safety")

    async def set_automod(self, guild_id: int, config: dict[str, Any]) -> None:
        await self.set(guild_id, "automod", config)

    async def set_antialt(self, guild_id: int, config: dict[str, Any]) -> None:
        await self.set(guild_id, "antialt", config)

    async def set_safety(self, guild_id: int, config: dict[str, Any]) -> None:
        await self.set(guild_id, "safety", config)

    async def automod_enabled(self, guild_id: int) -> bool:
        return bool((await self.automod(guild_id)).get("enabled"))

    async def antialt_enabled(self, guild_id: int) -> bool:
        return bool((await self.antialt(guild_id)).get("enabled"))

    async def thresholds(self, guild_id: int) -> list[dict[str, Any]]:
        thresholds = (await self.automod(guild_id)).get("thresholds") or []
        return sorted(thresholds, key=lambda entry: int(entry.get("warns", 0)))

    async def warn_decay_days(self, guild_id: int) -> int:
        return int((await self.automod(guild_id)).get("warn_decay_days") or 0)

    async def module_settings(
        self, guild_id: int, module: str, channel_id: int | None = None
    ) -> dict[str, Any]:
        config = await self.automod(guild_id)
        settings = deepcopy(module_defaults(module))
        settings.update(config.get(module) or {})
        if channel_id is not None:
            overrides = config.get("overrides") or {}
            override = overrides.get(str(channel_id)) or {}
            if isinstance(override, dict) and isinstance(override.get(module), dict):
                settings.update(override[module])
        return settings

    async def module_enabled(
        self, guild_id: int, module: str, channel_id: int | None = None
    ) -> bool:
        return is_module_enabled(await self.automod(guild_id), module, channel_id)

    async def detect_rules(
        self, guild_id: int, channel_id: int | None = None
    ) -> list[tuple[str, dict[str, Any]]]:
        """Return the active detection rules and their resolved settings."""

        config = await self.automod(guild_id)
        if not config.get("enabled"):
            return []
        rules: list[tuple[str, dict[str, Any]]] = []
        for module in ALL_MODULES:
            if not is_module_enabled(config, module, channel_id):
                continue
            settings = deepcopy(module_defaults(module))
            settings.update(config.get(module) or {})
            overrides = config.get("overrides") or {}
            if channel_id is not None:
                override = overrides.get(str(channel_id)) or {}
                if isinstance(override.get(module), dict):
                    settings.update(override[module])
            rules.append((module, settings))
        return rules
