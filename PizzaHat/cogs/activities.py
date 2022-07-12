from core.bot import PizzaHat
from core.cog import Cog
from discord.ext import commands
from discord.ext.commands import Context


class Activities(Cog, emoji="🚀"):
    """Discord Activities."""
    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot

    @commands.command(aliases=["ytt"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def yttogether(self, ctx: Context):
        """
        Starts a YouTube Together activity in your server.
        Must join a VC.
        """

        voice_state = ctx.author.voice  # type: ignore

        if voice_state is None:
            return await ctx.send("You need to join a VC to use this command.")
            
        else:
            link = await self.bot.togetherControl.create_link(ctx.author.voice.channel.id, 'youtube')  # type: ignore
            await ctx.send(f"Click the link to start the activity\n{link}")
        
    @commands.command(aliases=["pokernight"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def poker(self, ctx: Context):
        """
        Starts a Poker Night activity in your server.
        Must join a VC.
        """

        voice_state = ctx.author.voice  # type: ignore

        if voice_state is None:
            return await ctx.send("You need to join a VC to use this command.")

        else:
            link = await self.bot.togetherControl.create_link(ctx.author.voice.channel.id, 'poker')  # type: ignore
            await ctx.send(f"Click the link to start the activity\n{link}")
        
    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def chess(self, ctx: Context):
        """
        Starts a Chess in the Park activity in your server.
        Must join a VC.
        """

        voice_state = ctx.author.voice  # type: ignore

        if voice_state is None:
            return await ctx.send("You need to join a VC to use this command.")
        
        else:
            link = await self.bot.togetherControl.create_link(ctx.author.voice.channel.id, 'chess')  # type: ignore
            await ctx.send(f"Click the link to start the activity\n{link}")
        
    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def checkers(self, ctx: Context):
        """
        Starts a Checkers in the Park activity in your server.
        Must join a VC.
        """

        voice_state = ctx.author.voice  # type: ignore

        if voice_state is None:
            return await ctx.send("You need to join a VC to use this command.")

        else:
            link = await self.bot.togetherControl.create_link(ctx.author.voice.channel.id, 'checkers')  # type: ignore
            await ctx.send(f"Click the link to start the activity\n{link}")
        
    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def spellcast(self, ctx: Context):
        """
        Starts a Spell Case activity in your server.
        Must join a VC.
        """

        voice_state = ctx.author.voice  # type: ignore

        if voice_state is None:
            return await ctx.send("You need to join a VC to use this command.")
            
        else:
            link = await self.bot.togetherControl.create_link(ctx.author.voice.channel.id, 'spellcast')  # type: ignore
            await ctx.send(f"Click the link to start the activity\n{link}")
        
    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def betrayal(self, ctx: Context):
        """
        Starts a Betrayal IO activity in your server.
        Must join a VC.
        """
        
        voice_state = ctx.author.voice  # type: ignore

        if voice_state is None:
            return await ctx.send("You need to join a VC to use this command.")

        else:
            link = await self.bot.togetherControl.create_link(ctx.author.voice.channel.id, 'betrayal')  # type: ignore
            await ctx.send(f"Click the link to start the activity\n{link}")
        
        
async def setup(bot):
    await bot.add_cog(Activities(bot))
