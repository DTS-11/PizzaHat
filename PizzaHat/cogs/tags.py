from typing import Optional

import discord
from discord.ext import commands
from discord.ext.commands import Context

from core.bot import PizzaHat, Tier
from core.cog import Cog
from utils.custom_checks import _tier_cache
from utils.embed import ctx_embed, green_embed, red_embed
from utils.ui import Paginator

TAG_LIMITS = {
    Tier.FREE: 25,
    Tier.BASIC: 50,
    Tier.PRO: 250,
}


class Tags(Cog, emoji=1268850578415681546):
    """Organize and streamline your server's content."""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot

    @staticmethod
    def _chunk_text(content: str, limit: int) -> list[str]:
        chunks = []
        remaining = content

        while remaining:
            if len(remaining) <= limit:
                chunks.append(remaining)
                break

            split_at = remaining.rfind("\n", 0, limit)
            if split_at <= 0:
                split_at = limit

            chunks.append(remaining[:split_at])
            remaining = remaining[split_at:].lstrip("\n")

        return chunks or [""]

    async def _fetch_tag_content(
        self, ctx: Context, tag_name: str, full_info: bool = False
    ):
        """Fetch and display tag content. If full_info=True, show creator and timestamp."""
        if self.bot.db and ctx.guild is not None:
            data = await self.bot.db.fetchrow(
                "SELECT tag_name, content, creator, uses FROM tags WHERE guild_id=$1 AND tag_name=$2",
                ctx.guild.id,
                tag_name,
            )

            if not data:
                await ctx.send(
                    embed=red_embed(f"{self.bot.no} Tag `{tag_name}` not found.")
                )
                return

            content = data["content"]

            if full_info:
                creator = self.bot.get_user(data["creator"])
                if data["creator"] is not None and creator is None:
                    try:
                        creator = await self.bot.fetch_user(data["creator"])
                    except discord.HTTPException:
                        creator = None

                content_chunks = self._chunk_text(content, 4000)
                embeds = []

                for index, chunk in enumerate(content_chunks):
                    em = await ctx_embed(
                        ctx,
                        title=tag_name if index == 0 else f"{tag_name} (cont.)",
                        description=chunk,
                        timestamp=index == 0,
                    )

                    if index == 0:
                        em.set_author(
                            name=ctx.author.display_name,
                            icon_url=ctx.author.display_avatar.url,
                        )
                        if data["creator"] is None:
                            owner_value = "Unknown"
                        else:
                            owner_value = f"<@{data['creator']}>"
                            if creator is not None:
                                owner_value += f" `[{creator}]`"
                        em.add_field(
                            name="Owner",
                            value=owner_value,
                            inline=False,
                        )
                        em.add_field(
                            name="Uses",
                            value=str(data["uses"]),
                            inline=False,
                        )

                    embeds.append(em)

                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    paginator = Paginator(ctx, embeds)
                    await ctx.send(embed=embeds[0], view=paginator)
            else:
                await self.bot.db.execute(
                    "UPDATE tags SET uses = uses + 1 WHERE guild_id=$1 AND tag_name=$2",
                    ctx.guild.id,
                    tag_name,
                )
                if len(content) > 2000:
                    chunks = self._chunk_text(content, 2000)
                    for chunk in chunks:
                        await ctx.send(chunk)
                else:
                    await ctx.send(content)

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def tag(self, ctx: Context, *, tag_name: Optional[str] = None):
        """Tag commands. Pass a tag name to fetch its content."""

        if ctx.invoked_subcommand is not None:
            return
        if tag_name is None:
            await ctx.send_help(ctx.command)
        else:
            await self._fetch_tag_content(ctx, tag_name)

    @tag.command(name="create")
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(manage_messages=True)
    async def tag_create(self, ctx: Context, name: str, *, content: str):
        """
        Creates a new tag.
        Put quotes around the name if you want it to have multiple words.
        """

        if self.bot.db and ctx.guild is not None:
            if len(name) > 50:
                return await ctx.send(
                    embed=red_embed(
                        f"{self.bot.no} Tag name length cannot exceed 50 characters!"
                    )
                )

            cached_tier = _tier_cache.get(ctx.guild.id)
            if cached_tier is None:
                tier_row = await self.bot.db.fetchrow(
                    "SELECT tier FROM premium WHERE guild_id=$1", ctx.guild.id
                )
                cached_tier = Tier(tier_row["tier"]) if tier_row else Tier.FREE
                _tier_cache[ctx.guild.id] = cached_tier

            limit = TAG_LIMITS[cached_tier]
            current_tags = await self.bot.db.fetchval(
                "SELECT COUNT(*) FROM tags WHERE guild_id=$1", ctx.guild.id
            )

            if current_tags >= limit:
                tier_name = cached_tier.name.title()
                return await ctx.send(
                    embed=red_embed(
                        f"{self.bot.no} Tag limit reached! ({limit} tags).",
                        f"Your current tier is **{tier_name}**. Upgrade to unlock more tags.",
                    )
                )

            data = await self.bot.db.fetchrow(
                "SELECT tag_name FROM tags WHERE guild_id=$1 AND tag_name=$2",
                ctx.guild.id,
                name,
            )

            if data is None:
                (
                    await self.bot.db.execute(
                        "INSERT INTO tags (guild_id, tag_name, content, creator) VALUES ($1, $2, $3, $4)",
                        ctx.guild.id,
                        name,
                        content,
                        ctx.author.id,
                    )
                )
                await ctx.send(
                    embed=green_embed(f"{self.bot.yes} Tag created successfully!")
                )

            else:
                await ctx.send(
                    embed=red_embed(f"{self.bot.no} Tag with this name already exists!")
                )

    @tag.command(name="delete", aliases=["remove", "del"])
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(manage_messages=True)
    async def tag_delete(self, ctx: Context, tag: str):
        """Delete an existing tag."""

        if self.bot.db and ctx.guild is not None:
            deleted = await self.bot.db.execute(
                "DELETE FROM tags WHERE guild_id=$1 AND tag_name=$2",
                ctx.guild.id,
                tag,
            )

            if deleted.endswith("0"):
                await ctx.send(
                    embed=red_embed(
                        f"{self.bot.no} Tag with name `{tag}` does not exist."
                    )
                )
            else:
                await ctx.send(embed=green_embed(f"{self.bot.yes} Tag deleted!"))

    @tag.command(name="list", aliases=["all"])
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def tag_list(self, ctx: Context):
        """Retrieve all tags"""

        if self.bot.db and ctx.guild is not None:
            data = await self.bot.db.fetch(
                "SELECT tag_name FROM tags WHERE guild_id=$1", ctx.guild.id
            )

            if data:
                if len(data) > 10:
                    embeds = []
                    chunks = [data[i : i + 10] for i in range(0, len(data), 10)]

                    for chunk in chunks:
                        em = await ctx_embed(
                            ctx,
                            description="",
                        )
                        for i in chunk:
                            em.description += f"<:arrow:1267380018116563016> {i[0]}\n"  # type: ignore
                        embeds.append(em)

                    paginator = Paginator(ctx, embeds)
                    await ctx.send(embed=embeds[0], view=paginator)

                else:
                    em = await ctx_embed(
                        ctx,
                        description="",
                    )
                    for i in data:
                        em.description += f"<:arrow:1267380018116563016> {i[0]}\n"  # type: ignore
                    await ctx.send(embed=em)

            else:
                await ctx.send("No tags found.")

    @tag.command(name="info")
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def tag_info(self, ctx: Context, *, tag: Optional[str] = None):
        """Get info on a particular tag."""

        if tag is None:
            await ctx.send_help(ctx.command)
            return

        await self._fetch_tag_content(ctx, tag, full_info=True)

    @tag.command(name="edit")
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(manage_messages=True)
    async def tag_edit(self, ctx: Context, tag: str, *, content: str):
        """Edit the content of an existing tag."""

        if self.bot.db and ctx.guild:
            updated = await self.bot.db.execute(
                "UPDATE tags SET content=$1 WHERE guild_id=$2 AND tag_name=$3",
                content,
                ctx.guild.id,
                tag,
            )

            if updated.endswith("0"):
                await ctx.send(
                    embed=red_embed(
                        f"{self.bot.no} Tag with name `{tag}` does not exist."
                    )
                )
            else:
                await ctx.send(embed=green_embed(f"{self.bot.yes} Tag updated!"))


async def setup(bot: PizzaHat) -> None:
    await bot.add_cog(Tags(bot))
