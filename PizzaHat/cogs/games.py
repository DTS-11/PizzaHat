from typing import Optional

import discord
import discord_games as games
from discord.ext import commands
from discord.ext.commands import Context
from discord_games import button_games

from core.bot import PizzaHat
from core.cog import Cog


class Games(Cog, emoji=1268852069624975441):
    """Games that can be played with the bot!"""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot

    @commands.command(aliases=["ttt"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def tictactoe(self, ctx: Context, member: discord.User):
        """Play Tic-Tac-Toe."""

        if member == ctx.author or member.bot:
            return await ctx.send("You can't play against yourself or bots!")

        game = button_games.BetaTictactoe(cross=ctx.author, circle=member)  # type: ignore
        await game.start(ctx, timeout=300, embed_color=self.bot.color)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def hangman(self, ctx: Context):
        """Play hangman."""

        game = button_games.BetaHangman()
        await game.start(ctx, timeout=180, embed_color=self.bot.color)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def typerace(self, ctx: Context):
        """Play type racing game."""

        game = games.TypeRacer()
        await game.start(ctx, timeout=120, embed_color=self.bot.color)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def rps(self, ctx: Context, member: Optional[discord.User] = None):
        """Play rock, paper, scissor"""

        if member == ctx.author or (member is not None and member.bot):
            return await ctx.send("You can't play against yourself or bots!")

        game = button_games.BetaRockPaperScissors(member)
        await game.start(ctx, timeout=30, embed_color=self.bot.color)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def chess(self, ctx: Context, member: discord.User):
        """Play chess."""

        if member == ctx.author or member.bot:
            return await ctx.send("You can't play against yourself or bots!")

        game = button_games.BetaChess(white=ctx.author, black=member)  # type: ignore
        await game.start(ctx, timeout=600, embed_color=self.bot.color)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def wordle(self, ctx: Context):
        """Play wordle."""

        game = button_games.BetaWordle()
        await game.start(ctx, timeout=180, embed_color=self.bot.color)

    @commands.command(aliases=["aki"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def akinator(self, ctx: Context):
        """Think of someone/something and I'll guess it"""

        game = button_games.BetaAkinator()
        await game.start(
            ctx, timeout=300, delete_button=True, embed_color=self.bot.color
        )

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def reactiontest(self, ctx: Context):
        """Test your reaction time."""

        game = button_games.BetaReactionGame()
        await game.start(ctx, timeout=15, embed_color=self.bot.color)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def connect4(self, ctx: Context, member: discord.User):
        """Play connect4."""

        if member == ctx.author or member.bot:
            return await ctx.send("You can't play against yourself or bots!")

        game = button_games.BetaConnectFour(red=ctx.author, blue=member)  # type: ignore
        await game.start(ctx, timeout=300, embed_color=self.bot.color)


async def setup(bot):
    await bot.add_cog(Games(bot))
