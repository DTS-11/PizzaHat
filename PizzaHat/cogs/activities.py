from discord.ext import commands

from core.cog import Cog


class Activities(Cog, emoji="🚀"):
    """Discord Activities"""
    def __init__(self, bot):
        self.bot=bot

    @commands.command(aliases=["ytt"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def yttogether(self, ctx):
        """
        Starts a YouTube Together activity in your server.
        Must join a VC.
        """
        voice_state = ctx.author.voice

        if voice_state is None:
            return await ctx.send("You need to join a VC to use this command.")
            
        else:
            link = await self.bot.togetherControl.create_link(ctx.author.voice.channel.id, 'youtube')
            await ctx.send(f"Click the link to start the activity\n{link}")
        
    @commands.command(aliases=["pokernight"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def poker(self, ctx):
        """
        Starts a Poker Night activity in your server.
        Must join a VC.
        """
        voice_state = ctx.author.voice

        if voice_state is None:
            return await ctx.send("You need to join a VC to use this command.")

        else:
            link = await self.bot.togetherControl.create_link(ctx.author.voice.channel.id, 'poker')
            await ctx.send(f"Click the link to start the activity\n{link}")
        
    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def chess(self, ctx):
        """
        Starts a Chess in the Park activity in your server.
        Must join a VC.
        """
        voice_state = ctx.author.voice

        if voice_state is None:
            return await ctx.send("You need to join a VC to use this command.")
        
        else:
            link = await self.bot.togetherControl.create_link(ctx.author.voice.channel.id, 'chess')
            await ctx.send(f"Click the link to start the activity\n{link}")
        
    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def checkers(self, ctx):
        """
        Starts a Checkers in the Park activity in your server.
        Must join a VC.
        """
        voice_state = ctx.author.voice

        if voice_state is None:
            return await ctx.send("You need to join a VC to use this command.")

        else:
            link = await self.bot.togetherControl.create_link(ctx.author.voice.channel.id, 'checkers')
            await ctx.send(f"Click the link to start the activity\n{link}")
        
    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def spellcast(self, ctx):
        """
        Starts a Spell Case activity in your server.
        Must join a VC.
        """
        voice_state = ctx.author.voice

        if voice_state is None:
            return await ctx.send("You need to join a VC to use this command.")
            
        else:
            link = await self.bot.togetherControl.create_link(ctx.author.voice.channel.id, 'spellcast')
            await ctx.send(f"Click the link to start the activity\n{link}")
        
    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def betrayal(self, ctx):
        """
        Starts a Betrayal IO activity in your server.
        Must join a VC.
        """
        voice_state = ctx.author.voice

        if voice_state is None:
            return await ctx.send("You need to join a VC to use this command.")

        else:
            link = await self.bot.togetherControl.create_link(ctx.author.voice.channel.id, 'betrayal')
            await ctx.send(f"Click the link to start the activity\n{link}")
        
        
async def setup(bot):
    await bot.add_cog(Activities(bot))
