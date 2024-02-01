from discord.ext import commands
from discord.ext.commands import Context


class NoStaffRoleSet(commands.CheckFailure):
    pass


class UserNotStaff(commands.CheckFailure):
    pass


def server_staff_role():
    """Check if the server has a staff role set."""

    async def predicate(ctx: Context):
        role_id = await ctx.bot.db.fetchval("SELECT role_id FROM staff_role WHERE guild_id=$1", ctx.guild.id)  # type: ignore

        if ctx.guild.get_role(role_id):  # type: ignore
            return True

        else:
            await ctx.send("No staff role set in this server.")
            raise NoStaffRoleSet()

    return commands.check(predicate)


def user_is_staff():
    """Check if the user has a staff role."""

    async def predicate(ctx: Context):
        role_id = await ctx.bot.db.fetchval("SELECT role_id FROM staff_role WHERE guild_id=$1", ctx.guild.id)  # type: ignore

        if role_id in [role.id for role in ctx.author.roles]:  # type: ignore
            return True

        else:
            await ctx.send(
                "You do not have the required staff role to use this command."
            )
            raise UserNotStaff()

    return commands.check(predicate)
