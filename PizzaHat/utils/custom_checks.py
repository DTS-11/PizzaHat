from discord.ext import commands
from discord.ext.commands import Context


class NoStaffRoleSet(commands.CheckFailure):
    pass


class UserNotStaff(commands.CheckFailure):
    pass


def server_staff_role():
    def predicate(ctx: Context):
        role_id = ctx.bot.db.fetchval("SELECT role_id FROM staff_role WHERE guild_id=$1", ctx.guild.id)  # type: ignore
        staff_role = ctx.guild.get_role(role_id)  # type: ignore

        if staff_role:
            return True

        else:
            raise NoStaffRoleSet

    return commands.check(predicate)


def user_is_staff():
    def predicate(ctx: Context):
        role_id = ctx.bot.db.fetchval("SELECT role_id FROM staff_role WHERE guild_id=$1", ctx.guild.id)  # type: ignore

        if role_id in ctx.author.roles:  # type: ignore
            return True

        else:
            raise UserNotStaff

    return commands.check(predicate)
