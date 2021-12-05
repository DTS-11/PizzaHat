import discord
from discord.ext import commands
import io
import inspect
import textwrap
import traceback
from contextlib import redirect_stdout
import sys
import os

class Dev(commands.Cog):
    """<:Developer:808407479687053403> Developer Only Commands"""
    def __init__(self,bot):
        self.bot = bot

    @commands.command(hidden=True, aliases=['logout'])
    @commands.is_owner()
    async def restart(self, ctx):
        """Restarts the bot."""
        msg = await ctx.send('Restarting bot...')
        exe = sys.executable
        os.execl(exe, exe, * sys.argv)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def eval(self, ctx, *, body):
        """Eval command."""
        env = {
            'ctx': ctx,
            'bot': self.bot,
            'client': self.bot,
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
                
        try:
            exec(to_compile, env)
        except Exception as e:
            embed=discord.Embed(
                title='Error',
                description=f'```py\n{e.__class__.__name__}: {e}\n```',
                color=0x2e3135
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
                color=0x2e3135
            )
            await ctx.send(embed=embed)
        else:
            value = stdout.getvalue()
            if ret is None:
                if value:
                    try:
                                                
                        embed=discord.Embed(
                            description=f'```py\n{value}\n```',
                                color=0x2e3135
                            )
                        await ctx.send(embed=embed)
                    except:
                        paginated_text = paginate(value)
                        for page in paginated_text:
                            if page == paginated_text[-1]:
                                embed=discord.Embed(
                                    description=f'```py\n{page}\n```',
                                    color=0x2e3135
                                    )
                                await ctx.send(embed=embed)
                                break
                            embed=discord.Embed(
                                description=f'```py\n{page}\n```',
                                color=0x2e3135
                                )
                            await ctx.send(embed=embed)
            else:
                try:
                    embed=discord.Embed(
                        description=f'```py\n{value}{ret}\n```',
                        color=0x2e3135
                        )
                    await ctx.send(embed=embed)
                except:
                    paginated_text = paginate(f"{value}{ret}")
                    for page in paginated_text:
                        if page == paginated_text[-1]:
                            embed=discord.Embed(
                                description=f'```py\n{page}\n```',
                                color=0x2e3135
                                )
                            await ctx.send(embed=embed)
                            break
                        embed=discord.Embed(
                            description=f'```py\n{page}\n```',
                            color=0x2e3135
                        )
                        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(Dev(bot))