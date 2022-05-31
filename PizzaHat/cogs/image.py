import os
import random

import aiohttp
import discord
from asyncdagpi import Client, ImageFeatures
from core.cog import Cog
from discord.ext import commands

dagpi = Client(os.getenv('DAGPI'))


class Images(Cog, emoji="📷"):
    """Cool image commands!"""
    def __init__(self, bot):
        self.bot = bot
    
    @staticmethod
    async def generate_image(member: discord.Member, gen_name: str, username: str=None, text: str=None):
        """Helper function for image generation commands."""
        url = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(getattr(ImageFeatures, gen_name)(), url=url, username=username, text=text)
        file = discord.File(fp=img.image, filename=f"{gen_name}.{img.format}")
        
        return file

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def meme(self, ctx):
        """Gets a random meme from Reddit."""
        async with aiohttp.ClientSession() as cs:
            async with cs.get('https://www.reddit.com/r/dankmemes/new.json?sort=hot') as r:
                memes = await r.json()

                em = discord.Embed(color=self.bot.color)
                em.set_image(url=memes['data']['children'] [random.randint(0, 25)]['data']['url'])
                em.set_footer(text='r/dankmemes')

                await ctx.send(embed=em)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def pixel(self, ctx, member: discord.Member=None):
        """
        Pixellates a user's avatar.
        If no user is provided, returns your avatar.
        """
        if member is None:
            member = ctx.author
        await ctx.send(file=await Images.generate_image(member, "pixel"))

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def tweet(self, ctx, member: discord.Member, *, text):
        """Tweeting with your pfp."""
        uname = member.name
        text = str(text)
        await ctx.send(file=await Images.generate_image(member, "tweet", uname, text))

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def triggered(self, ctx, member: discord.Member=None):
        """Triggers yours or someone's avatar."""
        if member is None:
            member = ctx.author
        await ctx.send(file=await Images.generate_image(member, "triggered"))
    
    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def wasted(self, ctx, member: discord.Member=None):
        """
        GTA wasted...
        If no user is given, returns yours.
        """
        if member is None:
            member = ctx.author
        await ctx.send(file=await Images.generate_image(member, "wasted"))

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def angel(self, ctx, member: discord.Member=None):
        """Angelify your pfp or someone's."""
        if member is None:
            member = ctx.author
        await ctx.send(file=await Images.generate_image(member, "angel"))

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def hitler(self, ctx, member: discord.Member=None):
        """Changes you or someone into hitler."""
        if member is None:
            member = ctx.author
        await ctx.send(file=await Images.generate_image(member, "hitler"))

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def delete(self, ctx, member: discord.Member=None):
        """Delete someone or yourself."""
        if member is None:
            member = ctx.author
        await ctx.send(file=await Images.generate_image(member, "delete"))

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def wanted(self, ctx, member: discord.Member=None):
        """Police wanted poster."""
        if member is None:
            member = ctx.author

        await ctx.send(file=await Images.generate_image(member, "wanted"))

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def jail(self, ctx, member: discord.Member=None):
        """Lock yourself or someone behind bars."""
        if member is None:
            member = ctx.author
        await ctx.send(file=await Images.generate_image(member, "jail"))

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def trash(self, ctx, member: discord.Member=None):
        """Replace the trash with your face/avatar."""
        if member is None:
            member = ctx.author
        await ctx.send(file=await Images.generate_image(member, "trash"))

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def discord(self, ctx, member: discord.Member, *, text):
        """Send a Discord message, simple."""
        uname = member.name
        text = str(text)
        await ctx.send(file=await Images.generate_image(member, "discord", uname, text))


async def setup(bot):
    await bot.add_cog(Images(bot))
