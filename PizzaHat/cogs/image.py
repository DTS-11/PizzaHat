import discord
from discord.ext import commands
from numpy import delete
from asyncdagpi import Client, ImageFeatures
import os
import aiohttp
import random

from core.cog import Cog

dagpi = Client(os.getenv('DAGPI'))


class Images(Cog, emoji="📷"):
    """Image Commands"""
    def __init__(self, client):
        self.client = client
    
    @staticmethod
    async def generate_image(member: discord.Member, gen_name: str, username: str=None, text: str=None):
        """Helper function for image generation commands."""

        url = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(getattr(ImageFeatures, gen_name)(), url, username, text)
        file = discord.File(fp=img.image, filename=f"{gen_name}.{img.format}")

        return file

    @commands.command()
    async def meme(self, ctx):
        """Gets a random meme from Reddit."""
        async with aiohttp.ClientSession() as cs:
            async with cs.get('https://reddit.com/r/dankmemes.json') as r:
                memes = await r.json()
                em = discord.Embed(
                    color=discord.Color.random()
                )
                em.set_image(url=memes['data']['children'][random.randint(0, 50)]['data']['url'])
                em.set_footer(text='r/dankmemes')
                await ctx.send(embed=em)

    @commands.command()
    async def pixel(self, ctx, member: discord.Member=None):
        """Pixellates a user's avatar.
        If no user is provided, returns yours avatar."""
        if member is None:
            member = ctx.author
        await ctx.send(file=await Images.generate_image(member, "pixel"))

    @commands.command()
    async def tweet(self, ctx, member: discord.Member, *, text):
        """Tweeting with your pfp.
        If no user is provided, replaces with your pfp."""
        uname = member.name
        text = str(text)
        await ctx.send(file=await Images.generate_image(member, "tweet", uname, text))

    @commands.command()
    async def triggered(self, ctx, member: discord.Member = None):
        """Triggers yours or someone's avatar."""
        if member is None:
            member = ctx.author
        await ctx.send(file=await Images.generate_image(member, "triggered"))
    
    @commands.command()
    async def wasted(self, ctx, member: discord.Member = None):
        """GTA wasted...
        If no user is given, returns yours."""
        if member is None:
            member = ctx.author
        await ctx.send(file=await Images.generate_image(member, "wasted"))

    @commands.command()
    async def angel(self, ctx, member: discord.Member = None):
        """Angelify your pfp."""
        if member is None:
            member = ctx.author
        await ctx.send(file=await Images.generate_image(member, "angle"))

    @commands.command()
    async def hitler(self, ctx, member: discord.Member = None):
        """Changes you or someone into hitler."""
        if member is None:
            member = ctx.author
        await ctx.send(file=await Images.generate_image(member, "hitler"))

    @commands.command()
    async def delete(self, ctx, member: discord.Member = None):
        """Delete someone or yourself."""
        if member is None:
            member = ctx.author
        await ctx.send(file=await Images.generate_image(member, "delete"))

    @commands.command()
    async def wanted(self, ctx, member: discord.Member = None):
        """Police wanted poster."""
        if member is None:
            member = ctx.author

        await ctx.send(file=await Images.generate_image(member, "wanted"))

    @commands.command()
    async def jail(self, ctx, member: discord.Member = None):
        """Lock yourself or someone behind bars."""
        if member is None:
            member = ctx.author
        await ctx.send(file=await Images.generate_image(member, "jail"))

    @commands.command()
    async def trash(self, ctx, member: discord.Member = None):
        """Replace the trash with your face/avatar."""
        if member is None:
            member = ctx.author
        await ctx.send(file=await Images.generate_image(member, "trash"))

    @commands.command()
    async def discord(self, ctx, member: discord.Member, *, text):
        """Send a Discord message, simple."""
        uname = member.name
        text = str(text)
        await ctx.send(file=await Images.generate_image(member, "discord", uname, text))


def setup(client):
    client.add_cog(Images(client))
