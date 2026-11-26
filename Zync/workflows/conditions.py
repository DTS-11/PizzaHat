"""Deterministic workflow condition evaluation.

Conditions never execute user code. Regular expressions are capped in both
pattern and input length, cached, and evaluated on a bounded copy of the event
text. ``negate`` is supported uniformly on every condition type.
"""

from __future__ import annotations

import datetime
import functools
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import discord

from workflows import schema
from workflows.triggers import WorkflowContext

logger = logging.getLogger("bot")

_LINK_REGEX = re.compile(
    r"https?://|discord\.(gg|io|me|li)/|discordapp\.com|discord\.com/invite/",
    re.IGNORECASE,
)
_MAX_INPUT = 4000
_COOLDOWN_TTL = 86400


@dataclass(frozen=True)
class ConditionResult:
    type: str
    passed: bool
    negate: bool = False
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "passed": self.passed,
            "negate": self.negate,
            "detail": self.detail[:200],
        }


@dataclass
class Evaluation:
    results: list[ConditionResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    def as_dicts(self) -> list[dict[str, Any]]:
        return [result.to_dict() for result in self.results]


@functools.lru_cache(maxsize=256)
def _compiled(pattern: str) -> re.Pattern[str] | None:
    if len(pattern) > schema._MAX_PATTERN:  # noqa: SLF001 - schema owns the cap
        return None
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return None


class ConditionEvaluator:
    """Evaluate validated conditions against a normalized event context."""

    def __init__(self) -> None:
        self._memory_cooldowns: dict[tuple[int, int, str], float] = {}

    @staticmethod
    def _text(text: Any) -> str:
        return str(text or "")[:_MAX_INPUT]

    def _matches_text(self, text: str, expected: str, match: str) -> bool:
        text = self._text(text)
        if match == "exact":
            return text.lower() == expected.lower()
        if match == "starts_with":
            return text.lower().startswith(expected.lower())
        if match == "regex":
            compiled = _compiled(expected)
            return bool(compiled and compiled.search(text))
        return expected.lower() in text.lower()

    @staticmethod
    def _source(ctx: WorkflowContext) -> dict[str, Any]:
        return ctx.alert or ctx.event or {}

    async def evaluate(
        self,
        conditions: list[dict[str, Any]],
        ctx: WorkflowContext,
        *,
        workflow_id: int | None = None,
        guild_id: int | None = None,
        cooldown_checker: Any = None,
    ) -> Evaluation:
        """Return structured results; evaluation stops at the first failure."""

        evaluation = Evaluation()
        guild_id = guild_id if guild_id is not None else ctx.guild.id
        for condition in conditions:
            kind = condition.get("type", "")
            negate = bool(condition.get("negate", False))
            base, detail = await self._base(
                kind, condition, ctx, workflow_id, guild_id, cooldown_checker, negate
            )
            passed = base != negate
            evaluation.results.append(
                ConditionResult(kind, passed, negate, detail)
            )
            if not passed:
                break
        return evaluation

    async def _base(
        self,
        kind: str,
        condition: dict[str, Any],
        ctx: WorkflowContext,
        workflow_id: int | None,
        guild_id: int,
        cooldown_checker: Any,
        negate: bool,
    ) -> tuple[bool, str]:
        if kind == "account_age_lt":
            created = getattr(ctx.member, "created_at", None)
            if created is None:
                return False, "no account timestamp"
            age = (
                datetime.datetime.now(datetime.timezone.utc) - created
            ).total_seconds() / 86400
            return age < int(condition["days"]), f"age={age:.2f}d"

        if kind == "contains_link":
            return bool(_LINK_REGEX.search(self._text(ctx.content()))), "content"

        if kind == "contains_text":
            matched = self._matches_text(
                ctx.content(),
                str(condition["text"]),
                str(condition.get("match", "contains")),
            )
            return matched, "content"

        if kind == "has_role":
            roles = getattr(ctx.member, "roles", []) or []
            return any(
                getattr(role, "id", None) == condition["role_id"] for role in roles
            ), "roles"

        if kind == "channel_in":
            channel_id = getattr(ctx.channel, "id", None)
            return channel_id in set(condition.get("channel_ids") or []), "channel"

        if kind == "cooldown_sec":
            return await self._cooldown(
                condition, ctx, workflow_id, guild_id, cooldown_checker, negate
            )

        if kind == "is_bot":
            user = ctx.user
            return bool(getattr(user, "bot", False)) == bool(condition["value"]), "user"

        if kind == "emoji_is":
            return ctx.emoji == condition.get("emoji"), "emoji"

        if kind == "reaction_count_gte":
            return ctx.reaction_count >= int(condition["count"]), "reaction count"

        if kind == "not_self_react":
            if not condition.get("enabled", True):
                return True, "disabled"
            reactor = getattr(ctx.payload, "user_id", None)
            if reactor is None:
                reactor = ctx.extra.get("user_id")
            author = getattr(ctx.message.author, "id", None) if ctx.message else None
            return author is not None and reactor is not None and int(author) != int(reactor), "reactor"

        if kind == "safety_source":
            source = str(self._source(ctx).get("source", ""))
            return source == str(condition["source"]), "source"

        if kind == "safety_module":
            module = str(self._source(ctx).get("module", ""))
            return module == str(condition["module"]), "module"

        if kind == "moderation_action":
            event = self._source(ctx)
            action = str(event.get("action_type") or event.get("action") or "")
            return action == str(condition["action"]), "action"

        logger.warning("Unknown workflow condition type %s", kind)
        return False, "unknown condition"

    async def _cooldown(
        self,
        condition: dict[str, Any],
        ctx: WorkflowContext,
        workflow_id: int | None,
        guild_id: int,
        checker: Any,
        negate: bool,
    ) -> tuple[bool, str]:
        scope = str(condition.get("scope", "user"))
        if scope == "user":
            scope_id = ctx.user_id or 0
        elif scope == "guild":
            scope_id = guild_id
        else:
            scope_id = 0
        key = f"cooldown:{scope}:{scope_id}"
        seconds = int(condition["seconds"])

        if checker is not None:
            consume = not negate  # a negated cooldown is a pure observation
            try:
                ready = checker(workflow_id, guild_id, key, seconds, consume=consume)
            except TypeError:
                ready = checker(workflow_id, guild_id, key, seconds)
            if hasattr(ready, "__await__"):
                ready = await ready
            return bool(ready), "persisted cooldown"

        # Offline fallback for pools that are not available (tests/startup).
        now = time.monotonic()
        memory_key = (guild_id, workflow_id or 0, key)
        last = self._memory_cooldowns.get(memory_key, 0.0)
        if now - last >= seconds:
            if not negate:
                self._memory_cooldowns[memory_key] = now
                if len(self._memory_cooldowns) > 10000:
                    cutoff = now - _COOLDOWN_TTL
                    self._memory_cooldowns = {
                        k: v for k, v in self._memory_cooldowns.items() if v >= cutoff
                    }
            return True, "memory cooldown"
        return False, "memory cooldown"
