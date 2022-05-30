import discord
from discord.ext import commands
import io
import os
import sys
import inspect
import textwrap
import traceback
from contextlib import redirect_stdout

from core.cog import Cog

def restart_bot():
    os.execv(sys.executable, ['python'] + sys.argv)


class Dev(Cog, emoji=808407479687053403):
    """Developer Only Commands"""
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.is_owner()
    async def restart(self, ctx):
        """Restarts the bot."""
        await ctx.message.add_reaction("✅")
        restart_bot()

    @commands.command()
    @commands.is_owner()
    async def eval(self, ctx, *, body):
        """Eval command."""
        env = {
            'ctx': ctx,
            'bot': self.bot,
            'client': self.bot,
            'db': self.bot.db,
            'channel': ctx.channel,
            'author': ctx.author,
            'guild': ctx.guild,
            'message': ctx.message,
            'source': inspect.getsource
        }

        def cleanup_code(content):
            # remove ```py\n```
            if content.startswith('```') and content.endswith('```'):
                return '\n'.join(content.split('\n')[1:-1])

                # remove `foo`
            return content.strip('` \n')

        env.update(globals())

        body = cleanup_code(body)
        stdout = io.StringIO()

        to_compile = f'async def func():\n{textwrap.indent(body, "    ")}'

        def paginate(text: str):
            '''Simple generator that paginates text.'''
            last = 0
            pages = []
            for curr in range(0, len(text)):
                if curr % 1980 == 0:
                    pages.append(text[last:curr])
                    last = curr
                    appd_index = curr
            if appd_index != len(text)-1:
                pages.append(text[last:curr])
            return list(filter(lambda a: a != '', pages))
        
        color = 0x2e3135

        try:
            exec(to_compile, env)
        except Exception as e:
            embed=discord.Embed(
                title='Error',
                description=f'```py\n{e.__class__.__name__}: {e}\n```',
                color=color
            )
            await ctx.send(embed=embed)

        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception:
            value = stdout.getvalue()
            embed=discord.Embed(
                title='Error',
                description=f'```py\n{value}{traceback.format_exc()}\n```',
                color=color
            )
            await ctx.send(embed=embed)
        else:
            value = stdout.getvalue()
            if ret is None:
                if value:
                    try:
                        embed=discord.Embed(
                            description=f'```py\n{value}\n```',
                                color=color
                            )
                        await ctx.send(embed=embed)
                    except:
                        paginated_text = paginate(value)
                        for page in paginated_text:
                            if page == paginated_text[-1]:
                                embed=discord.Embed(
                                    description=f'```py\n{page}\n```',
                                    color=color
                                    )
                                await ctx.send(embed=embed)
                                break
                            embed=discord.Embed(
                                description=f'```py\n{page}\n```',
                                color=color
                                )
                            await ctx.send(embed=embed)
            else:
                try:
                    embed=discord.Embed(
                        description=f'```py\n{value}{ret}\n```',
                        color=color
                        )
                    await ctx.send(embed=embed)
                except:
                    paginated_text = paginate(f"{value}{ret}")
                    for page in paginated_text:
                        if page == paginated_text[-1]:
                            embed=discord.Embed(
                                description=f'```py\n{page}\n```',
                                color=color
                                )
                            await ctx.send(embed=embed)
                            break
                        embed=discord.Embed(
                            description=f'```py\n{page}\n```',
                            color=color
                        )
                        await ctx.send(embed=embed)
                        
    @commands.command()
    @commands.is_owner()
    async def load(self, ctx, cog):
        try:
            await self.bot.load_extension(cog)
            await ctx.send(f"{self.bot.yes} Cog loaded")
        except Exception as e:
            print(e)
        
    @commands.command()
    @commands.is_owner()
    async def unload(self, ctx, cog):
        try:
            await self.bot.unload_extension(cog)
            await ctx.send(f"{self.bot.yes} Cog unloaded")
        except Exception as e:
            print(e)

    @commands.command()
    @commands.is_owner()
    async def reload(self, ctx, cog):
        try:
            await self.bot.reload_extension(cog)
            await ctx.send(f"{self.bot.yes} Cog reloaded")
        except Exception as e:
            print(e)


async def setup(bot):
    await bot.add_cog(Dev(bot))
