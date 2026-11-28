"""Regression checks that setup interactions are acknowledged before DB work."""

from __future__ import annotations

import asyncio

import discord

from cogs.setup import Setup, ViewSetupView


class _Permissions:
    manage_guild = True


class _User:
    id = 1
    guild_permissions = _Permissions()


class _Guild:
    id = 2


class _Response:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    async def defer(self, **kwargs: object) -> None:
        self.log.append("defer")

    async def send_message(self, **kwargs: object) -> None:
        self.log.append("send_message")


class _Followup:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    async def send(self, **kwargs: object) -> None:
        self.log.append("send")


class _Interaction:
    def __init__(self, log: list[str]) -> None:
        self.log = log
        self.guild = _Guild()
        self.user = _User()
        self.response = _Response(log)
        self.followup = _Followup(log)

    async def edit_original_response(self, **kwargs: object) -> None:
        self.log.append("edit")


class _Bot:
    db = None
    can_read_message_content = False

    def get_cog(self, name: str) -> None:
        return None


def _stub_overview(cog: Setup, log: list[str]) -> None:
    async def overview(guild_id: int) -> discord.Embed:
        log.append("overview")
        return discord.Embed(title="Configuration")

    cog.overview_embed = overview  # type: ignore[method-assign]


def test_view_setup_defers_before_database_work() -> None:
    log: list[str] = []
    cog = Setup(_Bot())  # type: ignore[arg-type]
    _stub_overview(cog, log)

    asyncio.run(cog.view_setup.callback(cog, _Interaction(log)))

    assert log == ["defer", "overview", "send"]


def test_view_setup_refresh_defers_before_database_work() -> None:
    log: list[str] = []
    cog = Setup(_Bot())  # type: ignore[arg-type]
    _stub_overview(cog, log)
    view = ViewSetupView(cog, 2, 1)

    asyncio.run(ViewSetupView.refresh(view, _Interaction(log), None))  # type: ignore[arg-type]

    assert log == ["defer", "overview", "edit"]
