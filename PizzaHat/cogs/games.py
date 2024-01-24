import discord
import discord_games as games
from core.bot import PizzaHat
from core.cog import Cog
from discord.ext import commands
from discord.ext.commands import Context
from discord_games import button_games


class Games(Cog, emoji="🎮"):
    """Games that can be played with the bot!"""
    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot


    @commands.command(aliases=['ttt'])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def tictactoe(self, ctx: Context, member: discord.User):
        """
        Play tic-tac-toe with another user.
        """

        game = button_games.BetaTictactoe(cross=ctx.author, circle=member) # type: ignore
        await game.start(ctx)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def hangman(self, ctx: Context):
        """
        Play hangman.
        """

        game = games.Hangman()
        await game.start(ctx, timeout=180, embed_color=self.bot.color, delete_after_guess=True)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def typerace(self, ctx: Context):
        """
        Play type racing game.
        """

        game = games.TypeRacer()
        await game.start(ctx, timeout=120)
    
    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def rps(self, ctx: Context, member: discord.User = None): # type: ignore
        """
        Play rock, paper, scissors with another user or the bot.
        """

        game = button_games.BetaRockPaperScissors(member)
        await game.start(ctx, timeout=30)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def chess(self, ctx: Context, member: discord.User):
        """
        Play chess with another user.
        """

        game = games.Chess(
            white=ctx.author, # type: ignore
            black=member,
        )
        await game.start(ctx, timeout=60, add_reaction_after_move=True)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def wordle(self, ctx: Context):
        """
        Play wordle.
        """

        game = button_games.BetaWordle()
        await game.start(ctx)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def guess(self, ctx: Context):
        """
        Guess the word.
        """

        game = button_games.BetaAkinator()
        await game.start(ctx, timeout=120, delete_button=True)


async def setup(bot):
    await bot.add_cog(Games(bot))
