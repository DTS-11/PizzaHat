import asyncio
from typing import Union

import discord
import requests
import yarl
from discord.ext import commands
from discord.ext.commands import Context
from PIL import Image

from core.bot import PizzaHat
from core.cog import Cog
from utils.embed import green_embed, normal_embed, red_embed
from utils.ui import Paginator

from .utility import format_date

COLORS = {
    (0, 0, 0): "⬛",
    (0, 0, 255): "🟦",
    (255, 0, 0): "🟥",
    (255, 255, 0): "🟨",
    # (190, 100, 80):  "🟫",
    (255, 165, 0): "🟧",
    # (160, 140, 210): "🟪",
    (255, 255, 255): "⬜",
    (0, 255, 0): "🟩",
}


def euclidean_distance(c1, c2) -> float:
    r1, g1, b1 = c1
    r2, g2, b2 = c2
    d = ((r2 - r1) ** 2 + (g2 - g1) ** 2 + (b2 - b1) ** 2) ** 0.5

    return d


def find_closest_emoji(color) -> str:
    c = sorted(list(COLORS), key=lambda k: euclidean_distance(color, k))
    return COLORS[c[0]]


def emojify_image(img, size=14) -> str:
    WIDTH, HEIGHT = (size, size)
    small_img = img.resize((WIDTH, HEIGHT), Image.NEAREST)

    emoji = ""
    small_img = small_img.load()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            emoji += find_closest_emoji(small_img[x, y])
        emoji += "\n"
    return emoji


# credits to R.Danny:
# https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/emoji.py
class EmojiURL:
    def __init__(self, *, animated: bool, url: str):
        self.url: str = url
        self.animated: bool = animated

    @classmethod
    async def convert(cls, ctx: Context, argument):
        try:
            partial = await commands.PartialEmojiConverter().convert(ctx, argument)
        except commands.BadArgument:
            try:
                url = yarl.URL(argument)
                if url.scheme not in ("http", "https"):
                    raise RuntimeError
                path = url.path.lower()
                if not path.endswith((".png", ".jpeg", ".jpg", ".gif")):
                    raise RuntimeError
                return cls(animated=url.path.endswith(".gif"), url=argument)
            except Exception:
                raise commands.BadArgument(
                    "Not a valid or supported emoji URL."
                ) from None
        else:
            return cls(animated=partial.animated, url=str(partial.url))


class Emojis(Cog, emoji=1268867324195246133):
    """Emoji management commands."""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot

    @commands.group(name="emoji")
    @commands.guild_only()
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def _emoji(self, ctx: Context):
        """Emoji management commands."""

        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    @_emoji.command()
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def create(self, ctx: Context, emoji: EmojiURL, name):
        """Creates an emoji."""

        if ctx.guild is not None:
            emoji_count = sum(e.animated == emoji.animated for e in ctx.guild.emojis)

            if emoji_count >= ctx.guild.emoji_limit:
                return await ctx.send(
                    embed=red_embed(
                        f"{self.bot.no} There are no more emoji slots in this server."
                    )
                )

            async with self.bot.session.get(emoji.url) as resp:
                if resp.status >= 400:
                    return await ctx.send(
                        embed=red_embed(f"{self.bot.no} Could not fetch the image.")
                    )

                if int(resp.headers["Content-Length"]) >= (256 * 1024):
                    return await ctx.send(
                        embed=red_embed(f"{self.bot.no} Image is too big.")
                    )

                data = await resp.read()
                coro = ctx.guild.create_custom_emoji(
                    name=name, image=data, reason=f"Action done by {ctx.author}"
                )

                try:
                    created = await asyncio.wait_for(coro, timeout=10.0)

                except asyncio.TimeoutError:
                    return await ctx.send(
                        embed=red_embed(
                            "Sorry, the bot is rate limited or it took too long."
                        )
                    )

                except discord.HTTPException as e:
                    return await ctx.send(
                        embed=red_embed(f"{self.bot.no} Failed to create emoji: {e}")
                    )

                else:
                    return await ctx.send(
                        embed=green_embed(f"{self.bot.yes} Created {created}")
                    )

    @_emoji.command()
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def delete(self, ctx: Context, emoji: discord.Emoji):
        """Deletes an emoji."""

        await emoji.delete(reason=f"Action done by {ctx.author}")
        await ctx.send(embed=green_embed(f"{self.bot.yes} Emoji successfully deleted."))

    @_emoji.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def info(self, ctx: Context, emoji: discord.Emoji):
        """Shows info about an emoji."""

        try:
            if emoji.guild is not None:
                emoji = await emoji.guild.fetch_emoji(emoji.id)

        except discord.NotFound:
            return await ctx.send(
                embed=red_embed(
                    f"{self.bot.no} I could not find this emoji in the given guild."
                )
            )

        is_managed = "Yes" if emoji.managed else "No"
        is_animated = "Yes" if emoji.animated else "No"
        requires_colons = "Yes" if emoji.require_colons else "No"
        can_use_emoji = (
            "Everyone"
            if not emoji.roles
            else " ".join(role.name for role in emoji.roles)
        )

        if emoji.guild and emoji.user is not None:
            description = f"""
**__General:__**
**- Name:** {emoji.name}
**- ID:** {emoji.id}
**- URL:** [Link To Emoji]({emoji.url})
**- Author:** {emoji.user.mention}
**- Time Created:** {format_date(emoji.created_at)}
**- Usable by:** {can_use_emoji}
**__Others:__**
**- Animated:** {is_animated}
**- Managed:** {is_managed}
**- Requires Colons:** {requires_colons}
**- Guild Name:** {emoji.guild.name}
**- Guild ID:** {emoji.guild.id}
        """

            embed = discord.Embed(
                title=f"**Emoji Information for:** `{emoji.name}`",
                description=description,
                color=0xADD8E6,
                timestamp=ctx.message.created_at,
            )
            embed.set_thumbnail(url=emoji.url)

            await ctx.send(embed=embed)

    @_emoji.command(name="list", aliases=["all"])
    @commands.guild_only()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def emoji_list(self, ctx: Context):
        """Show list of emojis in the server."""

        if ctx.guild and ctx.guild.emojis is not None:
            emojis = ctx.guild.emojis
            embeds = []

            chunk_size = 10
            emoji_chunks = [
                emojis[i : i + chunk_size] for i in range(0, len(emojis), chunk_size)
            ]

            for i, chunk in enumerate(emoji_chunks, 1):
                description = "\n\n".join(
                    [
                        f"{emoji} {f'`<a:{emoji.name}:{emoji.id}>`' if emoji.animated else f'`<:{emoji.name}:{emoji.id}>`'}"
                        for emoji in chunk
                    ]
                )

                embeds.append(
                    normal_embed(
                        title=f"{ctx.guild.name} Emojis ({len(emojis)})",
                        description=description,
                        timestamp=True,
                    )
                    .set_thumbnail(url=ctx.guild.icon.url)  # type: ignore
                    .set_footer(text=f"Page {i}/{len(emoji_chunks)}")
                )

            if not embeds:
                return await ctx.send("No emojis to display.")

            if len(embeds) == 1:
                return await ctx.send(embed=embeds[0])

            view = Paginator(ctx, embeds)
            return await ctx.send(embed=embeds[0], view=view)

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def emojify(self, ctx: Context, emoji: discord.Emoji):
        """Emojify a given emoji."""

        if emoji.url is not None:
            if isinstance(emoji, discord.Emoji):
                await ctx.send(emoji.url)

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def emojifyav(
        self, ctx: Context, url: Union[discord.Member, str], size: int = 14
    ):
        """
        Emojify an avatar or image link.
        Works fine with simple images.
        """

        if not isinstance(url, str):
            url = url.display_avatar.url

        def get_emojified_image() -> str:
            r = requests.get(url, stream=True)
            image = Image.open(r.raw).convert("RGB")
            res = emojify_image(image, size)

            if size > 14:
                res = f"```{res}```"
            return res

        result = await self.bot.loop.run_in_executor(None, get_emojified_image)
        await ctx.send(result)


async def setup(bot):
    await bot.add_cog(Emojis(bot))
