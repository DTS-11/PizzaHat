import os
import random

import aiohttp
import alexflipnote
import discord
from asyncdagpi import Client, ImageFeatures
from core.cog import Cog
from discord.ext import commands

dagpi = Client(os.getenv('DAGPI'))
alex_api = alexflipnote.Client()


class Images(Cog, emoji="📷"):
    """Cool image commands!"""
    def __init__(self, bot):
        self.bot = bot

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
    async def bird(self, ctx):
        """Return a random bird pic or gif."""

        em = discord.Embed(color=self.bot.color)
        em.set_image(url=await alex_api.birb())
        em.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url)

        await ctx.send(embed=em)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def dog(self, ctx):
        """Return a random dog pic or gif."""

        em = discord.Embed(color=self.bot.color)
        em.set_image(url=await alex_api.dogs())
        em.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url)

        await ctx.send(embed=em)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def cat(self, ctx):
        """Return a random cat pic or gif."""

        em = discord.Embed(color=self.bot.color)
        em.set_image(url=await alex_api.cats())
        em.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url)

        await ctx.send(embed=em)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def sadcat(self, ctx):
        """Return a random sadcat pic or gif."""

        em = discord.Embed(color=self.bot.color)
        em.set_image(url=await alex_api.sadcat())
        em.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url)

        await ctx.send(embed=em)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def coffee(self, ctx):
        """Return a random coffee pic or gif."""

        em = discord.Embed(color=self.bot.color)
        em.set_image(url=await alex_api.coffee())
        em.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url)

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

        url = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.pixel(), url)
        file = discord.File(fp=img.image,filename=f"pixel.{img.format}")

        await ctx.send(file=file)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def tweet(self, ctx, member: discord.Member, *, text):
        """Tweeting with your pfp."""

        uname = member.name
        text = str(text)
        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.tweet(), url=pfp, username=uname, text=text)   
        file = discord.File(fp=img.image,filename=f"tweet.{img.format}")

        await ctx.send(file=file)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def triggered(self, ctx, member: discord.Member=None):
        """Triggers yours or someone's avatar."""

        if member is None:
            member = ctx.author

        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.triggered(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"triggered.{img.format}")

        await ctx.send(file=file)
    
    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def wasted(self, ctx, member: discord.Member=None):
        """
        GTA wasted...
        If no user is given, returns yours.
        """

        if member is None:
            member = ctx.author

        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.wasted(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"wasted.{img.format}")

        await ctx.send(file=file)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def angel(self, ctx, member: discord.Member=None):
        """Angelify your pfp or someone else's."""

        if member is None:
            member = ctx.author

        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.angel(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"angel.{img.format}")

        await ctx.send(file=file)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def hitler(self, ctx, member: discord.Member=None):
        """Changes you or someone into hitler."""

        if member is None:
            member = ctx.author

        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.hitler(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"hitler.{img.format}")

        await ctx.send(file=file)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def delete(self, ctx, member: discord.Member=None):
        """Delete someone or yourself."""

        if member is None:
            member = ctx.author

        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.delete(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"delete.{img.format}")

        await ctx.send(file=file)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def wanted(self, ctx, member: discord.Member=None):
        """Police wanted poster."""

        if member is None:
            member = ctx.author

        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.wanted(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"wanted.{img.format}")

        await ctx.send(file=file)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def jail(self, ctx, member: discord.Member=None):
        """Lock yourself or someone behind bars."""

        if member is None:
            member = ctx.author

        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.jail(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"jail.{img.format}")

        await ctx.send(file=file)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def trash(self, ctx, member: discord.Member=None):
        """Replace the trash with your avatar."""

        if member is None:
            member = ctx.author

        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.trash(), url=pfp)   
        file = discord.File(fp=img.image, filename=f"trash.{img.format}")

        await ctx.send(file=file)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def discord(self, ctx, member: discord.Member, *, text):
        """Send a Discord message, simple."""
        
        uname = member.name
        text = str(text)
        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.discord(), url=pfp, username=uname, text=text)   
        file = discord.File(fp=img.image, filename=f"discord.{img.format}")

        await ctx.send(file=file)

    # @commands.command()
    # @commands.cooldown(1, 5, commands.BucketType.user)
    # async def bonk(self, ctx, member: discord.Member):
    #     """"""

    #     if member is None:
    #         member = ctx.author

    #     pfp = str(member.display_avatar.with_format("png").with_size(1024))
    #     img = await dagpi.image_process(ImageFeatures.bonk(), url=pfp)
    #     file = discord.File(fp=img.image, filename=f"bonk.{img.format}")

    #     await ctx.send(file=file)


async def setup(bot):
    await bot.add_cog(Images(bot))
