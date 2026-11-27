"""Owner-only development commands.

These are *prefix-only* commands and are never registered in the application
command tree. They provide read-only SQL inspection, a restricted evaluator,
extension reloading and bot log access for the bot owner.
"""

from __future__ import annotations

import asyncio
import builtins
import io
import re
import textwrap
import time
import traceback
from contextlib import redirect_stdout
from pathlib import Path
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands
from discord.ext.commands import Context

from core.bot import INITIAL_EXTENSIONS, SUB_EXTENSIONS, Lucent
from core.cog import Cog
from utils.embed import ctx_embed
from utils.formats import TabularData, plural

if TYPE_CHECKING:
    from asyncpg import Record


# No imports, file access, eval/exec/compile, or dunder traversal in the
# evaluator. The whole command remains owner-only regardless.
_EVAL_BUILTINS: dict[str, Any] = {
    name: getattr(builtins, name)
    for name in (
        "abs",
        "all",
        "any",
        "bin",
        "bool",
        "bytes",
        "chr",
        "dict",
        "dir",
        "enumerate",
        "filter",
        "float",
        "format",
        "frozenset",
        "getattr",
        "hasattr",
        "hex",
        "int",
        "isinstance",
        "issubclass",
        "iter",
        "len",
        "list",
        "map",
        "max",
        "min",
        "next",
        "object",
        "oct",
        "ord",
        "pow",
        "print",
        "range",
        "repr",
        "reversed",
        "round",
        "set",
        "slice",
        "sorted",
        "str",
        "sum",
        "tuple",
        "type",
        "zip",
    )
}
_EVAL_FORBIDDEN = re.compile(
    r"\b(?:import|__import__|open|eval|exec|compile|input|breakpoint)\b|__"
)

_READONLY_SQL_START = re.compile(r"\A(?:\s|--[^\n]*(?:\n|$))*([A-Za-z]+)")
_MUTATING_SQL = re.compile(
    r"\b(?:INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|"
    r"COPY|CALL|DO|VACUUM|REINDEX|SET|RESET|COMMENT|LOCK|REFRESH)\b",
    re.IGNORECASE,
)


def _cleanup_code(content: str) -> str:
    """Remove surrounding Markdown code fences."""
    content = content.strip()
    if content.startswith("```") and content.endswith("```"):
        lines = content.splitlines()
        return "\n".join(lines[1:-1])
    return content


def _paginate(text: str, size: int = 1900) -> list[str]:
    """Split text into Discord-safe chunks."""
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def _code_block(text: str, language: str = "py") -> str:
    """Render text as a code block, neutralising embedded fences."""
    safe = text.replace("```", "\u200b``")
    return f"```{language}\n{safe}\n```"


class Dev(Cog, emoji=1268856867585658981):
    """Developer commands (owner only, prefix only)."""

    def __init__(self, bot: Lucent):
        self.bot: Lucent = bot

    @commands.command(name="updatecodebase", hidden=True)
    @commands.is_owner()
    async def _updatecodebase(self, ctx: Context):
        """Update the bot."""
        process = await asyncio.create_subprocess_exec(
            "git",
            "pull",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        output = ((stdout or b"") + (stderr or b"")).decode(errors="replace").strip()

        await ctx.send(f"```bash\n{output[:1900]}\n```\nRestarting...")
        await self.bot.close()

    @commands.command(name="eval", hidden=True)
    @commands.is_owner()
    async def _eval(self, ctx: Context, *, body: str):
        """Evaluate a small expression with restricted builtins."""
        body = _cleanup_code(body)
        if _EVAL_FORBIDDEN.search(body):
            return await ctx.send(
                embed=await ctx_embed(
                    ctx,
                    title="Eval rejected",
                    description=(
                        "Imports, file access, nested evaluation and dunder access "
                        "are disabled in the evaluator."
                    ),
                )
            )

        env: dict[str, Any] = {
            "__builtins__": _EVAL_BUILTINS,
            "ctx": ctx,
            "bot": self.bot,
            "client": self.bot,
            "channel": ctx.channel,
            "author": ctx.author,
            "guild": ctx.guild,
            "message": ctx.message,
        }

        try:
            exec(
                compile(
                    f"async def _dev_eval():\n{textwrap.indent(body, '    ')}",
                    "<owner-eval>",
                    "exec",
                ),
                env,
            )
        except Exception as exc:
            return await ctx.send(
                embed=await ctx_embed(
                    ctx,
                    title="Error",
                    description=_code_block(f"{type(exc).__name__}: {exc}"),
                )
            )

        stdout = io.StringIO()
        try:
            with redirect_stdout(stdout):
                result = await env["_dev_eval"]()
        except Exception:
            return await ctx.send(
                embed=await ctx_embed(
                    ctx,
                    title="Error",
                    description=_code_block(stdout.getvalue() + traceback.format_exc()),
                )
            )

        output = stdout.getvalue()
        if result is not None:
            output = f"{output}{result!r}"
        if not output:
            return await ctx.send("Evaluated successfully (no output).")

        for page in _paginate(output):
            await ctx.send(embed=await ctx_embed(ctx, description=_code_block(page)))

    @commands.command(name="sql", hidden=True)
    @commands.is_owner()
    async def sql(self, ctx: Context, *, query: str):
        """Run a single read-only SQL query (SELECT/WITH/EXPLAIN)."""
        query = _cleanup_code(query).rstrip().rstrip(";")
        match = _READONLY_SQL_START.match(query)
        if match is None or match.group(1).upper() not in {"SELECT", "WITH", "EXPLAIN"}:
            return await ctx.send(
                "Only single SELECT, WITH, or EXPLAIN queries are allowed."
            )
        if ";" in query or _MUTATING_SQL.search(query):
            return await ctx.send(
                "Write statements and multiple statements are blocked."
            )

        if not self.bot.db:
            return await ctx.send("Database unavailable.")

        try:
            start = time.perf_counter()
            results: list[Record] = await self.bot.db.fetch(query)
            elapsed = (time.perf_counter() - start) * 1000.0
        except Exception:
            return await ctx.send(_code_block(traceback.format_exc()))

        if not results:
            return await ctx.send(f"`{elapsed:.2f}ms: no rows returned`")

        table = TabularData()
        table.set_columns(list(results[0].keys()))
        table.add_rows(list(record.values()) for record in results)
        rendered = (
            f"```\n{table.render()}\n```\n"
            f"*Returned {plural(len(results)):row} in {elapsed:.2f}ms*"
        )
        if len(rendered) > 2000:
            await ctx.send(
                "Too many results...",
                file=discord.File(
                    io.BytesIO(rendered.encode("utf-8")), filename="results.txt"
                ),
            )
        else:
            await ctx.send(rendered)

    @commands.command(name="botlogs", hidden=True)
    @commands.is_owner()
    async def botlogs(self, ctx: Context):
        """Send the tail of bot.log."""
        try:
            contents = Path("bot.log").read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return await ctx.send(f"Could not read bot.log: {exc}")

        tail = contents[-3500:]
        for page in _paginate(tail, 1900):
            await ctx.send(_code_block(page, language="text"))

    @commands.command(name="reloadall", hidden=True)
    @commands.is_owner()
    async def reloadall(self, ctx: Context):
        """Reload all cogs (owner only)."""
        failed: list[str] = []
        extensions = (*INITIAL_EXTENSIONS, *SUB_EXTENSIONS)
        if "jishaku" in self.bot.extensions:
            extensions += ("jishaku",)

        for extension in extensions:
            try:
                await self.bot.reload_extension(extension)
            except commands.ExtensionError as exc:
                failed.append(f"{extension}: {exc}")

        synced = await self.bot.sync_commands()
        if failed or not synced:
            details = "\n".join(failed) if failed else "Command sync failed."
            return await ctx.send(
                f"Reload finished with issues:\n```\n{details[:1500]}\n```"
            )
        await ctx.send("Reloaded all cogs!")


async def setup(bot: Lucent) -> None:
    await bot.add_cog(Dev(bot))
