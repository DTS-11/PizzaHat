"""Workflow execution engine.

Workflows are cached per guild and guarded by a lock per definition. Runs are
recorded with an event-key idempotency check, cooldowns/schedule slots are
persisted, actions execute sequentially with bounded retry for HTTP 429, and
recursion is capped both by depth and by a per-event seen-workflow set.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord

from workflows.actions import ActionRegistry, ActionResult, build_variables
from workflows.conditions import ConditionEvaluator
from workflows.repository import WorkflowRepository
from workflows.triggers import TRIGGERS, TriggerRegistry, WorkflowContext

logger = logging.getLogger("bot")

MAX_DEPTH = 3
_DEDUPE_WINDOW = 300.0
_MAX_RETRIES = 3
_MAX_RETRY_DELAY = 5.0
_SCHEDULE_NAMESPACE = uuid.UUID("19f6d3ba-5a3f-4b51-a3bc-2e4b98ad0a11")

_ACTIVE_CONTEXT: ContextVar[WorkflowContext | None] = ContextVar(
    "zync_workflow_context", default=None
)


def active_context() -> WorkflowContext | None:
    """Return the workflow context of the current task, if any."""

    return _ACTIVE_CONTEXT.get()


@dataclass
class WorkflowRunOutcome:
    run_id: str | None
    workflow_id: int
    status: str
    action_results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "action_results": self.action_results,
            "error": self.error,
        }


class WorkflowEngine:
    """Loads, evaluates and executes workflows for Discord events."""

    def __init__(
        self,
        bot: Any,
        repository: WorkflowRepository | None = None,
        *,
        triggers: TriggerRegistry | None = None,
        conditions: ConditionEvaluator | None = None,
        actions: ActionRegistry | None = None,
    ) -> None:
        self.bot = bot
        self.repo = repository or WorkflowRepository(getattr(bot, "db", None))
        self.triggers = triggers or TRIGGERS
        self.conditions = conditions or ConditionEvaluator()
        self.actions = actions or ActionRegistry(bot, self.repo)
        self._cache: dict[int, list[dict[str, Any]]] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._seen_events: dict[str, float] = {}
        self._active_runs: dict[str, tuple[asyncio.Task[Any], str | None]] = {}

    # ── cache and lifecycle ──────────────────────────────────────────────────

    def clear_cache(self, guild_id: int | None = None) -> None:
        """Invalidate in-memory definitions after a management write."""

        if guild_id is None:
            self._cache.clear()
            self._locks.clear()
            self._seen_events.clear()
        else:
            old_ids = {item["id"] for item in self._cache.get(guild_id, [])}
            self._cache.pop(guild_id, None)
            self._locks = {
                key: value for key, value in self._locks.items() if key not in old_ids
            }
            self._seen_events = {
                key: value
                for key, value in self._seen_events.items()
                if not key.startswith(f"{guild_id}:")
            }

    async def workflows_for(self, guild_id: int) -> list[dict[str, Any]]:
        """Return validated enabled definitions, cached per guild."""

        cached = self._cache.get(guild_id)
        if cached is not None:
            return cached
        definitions = await self.repo.list_enabled(guild_id)
        self._cache[guild_id] = definitions
        return definitions

    def _workflow_lock(self, workflow_id: int) -> asyncio.Lock:
        lock = self._locks.get(workflow_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[workflow_id] = lock
        return lock

    def cancel_run(self, run_key: str) -> bool:
        """Explicitly cancel an in-flight run by its idempotency key."""

        entry = self._active_runs.get(run_key)
        if entry is None:
            return False
        entry[0].cancel()
        return True

    def cancel_guild_runs(self, guild_id: int) -> int:
        prefix = f"{guild_id}:"
        keys = [key for key in self._active_runs if key.startswith(prefix)]
        for key in keys:
            self.cancel_run(key)
        return len(keys)

    # ── dispatch ─────────────────────────────────────────────────────────────

    async def dispatch(
        self,
        ctx: WorkflowContext,
        *,
        parent: WorkflowContext | None = None,
        event_key_override: str | None = None,
    ) -> list[WorkflowRunOutcome]:
        """Run all matching workflows for one normalized event."""

        if parent is not None:
            ctx.depth = parent.depth + 1
            ctx.seen_workflows = parent.seen_workflows
        elif (current := _ACTIVE_CONTEXT.get()) is not None:
            ctx.depth = current.depth + 1
            ctx.seen_workflows = current.seen_workflows
        else:
            ctx.seen_workflows = set()
        if ctx.depth > MAX_DEPTH:
            logger.debug("Workflow recursion limit reached for %s", ctx.trigger_type)
            return []

        event_key = event_key_override or self.triggers.event_key(ctx)
        ctx.event_key = event_key
        token = _ACTIVE_CONTEXT.set(ctx)
        outcomes: list[WorkflowRunOutcome] = []
        try:
            definitions = await self.workflows_for(ctx.guild.id)
            for workflow in definitions:
                workflow_id = int(workflow["id"])
                if workflow_id in ctx.seen_workflows:
                    continue
                if not self.triggers.matches(workflow, ctx):
                    continue
                run_key = f"{ctx.guild.id}:{workflow_id}:{event_key}"
                async with self._workflow_lock(workflow_id):
                    evaluation = await self.conditions.evaluate(
                        workflow["conditions"],
                        ctx,
                        workflow_id=workflow_id,
                        guild_id=ctx.guild.id,
                        cooldown_checker=(
                            self.repo.cooldown_ready if self.repo.available else None
                        ),
                    )
                    if not evaluation.passed:
                        continue
                    now = time.monotonic()
                    if run_key in self._seen_events and now - self._seen_events[run_key] < _DEDUPE_WINDOW:
                        continue

                    run_id: str | None = None
                    if self.repo.available:
                        run_id = await self.repo.record_run_start(
                            ctx.guild.id,
                            workflow_id,
                            ctx.trigger_type,
                            run_key,
                            evaluation.as_dicts(),
                        )
                        if run_id is None:  # persisted idempotency
                            continue
                    self._seen_events[run_key] = now
                    ctx.seen_workflows.add(workflow_id)

                    task = asyncio.current_task()
                    if task is not None:
                        self._active_runs[run_key] = (task, run_id)
                    try:
                        variables = build_variables(ctx, workflow["trigger_config"])
                        results = await self._execute_actions(workflow, ctx, variables)
                        status = "completed"
                        error = None
                    except asyncio.CancelledError:
                        await self.repo.finish_run(
                            run_id or "", "cancelled", [], "cancelled"
                        )
                        raise
                    except Exception as exc:
                        status = "failed"
                        error = f"{type(exc).__name__}: {exc}"[:2000]
                        logger.warning(
                            "Workflow %s failed: %s", workflow_id, error
                        )
                        await self.repo.finish_run(
                            run_id or "", "failed", [], error
                        )
                        results = []
                    else:
                        await self.repo.finish_run(
                            run_id or "", status, results, error
                        )
                    finally:
                        self._active_runs.pop(run_key, None)

                    outcomes.append(
                        WorkflowRunOutcome(run_id, workflow_id, status, results, error)
                    )
            return outcomes
        finally:
            _ACTIVE_CONTEXT.reset(token)

    async def _execute_actions(
        self,
        workflow: dict[str, Any],
        ctx: WorkflowContext,
        variables: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Execute actions in order with bounded retry and no artificial sleeps."""

        results: list[dict[str, Any]] = []
        for index, action in enumerate(workflow["actions"]):
            kind = str(action.get("type", "unknown"))
            result: ActionResult | None = None
            for attempt in range(_MAX_RETRIES):
                try:
                    result = await self.actions.execute(
                        action, ctx, variables, workflow=workflow, index=index
                    )
                    break
                except asyncio.CancelledError:
                    raise
                except discord.HTTPException as exc:
                    if exc.status == 429 and attempt + 1 < _MAX_RETRIES:
                        retry = float(getattr(exc, "retry_after", 1.0) or 1.0)
                        await asyncio.sleep(min(max(retry, 0.25), _MAX_RETRY_DELAY))
                        continue
                    result = ActionResult(
                        index, kind, "failed", f"{type(exc).__name__}: {exc}"
                    )
                    break
                except Exception as exc:
                    result = ActionResult(
                        index, kind, "failed", f"{type(exc).__name__}: {exc}"
                    )
                    break
            results.append(
                (result or ActionResult(index, kind, "failed", "no result")).to_dict()
            )
        return results

    async def dispatch_custom(
        self, name: str, guild: discord.Guild, payload: Any = None
    ) -> list[WorkflowRunOutcome]:
        """Adapter for safely registered custom events."""

        ctx = await self.triggers.build_custom_context(name, guild, payload, bot=self.bot)
        if ctx is None:
            return []
        return await self.dispatch(ctx)

    # ── schedules ────────────────────────────────────────────────────────────

    @staticmethod
    def next_schedule(
        config: dict[str, Any], *, now: datetime.datetime | None = None
    ) -> tuple[datetime.datetime, str]:
        """Return the next UTC run time and its stable slot identifier."""

        now = now or datetime.datetime.now(datetime.timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=datetime.timezone.utc)
        if config.get("frequency") == "interval":
            step = max(1, int(config["interval_minutes"])) * 60
            slot = int(now.timestamp()) // step + 1
            return (
                datetime.datetime.fromtimestamp(slot * step, datetime.timezone.utc),
                f"interval:{slot}",
            )
        try:
            zone = ZoneInfo(str(config.get("timezone", "UTC")))
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            zone = datetime.timezone.utc
        local = now.astimezone(zone)
        target = local.replace(
            hour=int(config.get("hour", 0)),
            minute=int(config.get("minute", 0)),
            second=0,
            microsecond=0,
        )
        if target <= local:
            target += datetime.timedelta(days=1)
        return target.astimezone(datetime.timezone.utc), target.strftime("%Y-%m-%d")

    async def ensure_schedules(self, guild_id: int) -> None:
        """Create durable task rows so schedule slots survive restarts."""

        if not self.repo.available:
            return
        for workflow in await self.workflows_for(guild_id):
            if workflow["trigger_type"] != "schedule":
                continue
            config = workflow["trigger_config"]
            run_at, slot = self.next_schedule(config)
            definition_id = workflow.get("definition_id") or str(uuid.uuid4())
            task_id = str(
                uuid.uuid5(
                    _SCHEDULE_NAMESPACE,
                    f"schedule:{guild_id}:{definition_id}",
                )
            )
            payload = {
                "workflow_id": workflow["id"],
                "definition_id": definition_id,
                "slot": slot,
                "timezone": config.get("timezone", "UTC"),
            }
            existing = await self.repo.get_task(task_id)
            if existing is None:
                await self.repo.create_task(
                    guild_id, "workflow_schedule", payload, run_at, task_id=task_id
                )
            elif existing["status"] in ("done", "cancelled", "failed"):
                await self.repo.reactivate_task(task_id, payload, run_at)
            state = await self.repo.get_state(int(workflow["id"]), guild_id, "schedule")
            if state is None:
                await self.repo.set_state(
                    int(workflow["id"]),
                    guild_id,
                    "schedule",
                    run_at,
                    {"kind": "schedule", "slot": slot},
                )

    async def tick_schedules(self) -> list[WorkflowRunOutcome]:
        """Claim and execute due schedule tasks exactly once per slot."""

        if not self.repo.available:
            return []
        await self.repo.recover_stale_tasks()
        tasks = await self.repo.claim_due_tasks(limit=10)
        outcomes: list[WorkflowRunOutcome] = []
        for task in tasks:
            task_id = task["task_id"]
            guild_id = int(task["guild_id"])
            payload = task["payload"]
            if task["kind"] != "workflow_schedule":
                await self.repo.finish_task(task_id, "done")
                continue
            workflow_id = int(payload.get("workflow_id") or 0)
            workflow = await self.repo.get(guild_id, workflow_id)
            guild = self.bot.get_guild(guild_id)
            if workflow is None or not workflow.get("enabled") or guild is None:
                await self.repo.finish_task(task_id, "done")
                continue
            config = workflow["trigger_config"]
            next_run, next_slot = self.next_schedule(config)
            state = await self.repo.get_state(workflow_id, guild_id, "schedule")
            claimed = state is None or await self.repo.claim_state(
                workflow_id, guild_id, "schedule"
            )
            if not claimed:
                await self.repo.finish_task(task_id, "pending", next_run)
                continue
            slot = str(payload.get("slot") or "schedule")
            ctx = WorkflowContext.from_schedule(
                guild, slot=slot, timezone=str(config.get("timezone", "UTC"))
            )
            try:
                outcomes.extend(
                    await self.dispatch(
                        ctx,
                        event_key_override=(
                            f"schedule:{workflow.get('definition_id') or workflow_id}:{slot}"
                        ),
                    )
                )
            except asyncio.CancelledError:
                await self.repo.set_state(
                    workflow_id, guild_id, "schedule", next_run,
                    {"kind": "schedule", "slot": next_slot},
                )
                await self.repo.finish_task(task_id, "pending", next_run)
                raise
            except Exception as exc:
                logger.warning("Scheduled workflow %s failed: %s", workflow_id, exc)
            finally:
                await self.repo.set_state(
                    workflow_id,
                    guild_id,
                    "schedule",
                    next_run,
                    {"kind": "schedule", "slot": next_slot},
                )
                await self.repo.finish_task(task_id, "pending", next_run)
        return outcomes
