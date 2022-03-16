import discord

from core.cog import Cog

characters = "!@#$%^&*()_+-=.,/?;:[]{}`~\"'\\|<>"

class AntiHoist(Cog):
    def __init__(self, bot):
        self.bot = bot

    @Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if after.bot:
            return

        if after.display_name[0] in characters and not after.display_name.startswith("[AFK] "):
            try:
                await after.edit(
                    nick = before.display_name if before.display_name[0] not in characters else "Moderated Nickname",
                    reason = "PizzaHat anti-hoist"
                )
            except Exception:
                pass

    @Cog.listener()
    async def on_member_join(self, member):
        if member.bot:
            return
        
        if member.display_name[0] in characters:
            try:
                await member.edit(
                    nick = "Moderated Nickname",
                    reason = "PizzaHat anti-hoist"
                )
            except Exception:
                pass


def setup(bot):
    bot.add_cog(AntiHoist(bot))