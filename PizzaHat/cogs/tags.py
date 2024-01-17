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

    
    @commands.group(aliases=['tags'])
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def tag(self, ctx: Context):
        """Tag commands."""
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    @tag.command()
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(manage_messages=True)
    async def create(self, ctx: Context, name: str, *, content: str):
        """
        Creates a new tag with given name.

        Example: `p!tag create new_tag this is the content`

        In order for this to work, the bot must have Manage Messages permissions.

        To use this command, you must have Manage Messages permission.
        """

        try:
            if len(name) > 50:
                await ctx.send(f"{self.bot.no} Tag name length cannot exceed 50 characters!")
                
            data = await self.bot.db.fetchrow("SELECT * FROM tags WHERE guild_id=$1", ctx.guild.id) # type: ignore

            if data is None or data[1] != name:
                await self.bot.db.execute("INSERT INTO tags (guild_id, tag_name, content, creator) VALUES ($1, $2, $3, $4)", ctx.guild.id, name, content, ctx.author.id) # type: ignore
                await ctx.send(f"{self.bot.yes} Tag created successfully!")
            
            elif data[1] == name:
                await ctx.send(f"{self.bot.no} Tag with this name already exists!")
        
        except Exception as e:
            print(e)

    @tag.command()
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(manage_messages=True)
    async def delete(self, ctx: Context, tag: str):
        """
        Delete an existing tag.

        Example: `p!tag delete new_tag`

        In order for this to work, the bot must have Manage Messages permissions.

        To use this command, you must have Manage Messages permission.
        """

        data = await self.bot.db.fetch("SELECT * FROM tags WHERE guild_id=$1", ctx.guild.id) # type: ignore

        for i in data:
            if i[1] == tag:
                await self.bot.db.execute("DELETE FROM tags WHERE guild_id=$1 AND tag_name=$2", ctx.guild.id, tag) # type: ignore
                await ctx.send(f"{self.bot.yes} Tag deleted!")
                break
            
        else:
            await ctx.send(f"{self.bot.no} Tag with name `{tag}` does not exist.")

    @tag.command(name='list')
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def tag_list(self, ctx: Context):
        """Retrieve all tags"""

        if ctx.guild is not None:

            data = await self.bot.db.fetch("SELECT tag_name FROM tags WHERE guild_id=$1", ctx.guild.id) # type: ignore
            em = discord.Embed(
                description='',
                color=self.bot.color,
            )

            if data:
                for i in data:
                    em.description += f"<:join_arrow:946077216297590836> {i[0][0:15]}\n" # type: ignore

                await ctx.send(embed=em)
            
            else:
                await ctx.send("No tags found.")

    @tag.command()
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def info(self, ctx: Context, tag: str):
        """Get info on a particular tag."""

        data = await self.bot.db.fetch("SELECT tag_name, content, creator FROM tags WHERE guild_id=$1 AND tag_name=$2", ctx.guild.id, tag) # type: ignore
        em = discord.Embed(
            title=tag,
            description='',
            color=self.bot.color,
            timestamp=datetime.datetime.utcnow()
        )
        em.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar)

        if data:
            for i in data:
                em.description += i[1]
                em.add_field(name="Owner", value=f"<@{i[2]}>")

        await ctx.send(embed=em)

    @tag.command()
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(manage_messages=True)
    async def edit(self, ctx: Context, tag: str, *, content: str):
        """
        Edit the content of an existing tag.

        Example: `p!tag edit new_tag`

        In order for this to work, the bot must have Manage Messages permissions.

        To use this command, you must have Manage Messages permission.
        """

        data = await self.bot.db.fetch("SELECT tag_name, content FROM tags WHERE guild_id=$1", ctx.guild.id) # type: ignore

        for i in data:
            if i[0] == tag:
                await self.bot.db.execute("UPDATE tags SET content=$1 WHERE guild_id=$2 AND tag_name=$3", content, ctx.guild.id, tag) # type: ignore
                await ctx.send(f"{self.bot.yes} Tag updated!")
                break
        
        else:
            await ctx.send(f"{self.bot.no} Tag with name `{tag}` does not exist.")


async def setup(bot):
    await bot.add_cog(Tags(bot))