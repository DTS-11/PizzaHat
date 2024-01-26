from discord.ext import commands
from discord.ext.commands import Context


class NotServerStaff(commands.CheckFailure):
    pass


def is_staff():
    def predicate(ctx: Context):
        val = ctx.bot.db.fetchval("SELECT role_id FROM staff_role WHERE guild_id=$1", ctx.guild.id)  # type: ignore

        if val:
            return True
        else:
            raise NotServerStaff

    return commands.check(predicate)
