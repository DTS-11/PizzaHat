import discord
from discord.ext import commands
import yarl
import asyncio

from core.cog import Cog

# credits to R.Danny:
# https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/emoji.py
class EmojiURL:
    def __init__(self, *, animated: bool, url: str):
        self.url: str = url
        self.animated: bool = animated

    @classmethod
    async def convert(cls, ctx, argument):
        try:
            partial = await commands.PartialEmojiConverter().convert(ctx, argument)
        except commands.BadArgument:
            try:
                url = yarl.URL(argument)
                if url.scheme not in ('http', 'https'):
                    raise RuntimeError
                path = url.path.lower()
                if not path.endswith(('.png', '.jpeg', '.jpg', '.gif')):
                    raise RuntimeError
                return cls(animated=url.path.endswith('.gif'), url=argument)
            except Exception:
                raise commands.BadArgument('Not a valid or supported emoji URL.') from None
        else:
            return cls(animated=partial.animated, url=str(partial.url))

class Emoji(Cog, emoji="😀"):
    """Emoji management commands."""
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="emoji")
    @commands.guild_only()
    @commands.has_permissions(manage_emojis=True)
    async def _emoji(self, ctx):
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    @_emoji.command()
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(manage_emojis=True)
    async def create(self, ctx, emoji: EmojiURL, name):
        """Creates an emoji for the server under the given name."""
        emoji_count = sum(e.animated == emoji.animated for e in ctx.guild.emojis)
        if emoji_count >= ctx.guild.emoji_limit:
            return await ctx.send('There are no more emoji slots in this server.')

        async with self.bot.session.get(emoji.url) as resp:
            if resp.status >= 400:
                return await ctx.send('Could not fetch the image.')
            if int(resp.headers['Content-Length']) >= (256 * 1024):
                return await ctx.send('Image is too big.')
            data = await resp.read()
            coro = ctx.guild.create_custom_emoji(name=name, image=data, reason=f"Action done by {ctx.author}")
            try:
                created = await asyncio.wait_for(coro, timeout=10.0)
            except asyncio.TimeoutError:
                return await ctx.send('Sorry, the bot is rate limited or it took too long.')
            except discord.HTTPException as e:
                return await ctx.send(f'Failed to create emoji: {e}')
            else:
                return await ctx.send(f'Created {created}')    


async def setup(bot):
    await bot.add_cog(Emoji(bot))
