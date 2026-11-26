"""Focused application services shared by commands, listeners and workflows.

Services own database access for one domain and never import cogs. Command and
event modules construct them from the bot's pool (and entitlement service), so
business rules have a single implementation.

The ``get_*`` helpers attach one instance per bot so cache invalidation from a
command is immediately visible to event listeners.
"""

from __future__ import annotations

from typing import Any

from .logs import LogService
from .moderation import ModerationService
from .protection import ProtectionService
from .scheduler import SchedulerService
from .tickets import TicketService

__all__ = [
    "LogService",
    "ModerationService",
    "ProtectionService",
    "SchedulerService",
    "TicketService",
    "get_logs",
    "get_moderation",
    "get_protection",
    "get_scheduler",
    "get_tickets",
]


def get_moderation(bot: Any) -> ModerationService:
    service = getattr(bot, "_zync_moderation", None)
    if service is None:
        service = ModerationService(getattr(bot, "db", None))
        bot._zync_moderation = service
    return service


def get_logs(bot: Any) -> LogService:
    service = getattr(bot, "_zync_logs", None)
    if service is None:
        service = LogService(getattr(bot, "db", None))
        bot._zync_logs = service
    return service


def get_protection(bot: Any) -> ProtectionService:
    service = getattr(bot, "_zync_protection", None)
    if service is None:
        service = ProtectionService(
            getattr(bot, "db", None), getattr(bot, "entitlements", None)
        )
        bot._zync_protection = service
    return service


def get_tickets(bot: Any) -> TicketService:
    service = getattr(bot, "_zync_tickets", None)
    if service is None:
        service = TicketService(getattr(bot, "db", None))
        bot._zync_tickets = service
    return service


def get_scheduler(bot: Any) -> SchedulerService:
    service = getattr(bot, "_zync_scheduler", None)
    if service is None:
        service = SchedulerService(bot)
        bot._zync_scheduler = service
    return service
