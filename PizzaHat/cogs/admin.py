import inspect
import io
import os
import sys
import textwrap
import traceback
from contextlib import redirect_stdout

import discord
from core.cog import Cog
from discord.ext import commands


def restart_bot():
    os.execv(sys.executable, ['python'] + sys.argv)


class Admin(Cog, emoji="👷‍♂️"):
    """Admin configuration commands."""
    def __init__(self, bot):
        self.bot = bot

    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def set(self, ctx):
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    @set.command(aliases=['log'])
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def logs(self, ctx, channel: discord.TextChannel):
        """
        Set a mod-log channel.
        To replace a log channel, simply run this command again.
        """

        try:
            await self.bot.db.execute("INSERT INTO modlogs (guild_id, channel_id) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET channel_id=$2", ctx.guild.id, channel.id)
            await ctx.send(f"{self.bot.yes} Mod-logs channel set to {channel}")

        except Exception as e:
            print(e)


    @commands.command(hidden=True)
    @commands.is_owner()
    async def restart(self, ctx):
        """Restarts the bot."""

        await ctx.message.add_reaction("✅")
        restart_bot()

    @commands.command(hidden=True)
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
        
    @commands.command(hidden=True)
    @commands.is_owner()
    async def unload(self, ctx, cog):
        """Unloads a cog."""
        
        try:
            await self.bot.unload_extension(cog)
            await ctx.send(f"{self.bot.yes} Cog unloaded")
        except Exception as e:
            print(e)


async def setup(bot):
    await bot.add_cog(Admin(bot))
