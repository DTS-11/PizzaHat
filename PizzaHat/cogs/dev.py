import inspect
import io
import os
import textwrap
import time
import traceback
from contextlib import redirect_stdout
from typing import TYPE_CHECKING, Awaitable, Callable, Union

import discord
from core.bot import INITIAL_EXTENSIONS, PizzaHat
from core.cog import Cog
from discord.ext import commands
from discord.ext.commands import Context
from utils.formats import TabularData, plural

if TYPE_CHECKING:
    from asyncpg import Record


class Dev(Cog, emoji=833297795761831956):
    """Developer commands."""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot

    def cleanup_code(self, content: str) -> str:
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith("```") and content.endswith("```"):
            return "\n".join(content.split("\n")[1:-1])

        else:
            return content

    @commands.command(name="eval", hidden=True)
    @commands.is_owner()
    async def _eval(self, ctx: Context, *, body: str):
        """Eval command."""

        env = {
            "ctx": ctx,
            "bot": self.bot,
            "client": self.bot,
            "db": self.bot.db,  # type: ignore
            "channel": ctx.channel,
            "author": ctx.author,
            "guild": ctx.guild,
            "message": ctx.message,
            "source": inspect.getsource,
        }

        env.update(globals())

        body = self.cleanup_code(body)
        stdout = io.StringIO()

        to_compile = f'async def func():\n{textwrap.indent(body, "    ")}'

        def paginate(text: str):
            """Simple generator that paginates text."""
            last = 0
            pages = []
            for curr in range(0, len(text)):
                if curr % 1980 == 0:
                    pages.append(text[last:curr])
                    last = curr
                    appd_index = curr
            if appd_index != len(text) - 1:  # type: ignore
                pages.append(text[last:curr])  # type: ignore
            return list(filter(lambda a: a != "", pages))

        color = self.bot.color

        try:
            exec(to_compile, env)

        except Exception as e:
            embed = discord.Embed(
                title="Error",
                description=f"```py\n{e.__class__.__name__}: {e}\n```",
                color=color,
            )
            await ctx.send(embed=embed)

        func = env["func"]

        try:
            with redirect_stdout(stdout):
                ret = await func()

        except Exception:
            value = stdout.getvalue()
            embed = discord.Embed(
                title="Error",
                description=f"```py\n{value}{traceback.format_exc()}\n```",
                color=color,
            )
            await ctx.send(embed=embed)

        else:
            value = stdout.getvalue()
            if ret is None:
                if value:
                    try:
                        embed = discord.Embed(
                            description=f"```py\n{value}\n```", color=color
                        )

                        await ctx.send(embed=embed)

                    except:
                        paginated_text = paginate(value)

                        for page in paginated_text:
                            if page == paginated_text[-1]:
                                embed = discord.Embed(
                                    description=f"```py\n{page}\n```", color=color
                                )
                                await ctx.send(embed=embed)
                                break

                            embed = discord.Embed(
                                description=f"```py\n{page}\n```", color=color
                            )

                            await ctx.send(embed=embed)
            else:
                try:
                    embed = discord.Embed(
                        description=f"```py\n{value}{ret}\n```", color=color
                    )
                    await ctx.send(embed=embed)

                except:
                    paginated_text = paginate(f"{value}{ret}")

                    for page in paginated_text:
                        if page == paginated_text[-1]:
                            embed = discord.Embed(
                                description=f"```py\n{page}\n```", color=color
                            )
                            await ctx.send(embed=embed)
                            break

                        embed = discord.Embed(
                            description=f"```py\n{page}\n```", color=color
                        )

                        await ctx.send(embed=embed)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def sql(self, ctx: Context, *, query: str):
        """Run some SQL."""

        query = self.cleanup_code(query)

        is_multistatement = query.count(";") > 1
        strategy: Callable[[str], Union[Awaitable[list[Record]], Awaitable[str]]]

        if is_multistatement:
            # fetch does not support multiple statements
            strategy = self.bot.db.execute  # type: ignore

        else:
            strategy = self.bot.db.fetch  # type: ignore

        try:
            start = time.perf_counter()
            results = await strategy(query)
            dt = (time.perf_counter() - start) * 1000.0

        except Exception:
            return await ctx.send(f"```py\n{traceback.format_exc()}\n```")

        rows = len(results)

        if isinstance(results, str) or rows == 0:
            return await ctx.send(f"`{dt:.2f}ms: {results}`")

        headers = list(results[0].keys())
        table = TabularData()
        table.set_columns(headers)
        table.add_rows(list(r.values()) for r in results)
        render = table.render()

        fmt = f"```\n{render}\n```\n*Returned {plural(rows):row} in {dt:.2f}ms*"
        if len(fmt) > 2000:
            fp = io.BytesIO(fmt.encode("utf-8"))
            await ctx.send("Too many results...", file=discord.File(fp, "results.txt"))

        else:
            await ctx.send(fmt)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def botlogs(self, ctx: Context):
        """Command to show bot logs (bot.log) file in discord itself."""

        f = open("bot.log", "r")
        await ctx.send(f"```ruby\n{f.read()}\n```")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def reloadall(self, ctx: Context):
        """Quick way to reload all cogs at once."""

        for cog in INITIAL_EXTENSIONS:
            await self.bot.reload_extension(cog)
            print(cog, "reloaded")

        await ctx.send("Reloaded all cogs!")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def update_config(self, ctx: Context):
        """Update the config file by uploading the attachment."""

        if not ctx.message.attachments:
            return await ctx.send(f"{self.bot.no} No file attached.")

        attachment = ctx.message.attachments[0]
        file_path = os.path.join(os.getcwd(), "utils/config.py")

        if not attachment.filename.endswith(".py"):
            return await ctx.send(f"{self.bot.no} Not a Python config file.")

        await attachment.save(file_path) # type: ignore
        await ctx.send(f"{self.bot.yes} Config file updated successfully!")


async def setup(bot):
    await bot.add_cog(Dev(bot))
