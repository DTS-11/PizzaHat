import discord
from discord.ext import commands
from asyncdagpi import Client, ImageFeatures
import os
import aiohttp
import random

dagpi = Client(os.getenv('DAGPI'))

class Images(commands.Cog):
    """📷 Image Commands"""
    def __init__(self,client):
        self.client = client

    @commands.command()
    async def meme(self,ctx):
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
        url = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.pixel(), url)
        file = discord.File(fp=img.image,filename=f"pixel.{img.format}")
        await ctx.send(file=file)

    @commands.command()
    async def tweet(self, ctx, user: discord.Member, *, text):
        """Tweeting with your pfp.
        If no user is provided, replaces with your pfp."""
        uname = user.name
        text = str(text)
        pfp = str(user.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.tweet(), url=pfp, username=uname, text=text)   
        file = discord.File(fp=img.image,filename=f"tweet.{img.format}")
        await ctx.send(file=file)

    @commands.command()
    async def triggered(self, ctx, member: discord.Member = None):
        """Triggers yours or someone's avatar."""
        if member is None:
            member = ctx.author
        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.triggered(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"triggered.{img.format}")
        await ctx.send(file=file)
    
    @commands.command()
    async def wasted(self, ctx, member: discord.Member = None):
        """GTA wasted...
        If no user is given, returns yours."""
        if member is None:
            member = ctx.author
        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.wasted(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"wasted.{img.format}")
        await ctx.send(file=file)

    @commands.command()
    async def angel(self, ctx, member: discord.Member = None):
        """Angelify your pfp."""
        if member is None:
            member = ctx.author
        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.angel(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"angel.{img.format}")
        await ctx.send(file=file)

    @commands.command()
    async def hitler(self, ctx, member: discord.Member = None):
        """Changes you or someone into hitler."""
        if member is None:
            member = ctx.author
        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.hitler(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"hitler.{img.format}")
        await ctx.send(file=file)

    @commands.command()
    async def delete(self, ctx, member: discord.Member = None):
        """Delete someone or yourself."""
        if member is None:
            member = ctx.author
        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.delete(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"delete.{img.format}")
        await ctx.send(file=file)

    @commands.command()
    async def wanted(self, ctx, member: discord.Member = None):
        """Police wanted poster."""
        if member is None:
            member = ctx.author

        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.wanted(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"wanted.{img.format}")
        await ctx.send(file=file)

    @commands.command()
    async def jail(self, ctx, member: discord.Member = None):
        """Lock yourself or someone behind bars."""
        if member is None:
            member = ctx.author
        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.jail(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"jail.{img.format}")
        await ctx.send(file=file)

    @commands.command()
    async def trash(self, ctx, member: discord.Member = None):
        """Replace the trash with your face/avatar."""
        if member is None:
            member = ctx.author
        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.trash(), url=pfp)   
        file = discord.File(fp=img.image,filename=f"trash.{img.format}")
        await ctx.send(file=file)

    @commands.command()
    async def discord(self, ctx, member: discord.Member, *, text):
        """Send a Discord message, simple."""
        uname = member.name
        text = str(text)
        pfp = str(member.display_avatar.with_format("png").with_size(1024))
        img = await dagpi.image_process(ImageFeatures.discord(), url=pfp, username=uname, text=text)   
        file = discord.File(fp=img.image,filename=f"discord.{img.format}")
        await ctx.send(file=file)


def setup(client):
    client.add_cog(Images(client))
