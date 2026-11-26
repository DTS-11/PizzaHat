"""Guild logging configuration backed by ``guild_config``."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

LOG_MODULES = (
    "all",
    "automod",
    "guild",
    "integrations",
    "invites",
    "joins",
    "member",
    "messages",
    "mod",
    "roles",
    "voice",
)


class LogService:
    """Read and update the shared per-guild log channel/module settings."""

    def __init__(self, pool: Any | None) -> None:
        self.db = pool
        self._cache: dict[int, dict[str, Any]] = {}

    def invalidate(self, guild_id: int | None = None) -> None:
        if guild_id is None:
            self._cache.clear()
        else:
            self._cache.pop(guild_id, None)

    async def get(self, guild_id: int) -> dict[str, Any]:
        if guild_id in self._cache:
            return deepcopy(self._cache[guild_id])

        config: dict[str, Any] = {
            "guild_id": guild_id,
            "log_channel_id": None,
            "log_modules": ["all"],
        }
        if self.db is not None:
            row = await self.db.fetchrow(
                "SELECT guild_id, log_channel_id, log_modules FROM guild_config "
                "WHERE guild_id=$1",
                guild_id,
            )
            if row is not None:
                config["log_channel_id"] = row["log_channel_id"]
                config["log_modules"] = list(row["log_modules"] or ["all"])

        self._cache[guild_id] = deepcopy(config)
        return config

    async def get_channel_id(self, guild_id: int) -> int | None:
        return (await self.get(guild_id))["log_channel_id"]

    async def get_modules(self, guild_id: int) -> list[str]:
        return list((await self.get(guild_id))["log_modules"])

    async def set_channel(
        self,
        guild_id: int,
        channel_id: int,
        *,
        modules: list[str] | None = None,
    ) -> dict[str, Any]:
        if self.db is not None:
            if modules is None:
                await self.db.execute(
                    """INSERT INTO guild_config (guild_id, log_channel_id)
                       VALUES ($1, $2)
                       ON CONFLICT (guild_id) DO UPDATE
                       SET log_channel_id=EXCLUDED.log_channel_id,
                           updated_at=NOW()""",
                    guild_id,
                    channel_id,
                )
            else:
                await self.db.execute(
                    """INSERT INTO guild_config (guild_id, log_channel_id, log_modules)
                       VALUES ($1, $2, $3::text[])
                       ON CONFLICT (guild_id) DO UPDATE
                       SET log_channel_id=EXCLUDED.log_channel_id,
                           log_modules=EXCLUDED.log_modules,
                           updated_at=NOW()""",
                    guild_id,
                    channel_id,
                    list(modules),
                )
        self.invalidate(guild_id)
        config = await self.get(guild_id)
        config["log_channel_id"] = channel_id
        if modules is not None:
            config["log_modules"] = list(modules)
        self._cache[guild_id] = deepcopy(config)
        return config

    async def set_modules(
        self, guild_id: int, modules: list[str] | str, *, validate: bool = True
    ) -> tuple[list[str], list[str]]:
        """Replace the enabled modules; return ``(enabled, disabled)``."""

        if isinstance(modules, str):
            selected = modules.replace(",", " ").split()
        else:
            selected = list(modules)

        normalized = [module.lower() for module in selected if module]
        if validate:
            for module in normalized:
                if module not in LOG_MODULES:
                    raise ValueError(f"Invalid logging module: {module}")
        normalized = list(dict.fromkeys(normalized))
        if "all" in normalized:
            normalized = ["all"]

        previous = set(await self.get_modules(guild_id))
        removed = sorted(previous - set(normalized)) if "all" not in previous else []

        if self.db is not None:
            await self.db.execute(
                """INSERT INTO guild_config (guild_id, log_modules)
                   VALUES ($1, $2::text[])
                   ON CONFLICT (guild_id) DO UPDATE
                   SET log_modules=EXCLUDED.log_modules, updated_at=NOW()""",
                guild_id,
                normalized,
            )
        self.invalidate(guild_id)
        config = await self.get(guild_id)
        config["log_modules"] = list(normalized)
        self._cache[guild_id] = deepcopy(config)
        return normalized, removed
