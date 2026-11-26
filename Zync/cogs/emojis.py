"""Emoji management and image-to-emoji commands.

Contains the public ``/emoji`` group for creating, deleting, inspecting, and
listing guild emojis, plus the ``/emojify`` and ``/emojifyav`` helpers that turn
an image into a grid of color-matched square emojis.
"""

from __future__ import annotations

import asyncio
import re
from io import BytesIO

import discord
import requests
import yarl
from discord.ext import commands
from discord.ext.commands import Context
from PIL import Image, UnidentifiedImageError

from core.bot import Zync
from core.cog import Cog
from utils.embed import ctx_embed, green_embed, orange_embed, red_embed
from utils.formats import format_date
from utils.ui import Paginator

_CUSTOM_EMOJI_RE = re.compile(r"<(a?):([A-Za-z0-9_]{2,32}):(\d+)>")
_MEMBER_MENTION_RE = re.compile(r"<@!?(\d+)>")
_IMAGE_EXTENSIONS = (".png", ".jpeg", ".jpg", ".gif")
_MAX_EMOJI_BYTES = 256 * 1024
_MAX_EMOJIFY_SIZE = 24

_COLORS = {
    (0, 0, 0): "⬛",
    (0, 0, 255): "🟦",
    (255, 0, 0): "🟥",
    (255, 255, 0): "🟨",
    (255, 165, 0): "🟧",
    (255, 255, 255): "⬜",
    (0, 255, 0): "🟩",
}


def _euclidean_distance(first: tuple[int, ...], second: tuple[int, ...]) -> float:
    """Return the RGB distance between two colors."""
    r1, g1, b1 = first
    r2, g2, b2 = second
    return ((r2 - r1) ** 2 + (g2 - g1) ** 2 + (b2 - b1) ** 2) ** 0.5


def _closest_emoji(color: tuple[int, ...]) -> str:
    """Return the square emoji closest to an RGB color."""
    return _COLORS[min(_COLORS, key=lambda key: _euclidean_distance(color, key))]


def _emojify_image(image: Image.Image, size: int = 14) -> str:
    """Render an image as a grid of color-matched square emojis."""
    small = image.resize((size, size), Image.Resampling.NEAREST).convert("RGB")
    pixels = small.load()
    assert pixels is not None

    rows = []
    for y in range(size):
        cells = []
        for x in range(size):
            pixel = pixels[x, y]
            rgb = pixel if isinstance(pixel, tuple) else (0, 0, 0)
            cells.append(_closest_emoji(tuple(int(channel) for channel in rgb)))
        rows.append("".join(cells))
    return "\n".join(rows)


def _parse_emoji_ref(value: str) -> tuple[str, bool] | None:
    """Resolve a custom emoji string or image URL into ``(url, animated)``."""
    raw = value.strip()

    match = _CUSTOM_EMOJI_RE.fullmatch(raw)
    if match:
        animated = bool(match.group(1))
        extension = "gif" if animated else "png"
        return (
            f"https://cdn.discordapp.com/emojis/{match.group(3)}.{extension}",
            animated,
        )

    try:
        url = yarl.URL(raw)
    except ValueError:
        return None

    if url.scheme not in ("http", "https"):
        return None
    path = url.path.lower()
    if not path.endswith(_IMAGE_EXTENSIONS):
        return None
    return raw, path.endswith(".gif")


async def _resolve_guild_emoji(ctx: Context, value: str) -> discord.Emoji | None:
    """Resolve a name, ID, or custom emoji string to a guild emoji."""
    if not ctx.guild:
        return None

    raw = value.strip()
    emoji_id: int | None = None

    match = _CUSTOM_EMOJI_RE.fullmatch(raw)
    if match:
        emoji_id = int(match.group(3))
    elif raw.isdigit():
        emoji_id = int(raw)
    else:
        name = raw[1:-1] if raw.startswith(":") and raw.endswith(":") else raw
        return discord.utils.get(ctx.guild.emojis, name=name)

    found = ctx.guild.get_emoji(emoji_id)
    if found:
        return found

    try:
        return await ctx.guild.fetch_emoji(emoji_id)
    except (discord.NotFound, discord.HTTPException):
        return None


class Emojis(Cog, emoji=1268867324195246133):
    """Emoji management commands."""

    def __init__(self, bot: Zync):
        self.bot: Zync = bot

    async def _send_emoji_list(self, ctx: Context) -> None:
        """Send the paginated guild emoji list."""
        if not ctx.guild:
            return

        guild_emojis = list(ctx.guild.emojis)
        if not guild_emojis:
            await ctx.send(
                embed=orange_embed(description="This server has no emojis to display.")
            )
            return

        embeds = []
        chunk_size = 10
        chunks = [
            guild_emojis[index : index + chunk_size]
            for index in range(0, len(guild_emojis), chunk_size)
        ]

        for page, chunk in enumerate(chunks, 1):
            lines = []
            for item in chunk:
                raw = (
                    f"<a:{item.name}:{item.id}>"
                    if item.animated
                    else f"<:{item.name}:{item.id}>"
                )
                lines.append(f"{item} `{raw}`")

            embed = await ctx_embed(
                ctx,
                title=f"{ctx.guild.name} Emojis ({len(guild_emojis)})",
                description="\n\n".join(lines),
                timestamp=True,
            )
            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)
            embed.set_footer(text=f"Page {page}/{len(chunks)}")
            embeds.append(embed)

        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
            return
        await ctx.send(embed=embeds[0], view=Paginator(ctx, embeds))

    @commands.hybrid_group(name="emoji", fallback="all")
    @commands.guild_only()
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def _emoji(self, ctx: Context):
        """List this server's emojis."""
        await self._send_emoji_list(ctx)

    @_emoji.command(name="create")
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def emoji_create(self, ctx: Context, source: str, name: str):
        """Create a guild emoji from a custom emoji or image URL."""
        if not ctx.guild:
            return

        if not re.fullmatch(r"[A-Za-z0-9_]{2,32}", name):
            return await ctx.send(
                embed=red_embed(
                    f"{self.bot.no} Emoji names must be 2-32 letters, numbers, or underscores."
                )
            )

        parsed = _parse_emoji_ref(source)
        if parsed is None:
            return await ctx.send(
                embed=red_embed(
                    f"{self.bot.no} Provide a custom emoji or a PNG/JPEG/GIF URL."
                )
            )
        url, animated = parsed

        used = sum(item.animated == animated for item in ctx.guild.emojis)
        if used >= ctx.guild.emoji_limit:
            return await ctx.send(
                embed=red_embed(
                    f"{self.bot.no} There are no more "
                    f"{'animated' if animated else 'static'} emoji slots in this server."
                )
            )

        try:
            async with self.bot.session.get(url) as response:
                if response.status >= 400:
                    return await ctx.send(
                        embed=red_embed(f"{self.bot.no} Could not fetch the image.")
                    )

                content_length = int(response.headers.get("Content-Length") or 0)
                if content_length >= _MAX_EMOJI_BYTES:
                    return await ctx.send(
                        embed=red_embed(f"{self.bot.no} Image is too big.")
                    )

                data = await response.read()
        except (ValueError, discord.HTTPException, OSError):
            return await ctx.send(
                embed=red_embed(f"{self.bot.no} Could not fetch the image.")
            )

        if len(data) >= _MAX_EMOJI_BYTES:
            return await ctx.send(embed=red_embed(f"{self.bot.no} Image is too big."))

        try:
            created = await asyncio.wait_for(
                ctx.guild.create_custom_emoji(
                    name=name,
                    image=data,
                    reason=f"Action done by {ctx.author}",
                ),
                timeout=10.0,
            )
        except asyncio.TimeoutError:
            return await ctx.send(
                embed=red_embed(
                    f"{self.bot.no} Discord took too long or rate limited the request."
                )
            )
        except discord.HTTPException as exc:
            return await ctx.send(
                embed=red_embed(f"{self.bot.no} Failed to create emoji: {exc}")
            )

        return await ctx.send(embed=green_embed(f"{self.bot.yes} Created {created}"))

    @_emoji.command(name="delete")
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def emoji_delete(self, ctx: Context, emoji: str):
        """Delete a guild emoji by name, ID, or custom emoji string."""
        target = await _resolve_guild_emoji(ctx, emoji)
        if target is None:
            return await ctx.send(
                embed=red_embed(f"{self.bot.no} I could not find that emoji.")
            )

        try:
            await target.delete(reason=f"Action done by {ctx.author}")
        except discord.HTTPException as exc:
            return await ctx.send(
                embed=red_embed(f"{self.bot.no} Failed to delete emoji: {exc}")
            )

        return await ctx.send(
            embed=green_embed(f"{self.bot.yes} Emoji successfully deleted.")
        )

    @_emoji.command(name="info")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def emoji_info(self, ctx: Context, emoji: str):
        """Show details about a guild emoji."""
        target = await _resolve_guild_emoji(ctx, emoji)
        if target is None:
            return await ctx.send(
                embed=red_embed(f"{self.bot.no} I could not find that emoji.")
            )

        try:
            if target.guild is not None:
                target = await target.guild.fetch_emoji(target.id)
        except discord.NotFound:
            return await ctx.send(
                embed=red_embed(
                    f"{self.bot.no} I could not find this emoji in the given guild."
                )
            )
        except discord.HTTPException:
            pass

        author = target.user.mention if target.user else "Unknown"
        can_use = (
            "Everyone"
            if not target.roles
            else " ".join(role.name for role in target.roles)
        )
        guild_name = target.guild.name if target.guild else "Unknown"
        guild_id = target.guild.id if target.guild else "N/A"
        description = (
            "**__General:__**\n"
            f"**- Name:** {target.name}\n"
            f"**- ID:** {target.id}\n"
            f"**- URL:** [Link To Emoji]({target.url})\n"
            f"**- Author:** {author}\n"
            f"**- Time Created:** {format_date(target.created_at)}\n"
            f"**- Usable by:** {can_use}\n"
            "**__Others:__**\n"
            f"**- Animated:** {'Yes' if target.animated else 'No'}\n"
            f"**- Managed:** {'Yes' if target.managed else 'No'}\n"
            f"**- Requires Colons:** {'Yes' if target.require_colons else 'No'}\n"
            f"**- Guild Name:** {guild_name}\n"
            f"**- Guild ID:** {guild_id}"
        )

        embed = discord.Embed(
            title=f":{target.name}:",
            description=description,
            color=0x456DD4,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=target.url)
        return await ctx.send(embed=embed)

    @_emoji.command(name="list")
    @commands.guild_only()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def emoji_list(self, ctx: Context):
        """Show a paginated list of guild emojis."""
        await self._send_emoji_list(ctx)

    @commands.hybrid_command(name="emojify")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def emojify(self, ctx: Context, emoji: str):
        """Return the image URL for a custom emoji."""
        target = await _resolve_guild_emoji(ctx, emoji)
        if target is not None:
            return await ctx.send(str(target.url))

        parsed = _parse_emoji_ref(emoji)
        if parsed is None:
            return await ctx.send(
                embed=red_embed(f"{self.bot.no} I could not resolve that emoji.")
            )
        return await ctx.send(parsed[0])

    @commands.hybrid_command(name="emojifyav")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def emojifyav(self, ctx: Context, target: str, size: int = 14):
        """Emojify a member avatar or image URL. Works best on simple images."""
        if not 1 <= size <= _MAX_EMOJIFY_SIZE:
            return await ctx.send(
                embed=red_embed(
                    f"{self.bot.no} Size must be between 1 and {_MAX_EMOJIFY_SIZE}."
                )
            )

        raw = target.strip()
        member = None
        mention = _MEMBER_MENTION_RE.fullmatch(raw)
        if ctx.guild:
            if raw.isdigit():
                member = ctx.guild.get_member(int(raw))
            elif mention:
                member = ctx.guild.get_member(int(mention.group(1)))

        if member:
            url = member.display_avatar.url
        else:
            try:
                parsed_url = yarl.URL(raw)
            except ValueError:
                return await ctx.send(
                    embed=red_embed(
                        f"{self.bot.no} Provide a member, mention, or image URL."
                    )
                )
            if parsed_url.scheme not in ("http", "https"):
                return await ctx.send(
                    embed=red_embed(
                        f"{self.bot.no} Provide an HTTP or HTTPS image URL."
                    )
                )
            url = raw

        def build() -> str:
            with requests.get(url, stream=True, timeout=10) as response:
                response.raise_for_status()
                image = Image.open(BytesIO(response.content)).convert("RGB")

            result = _emojify_image(image, size)
            if size > 14:
                result = f"```{result}```"
            if len(result) > 1900:
                raise ValueError("Emojified image is too large for a Discord message.")
            return result

        try:
            result = await asyncio.to_thread(build)
        except (requests.RequestException, OSError, ValueError, UnidentifiedImageError):
            return await ctx.send(
                embed=red_embed(f"{self.bot.no} Could not emojify that image.")
            )

        return await ctx.send(result)


async def setup(bot: Zync) -> None:
    """Register the emoji cog on startup."""
    await bot.add_cog(Emojis(bot))
