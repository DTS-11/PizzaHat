import datetime

import discord
from core.bot import PizzaHat
from core.cog import Cog
from discord.ext import commands
from discord.ext.commands import Context


class Tags(Cog, emoji="🏷"):
    """Commands to fetch something by a tag name."""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot

    @commands.group()
    @commands.guild_only()
    async def tag(self, ctx: Context):
        """Tag commands."""

        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    @tag.command(name="create")
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(manage_messages=True)
    async def tag_create(self, ctx: Context, name: str, *, content: str):
        """
        Creates a new tag with given name.

        Example: `p!tag create new_tag this is the content`

        In order for this to work, the bot must have Manage Messages permissions.

        To use this command, you must have Manage Messages permission.
        """

        if len(name) > 50:
            return await ctx.send(
                f"{self.bot.no} Tag name length cannot exceed 50 characters!"
            )

        data = (
            await self.bot.db.fetchrow(
                "SELECT * FROM tags WHERE guild_id=$1", ctx.guild.id
            )
            if self.bot.db and ctx.guild
            else None
        )

        if data is None or data[1] != name:
            (
                await self.bot.db.execute(
                    "INSERT INTO tags (guild_id, tag_name, content, creator) VALUES ($1, $2, $3, $4)",
                    ctx.guild.id,
                    name,
                    content,
                    ctx.author.id,
                )
                if self.bot.db and ctx.guild
                else None
            )
            await ctx.send(f"{self.bot.yes} Tag created successfully!")

        elif data[1] == name:
            await ctx.send(f"{self.bot.no} Tag with this name already exists!")

    @tag.command(name="delete", aliases=["remove", "del"])
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(manage_messages=True)
    async def tag_delete(self, ctx: Context, tag: str):
        """
        Delete an existing tag using tag name.

        Example: `p!tag delete new_tag`

        In order for this to work, the bot must have Manage Messages permissions.

        To use this command, you must have Manage Messages permission.
        """

        if self.bot.db and ctx.guild is not None:
            data = await self.bot.db.fetch(
                "SELECT * FROM tags WHERE guild_id=$1", ctx.guild.id
            )

            for i in data:
                if i[1] == tag:
                    await self.bot.db.execute(
                        "DELETE FROM tags WHERE guild_id=$1 AND tag_name=$2",
                        ctx.guild.id,
                        tag,
                    )
                    await ctx.send(f"{self.bot.yes} Tag deleted!")
                    break

            else:
                await ctx.send(f"{self.bot.no} Tag with name `{tag}` does not exist.")

    @tag.command(name="list", aliases=["all"])
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def tag_list(self, ctx: Context):
        """Retrieve all tags"""

        if self.bot.db and ctx.guild is not None:
            data = await self.bot.db.fetch(
                "SELECT tag_name FROM tags WHERE guild_id=$1", ctx.guild.id
            )
            em = discord.Embed(
                description="",
                color=self.bot.color,
            )

            if data:
                for i in data:
                    em.description += f"<:join_arrow:946077216297590836> {i[0]}\n"  # type: ignore

                await ctx.send(embed=em)

            else:
                await ctx.send("No tags found.")

    @tag.command(name="info")
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def tag_info(self, ctx: Context, tag: str):
        """Get info on a particular tag."""

        if self.bot.db and ctx.guild is not None:
            data = await self.bot.db.fetch(
                "SELECT tag_name, content, creator FROM tags WHERE guild_id=$1 AND tag_name=$2",
                ctx.guild.id,
                tag,
            )

            em = discord.Embed(
                title=tag,
                description="",
                color=self.bot.color,
                timestamp=datetime.datetime.now(),
            )
            em.set_author(
                name=ctx.author.display_name,
                icon_url=ctx.author.avatar if ctx.author.avatar else None,
            )

            if data:
                for i in data:
                    em.description += i[1]
                    em.add_field(
                        name="Owner",
                        value=f"<@{i[2]}> `[{await self.bot.fetch_user(i[2])}]`",
                        inline=False,
                    )

            await ctx.send(embed=em)

    @tag.command(name="edit")
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(manage_messages=True)
    async def tag_edit(self, ctx: Context, tag: str, *, content: str):
        """
        Edit the content of an existing tag.

        Example: `p!tag edit new_tag`

        In order for this to work, the bot must have Manage Messages permissions.

        To use this command, you must have Manage Messages permission.
        """

        if self.bot.db and ctx.guild:
            data = await self.bot.db.fetch(
                "SELECT tag_name, content FROM tags WHERE guild_id=$1", ctx.guild.id
            )

            if data:
                for i in data:
                    if i[0] == tag:
                        await self.bot.db.execute(
                            "UPDATE tags SET content=$1 WHERE guild_id=$2 AND tag_name=$3",
                            content,
                            ctx.guild.id,
                            tag,
                        )
                        await ctx.send(f"{self.bot.yes} Tag updated!")
                        break

            else:
                await ctx.send(f"{self.bot.no} Tag with name `{tag}` does not exist.")


async def setup(bot):
    await bot.add_cog(Tags(bot))
