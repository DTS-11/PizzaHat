import discord
from core.cog import Cog
from discord.ext import commands


class AutoMod(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mentions = discord.AllowedMentions(
            everyone=False,
            roles=False,
            users=True
        )

    def mod_perms(self, m: discord.Message):
        p = m.author.guild_permissions
        return True if (
            p.kick_members or p.ban_members or p.manage_guild or p.administrator or m.author == m.guild.owner
        ) else False

    @Cog.listener()
    async def on_message(self, msg):
        pass


async def setup(bot):
    await bot.add_cog(AutoMod(bot))
