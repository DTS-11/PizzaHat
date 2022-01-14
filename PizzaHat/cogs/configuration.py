import discord
from discord.ext import commands

class Config(commands.Cog):
  """⚙ Configuration commands for the bot."""
  def __init__(self, bot):
    self.bot = bot
    
    
    
def setup(bot):
  bot.add_cog(Config(bot))
