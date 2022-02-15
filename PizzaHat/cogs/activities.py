import discord
from discord.ext import commands
from discord_together import DiscordTogether

class Activities(commands.Cog):
    """🚀 Discord Activity (beta)"""
    def __init__(self, bot):
        self.bot=bot
        
    @commands.command(aliases=["ytt"])
    async def yttogether(self, ctx):
        """
        Starts a YouTube Together activity in your server.
        Must join a VC.
        """
        link = self.bot.togetherControl.create_link(ctx.author.voice.channel.id, 'youtube')
        await ctx.send(f"Click the link to start the activity\n{link}")
        
    @commands.command(aliases=["pokernight"])
    async def poker(self, ctx):
        """
        Starts a Poker Night activity in your server.
        Must join a VC.
        """
        link = self.bot.togetherControl.create_link(ctx.author.voice.channel.id, 'poker')
        await ctx.send(f"Click the link to start the activity\n{link}")
        
    @commands.command()
    async def chess(self, ctx):
        """
        Starts a Chess in the Park activity in your server.
        Must join a VC.
        """
        link = self.bot.togetherControl.create_link(ctx.author.voice.channel.id, 'chess')
        await ctx.send(f"Click the link to start the activity\n{link}")
        
    @commands.command()
    async def checkers(self, ctx):
        """
        Starts a Checkers in the Park activity in your server.
        Must join a VC.
        """
        link = self.bot.togetherControl.create_link(ctx.author.voice.channel.id, 'checkers')
        await ctx.send(f"Click the link to start the activity\n{link}")
        
    @commands.command()
    async def spellcast(self, ctx):
        """
        Starts a Spell Case activity in your server.
        Must join a VC.
        """
        link = self.bot.togetherControl.create_link(ctx.author.voice.channel.id, 'spellcast')
        await ctx.send(f"Click the link to start the activity\n{link}")
        
    @commands.command()
    async def betrayal(self, ctx):
        """
        Starts a Betrayal IO activity in your server.
        Must join a VC.
        """
        link = self.bot.togetherControl.create_link(ctx.author.voice.channel.id, 'betrayal')
        await ctx.send(f"Click the link to start the activity\n{link}")
        
def setup(bot):
    bot.add_cog(Activities(bot))
