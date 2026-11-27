"""Guild emoji management commands.

Contains the public ``@Lucent emoji`` group for creating, deleting, inspecting
and listing guild emojis. Emoji creation only accepts Discord emoji references
(custom emoji markup, an emoji ID, or an emoji name in this guild); arbitrary
image URLs and local image processing are deliberately not supported.
"""

from __future__ import annotations

import asyncio
import re

import discord
from discord.ext import commands
from discord.ext.commands import Context

from core.bot import Lucent
from core.cog import Cog
from utils.embed import ctx_embed, green_embed, orange_embed, red_embed
from utils.formats import format_date
from utils.ui import Paginator

_CUSTOM_EMOJI_RE = re.compile(r"<(a?):([A-Za-z0-9_]{2,32}):(\d+)>")
_MAX_EMOJI_BYTES = 256 * 1024


async def _resolve_guild_emoji(ctx: Context, value: str) -> discord.Emoji | None:
    """Resolve a name, ID, or custom emoji string to an emoji in this guild."""
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


def _emoji_source(
    value: str, ctx: Context
) -> discord.Emoji | discord.PartialEmoji | None:
    """Build a Discord-backed emoji source; never accepts arbitrary URLs.

    Custom emoji markup and bare IDs are resolved through Discord's own asset
    API via ``PartialEmoji.read()``. Plain names resolve against this guild.
    """
    raw = value.strip()

    match = _CUSTOM_EMOJI_RE.fullmatch(raw)
    if match:
        return discord.PartialEmoji(
            name=match.group(2), id=int(match.group(3)), animated=bool(match.group(1))
        )
    if raw.isdigit():
        return discord.PartialEmoji(name="emoji", id=int(raw))

    if ctx.guild:
        return discord.utils.get(ctx.guild.emojis, name=raw.lstrip(":").rstrip(":"))
    return None


class Emojis(Cog, emoji=1268867324195246133):
    """Emoji management commands."""

    def __init__(self, bot: Lucent):
        self.bot: Lucent = bot

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

    @commands.hybrid_group(name="emoji", fallback="all", with_app_command=False)
    @commands.guild_only()
    async def _emoji(self, ctx: Context):
        """List this server's emojis (the fallback action)."""
        await self._send_emoji_list(ctx)

    @_emoji.command(name="create")
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def emoji_create(self, ctx: Context, source: str, name: str):
        """Create a guild emoji by copying another Discord emoji."""
        if not ctx.guild:
            return

        if not re.fullmatch(r"[A-Za-z0-9_]{2,32}", name):
            return await ctx.send(
                embed=red_embed(
                    f"{self.bot.no} Emoji names must be 2-32 letters, numbers, or underscores."
                )
            )

        emoji = _emoji_source(source, ctx)
        if emoji is None or getattr(emoji, "id", None) is None:
            return await ctx.send(
                embed=red_embed(
                    f"{self.bot.no} Provide a custom emoji, an emoji ID, or an emoji "
                    "from this server. Image URLs are not supported."
                )
            )

        animated = bool(getattr(emoji, "animated", False))
        used = sum(item.animated == animated for item in ctx.guild.emojis)
        if used >= ctx.guild.emoji_limit:
            return await ctx.send(
                embed=red_embed(
                    f"{self.bot.no} There are no more "
                    f"{'animated' if animated else 'static'} emoji slots in this server."
                )
            )

        try:
            data = await asyncio.wait_for(emoji.read(), timeout=10.0)
        except (discord.HTTPException, OSError, ValueError):
            return await ctx.send(
                embed=red_embed(
                    f"{self.bot.no} Could not fetch that emoji from Discord."
                )
            )
        except asyncio.TimeoutError:
            return await ctx.send(
                embed=red_embed(
                    f"{self.bot.no} Discord took too long to fetch that emoji."
                )
            )

        if len(data) >= _MAX_EMOJI_BYTES:
            return await ctx.send(embed=red_embed(f"{self.bot.no} Emoji is too big."))

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
    @commands.guild_only()
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


async def setup(bot: Lucent) -> None:
    """Register the emoji cog on startup."""
    await bot.add_cog(Emojis(bot))
