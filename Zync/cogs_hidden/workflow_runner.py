"""Extension entry point for the workflow runner.

The implementation lives in the ``workflows`` package; this module keeps the
extension path and Cog name stable for ``core.bot``.
"""

from __future__ import annotations

from core.bot import Zync
from workflows.runner import WorkflowRunner

__all__ = ["WorkflowRunner", "setup"]


async def setup(bot: Zync) -> None:
    await bot.add_cog(WorkflowRunner(bot))
