import base64
import os
import random
from io import BytesIO

import aiohttp
import alexflipnote
import discord
from asyncdagpi import Client, ImageFeatures
from core.bot import PizzaHat
from core.cog import Cog
from discord.ext import commands
from discord.ext.commands import Context

dagpi = Client(os.getenv('DAGPI'))  # type: ignore
alex_api = alexflipnote.Client()


class Images(Cog, emoji="📷"):
    """Cool image commands!"""
    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def ai_gen(self, ctx: Context, *, prompt:str):
        """Generate an AI image."""

        msg = await ctx.send("Please wait...")

        async with aiohttp.request("POST", "https://backend.craiyon.com/generate", json={"prompt": prompt}) as resp:
            r = await resp.json()
            images = r['images']
            image = BytesIO(base64.decodebytes(images[0].encode("utf-8")))

            await msg.delete()
            return await ctx.send(file=discord.File(fp=image, filename="GenImg.png"))

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def meme(self, ctx: Context):
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
    async def bird(self, ctx: Context):
        """Return a random bird pic or gif."""

        if ctx.author.avatar is not None:
            em = discord.Embed(color=self.bot.color)
            em.set_image(url=await alex_api.birb())
            em.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url)

            await ctx.send(embed=em)

        else:
            return await ctx.send("No pfp.")

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def dog(self, ctx: Context):
        """Return a random dog pic or gif."""

        if ctx.author.avatar is not None:
            em = discord.Embed(color=self.bot.color)
            em.set_image(url=await alex_api.dogs())
            em.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url)

            await ctx.send(embed=em)

        else:
            return await ctx.send("No pfp.")

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def cat(self, ctx: Context):
        """Return a random cat pic or gif."""

        if ctx.author.avatar is not None:
            em = discord.Embed(color=self.bot.color)
            em.set_image(url=await alex_api.cats())
            em.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url)
        
            await ctx.send(embed=em)

        else:
            return await ctx.send("No pfp.")

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def sadcat(self, ctx: Context):
        """Return a random sadcat pic or gif."""

        if ctx.author.avatar is not None:
            em = discord.Embed(color=self.bot.color)
            em.set_image(url=await alex_api.sadcat())
            em.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url)

            await ctx.send(embed=em)

        else:
            return await ctx.send("No pfp.")

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def coffee(self, ctx: Context):
        """Return a random coffee pic or gif."""


        if ctx.author.avatar is not None:
            em = discord.Embed(color=self.bot.color)
            em.set_image(url=await alex_api.coffee())
            em.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url)

            await ctx.send(embed=em)
        
        else:
            return await ctx.send("No pfp.")

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def pixel(self, ctx: Context, member: discord.Member=None):  # type: ignore
        """
        Pixellates a user's avatar.
        If no user is provided, returns your avatar.
        """

        if member is None:
            member = ctx.author  # type: ignore

        url = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.pixel(), url)
        file = discord.File(fp=img.image,filename=f"pixel.{img.format}")

        await ctx.send(file=file)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def tweet(self, ctx: Context, member: discord.Member, *, text):
        """Tweeting with your pfp."""

        uname = member.name
        text = str(text)
        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.tweet(), url=pfp, username=uname, text=text)   
        file = discord.File(fp=img.image,filename=f"tweet.{img.format}")

        await ctx.send(file=file)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def triggered(self, ctx: Context, member: discord.Member=None):  # type: ignore
        """Triggers yours or someone's avatar."""

        if member is None:
            member = ctx.author  # type: ignore

        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.triggered(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"triggered.{img.format}")

        await ctx.send(file=file)
    
    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def wasted(self, ctx: Context, member: discord.Member=None):  # type: ignore
        """
        GTA wasted...
        If no user is given, returns yours.
        """

        if member is None:
            member = ctx.author  # type: ignore

        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.wasted(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"wasted.{img.format}")

        await ctx.send(file=file)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def angel(self, ctx: Context, member: discord.Member=None):  # type: ignore
        """Angelify your pfp or someone else's."""

        if member is None:
            member = ctx.author  # type: ignore

        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.angel(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"angel.{img.format}")

        await ctx.send(file=file)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def hitler(self, ctx: Context, member: discord.Member=None):  # type: ignore
        """Changes you or someone into hitler."""

        if member is None:
            member = ctx.author  # type: ignore

        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.hitler(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"hitler.{img.format}")

        await ctx.send(file=file)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def delete(self, ctx: Context, member: discord.Member=None):  # type: ignore
        """Delete someone or yourself."""

        if member is None:
            member = ctx.author  # type: ignore

        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.delete(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"delete.{img.format}")

        await ctx.send(file=file)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def wanted(self, ctx: Context, member: discord.Member=None):  # type: ignore
        """Police wanted poster."""

        if member is None:
            member = ctx.author  # type: ignore

        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.wanted(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"wanted.{img.format}")

        await ctx.send(file=file)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def jail(self, ctx: Context, member: discord.Member=None):  # type: ignore
        """Lock yourself or someone behind bars."""

        if member is None:
            member = ctx.author  # type: ignore

        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.jail(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"jail.{img.format}")

        await ctx.send(file=file)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def trash(self, ctx: Context, member: discord.Member=None):  # type: ignore
        """Replace the trash with your avatar."""

        if member is None:
            member = ctx.author  # type: ignore

        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.trash(), url=pfp)   
        file = discord.File(fp=img.image, filename=f"trash.{img.format}")

        await ctx.send(file=file)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def discord(self, ctx: Context, member: discord.Member, *, text):
        """Send a Discord message, simple."""
        
        uname = member.name
        text = str(text)
        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.discord(), url=pfp, username=uname, text=text)   
        file = discord.File(fp=img.image, filename=f"discord.{img.format}")

        await ctx.send(file=file)

    # @commands.command()
    # @commands.cooldown(1, 5, commands.BucketType.user)
    # async def bonk(self, ctx: Context, member: discord.Member):
    #     """"""

    #     if member is None:
    #         member = ctx.author

    #     pfp = str(member.display_avatar.with_format("png").with_size(1024))
    #     img = await dagpi.image_process(ImageFeatures.bonk(), url=pfp)
    #     file = discord.File(fp=img.image, filename=f"bonk.{img.format}")

    #     await ctx.send(file=file)


async def setup(bot):
    await bot.add_cog(Images(bot))
