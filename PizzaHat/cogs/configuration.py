from discord.ext import commands

from core.cog import Cog


class Config(Cog, emoji="⚙"):
    """Configuration commands for the bot."""
    def __init__(self, bot):
        self.bot = bot
        
    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def disable(self, ctx, *, command):
        """Disable a command."""
        # to be done...
    
    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def enable(self, ctx, *, command):
        """Enable a disabled command."""
        # to be done...
    
    
def setup(bot):
    bot.add_cog(Config(bot))
