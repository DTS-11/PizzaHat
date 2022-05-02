import discord
from discord.ext import commands
import typing
import uuid
import datetime
import humanfriendly
import traceback

from core.cog import Cog


class Mod(Cog, emoji=847248846526087239):
    """Moderation related commands"""
    def __init__(self,bot):
        self.bot = bot

    async def warn_log(self, guild_id, user_id):
        data = await self.bot.db.fetchrow("SELECT * FROM warnlogs WHERE guild_id=$1 AND user_id=$2", guild_id, user_id)
        if not data:
            print("No data")
        else:
            return data

    async def warn_entry(self, guild_id, user_id, reason, time):
        data = await self.warn_log(guild_id, user_id)
        if data == []:
            await self.bot.db.execute("INSERT INTO warnlogs (guild_id, user_id, warns, time) VALUES ($1, $2, $3, $4)", guild_id, user_id, [reason], [time])
            return
        warns = data[2]
        times = data[3]

        if not warns:
            warns = [reason]
            times = [time]
        else:
            warns.append(reason)
            times.append(time)

        await self.bot.db.execute("UPDATE warnlogs SET time = $1, warns = $2 WHERE guild_id = $3 AND user_id = $4", times, warns, guild_id, user_id)

    async def delete_warn(self, guild_id, user_id, index):
        data = await self.warn_log(guild_id, user_id)
        if len(data[2])>=1:
            data[2].remove(data[2][index])
            data[3].remove(data[3][index])
            return await self.bot.db.execute("UPDATE warnlogs SET warns = $1, time = $2 WHERE guild_id = $3 AND user_id = $4", data[2], data[3], guild_id, user_id)
        else:
            await self.bot.db.execute("DELETE FROM warnlogs WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)

    @commands.command(aliases=['mn'])
    @commands.guild_only()
    @commands.has_permissions(manage_nicknames=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def modnick(self, ctx, member: discord.Member):
        """
        Sets a random moderated nickname.

        In order for this to work, the bot must have Manage Nicknames permissions.

        To use this command, you must have Manage Nicknames permission.
        """
        try:
            nick = f"Moderated Nickname {uuid.uuid4()}"[:24]
            await member.edit(nick = nick)
            await ctx.send(f'{self.bot.yes} Nickname changed to `{nick}`')

        except discord.HTTPException:
            await ctx.send("Something went wrong.")

    @commands.command(aliases=['sn'])
    @commands.guild_only()
    @commands.has_permissions(manage_nicknames=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def setnick(self, ctx, member: discord.Member, *, nick):
        """
        Sets a custom nickname.

        In order for this to work, the bot must have Manage Nicknames permissions.

        To use this command, you must have Manage Nicknames permission.
        """
        try:
            await member.edit(nick=nick)
            await ctx.send(f'{self.bot.yes} Nickname for {member.name} was changed to {member.mention}')
        
        except discord.HTTPException:
            await ctx.send("Something went wrong.")

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_nicknames=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def decancer(self, ctx, member: discord.Member):
        """
        Removes special characters and renames the member as "Moderated Nickname"

        In order for this to work, the bot must have Manage Nicknames permissions.

        To use this command, you must have Manage Nicknames permission.
        """
        characters = "!@#$%^&*()_+-=.,/?;:[]{}`~\"'\\|<>"

        try:
            if characters in member.name:
                await member.edit(
                    nick="Moderated Nickname",
                    reason="PizzaHat decancer member."
                )
                await ctx.send(f"{self.bot.yes} Successfully decancered {member}")
        
        except discord.HTTPException:
            await ctx.send("Something went wrong.")

    @commands.command(aliases=['sm'])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def slowmode(self, ctx, seconds: int=None):
        """
        Change the slow-mode in the current channel.
        If no values are given, the bot returns slowmode of the current channel.

        In order for this to work, the bot must have Manage Messages permissions.

        To use this command, you must have Manage Messages permission.
        """
        if seconds is None:
            seconds = ctx.channel.slowmode_delay
            await ctx.send(f'The slowmode in this channel is `{seconds}` seconds')

        elif seconds == 0:
            await ctx.channel.edit(slowmode_delay=0)
            await ctx.send(f'{self.bot.yes} Slow-mode set to none in this channel. Chat goes brrrr....')

        else:
            await ctx.channel.edit(slowmode_delay=seconds)
            await ctx.send(f"{self.bot.yes} Slow-mode in this channel changed to `{seconds}` seconds!")

    @commands.group(aliases=['lockdown'])
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx):
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    @lock.command(name='channel')
    @commands.has_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def lock_channel(self, ctx, role:discord.Role=None, channel:discord.TextChannel=None):
        """
        Locks a channel with role requirement.
        If role is not given, the bot takes the default role of the guild which is @everyone.

        In order for this to work, the bot must have Manage Channels permissions.

        To use this command, you must have Manage Channels permission.
        """
        role = role or ctx.guild.default_role
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(role)
        overwrite.send_messages = False

        await channel.set_permissions(role, overwrite=overwrite)
        await ctx.message.add_reaction('🔒')
        em = discord.Embed(color=self.bot.color)
        em.add_field(name='🔒 Locked', value=f"{channel.mention} has been locked for {role.mention}",inline=False)
        await ctx.send(embed=em)

    @lock.command(name='server')
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def lock_server(self, ctx, role: discord.Role=None):
        """
        Locks the whole server with role requirement.
        If role is not given, the bot takes the default role of the guild which is @everyone.

        In order for this to work, the bot must have Manage Channels permissions.

        To use this command, you must have Manage Channels permission.
        """
        role = ctx.guild.default_role or role

        for tc in ctx.guild.text_channels:
            await tc.set_permissions(role, send_messages=False, add_reactions=False)
        for vc in ctx.guild.voice_channels:
            await vc.set_permissions(role, connect=False, speak=False)

        em = discord.Embed(
            title=f'{self.bot.yes} Server Locked',
            description=f'The server has been locked by a staff member. You are **not muted**.',
            color=self.bot.success
        )
        await ctx.send(embed=em)

    @commands.group()
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx):
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    @unlock.command(name='channel')
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def unlock_channel(self, ctx, role:discord.Role=None, channel:discord.TextChannel=None):
        """
        Unlocks a channel with role requirement.
        If role is not given, the bot takes the default role of the guild which is @everyone.

        In order for this to work, the bot must have Manage Channels permissions.

        To use this command, you must have Manage Channels permission.
        """
        role = role or ctx.guild.default_role
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(role)
        overwrite.send_messages = True

        await channel.set_permissions(role, overwrite=overwrite)
        await ctx.message.add_reaction('🔓')
        em = discord.Embed(color=self.bot.color)
        em.add_field(name='🔓 Unlocked', value=f"{channel.mention} has been unlocked for {role.mention}",inline=False)
        await ctx.send(embed=em)

    @unlock.command(name='server')
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def unlock_server(self, ctx, role: discord.Role=None):
        """
        Unlocks the whole server with role requirement.
        If role is not given, the bot takes the default role of the guild which is @everyone.

        In order for this to work, the bot must have Manage Channels permissions.

        To use this command, you must have Manage Channels permission.
        """
        role = ctx.guild.default_role or role
        for tc in ctx.guild.text_channels:
            await tc.set_permissions(role, send_messages=True, add_reactions=True, read_message_history=True)
        for vc in ctx.guild.voice_channels:
            await vc.set_permissions(role, connect=True, speak=True)

        em = discord.Embed(
            title=f'{self.bot.yes} Server Unlocked',
            description=f'The server has been unlocked.',
            color=self.bot.success
        )
        await ctx.send(embed=em)

    @commands.command(aliases=['purge'])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def clear(self, ctx, amount: int = 100):
        """
        Deletes certain amount of messages in the current channel.
        If no amount is given, it deletes upto 100 messages.

        In order for this to work, the bot must have Manage Messages permissions.

        To use this command, you must have Manage Messages permission.
        """
        if amount > 100:
            return await ctx.send(f'{self.bot.no} I can only purge 100 messages at a time.')
        else:
            await ctx.channel.purge(limit=amount)
            await ctx.send(f'{self.bot.yes} {amount} messages cleared by {ctx.author}', delete_after=2.5)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def cleanup(self, ctx, amount: int = 100):
        """
        Cleans up bot's messages in the current channel.
        If no amount is given, it deletes upto 100 messages.

        In order for this to work, the bot must have Manage Messages permissions.

        To use this command, you must have Manage Messages permission.
        """
        def is_bot(m):
            return m.author == self.bot.user

        if amount > 100:
            return await ctx.send(f"{self.bot.no} I can only clear upto 100 messages at a time.")
        else:
            await ctx.channel.purge(limit=amount, check=is_bot)
            await ctx.send(f"{self.bot.yes} {amount} messages cleared", delete_after=2.5)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def kick(self, ctx, member: discord.Member, *, reason=None):
        """
        Kicks a member from the server.

        In order for this to work, the bot must have Kick Members permissions.

        To use this command, you must have Kick Members permission.
        """
        if reason is None:
            reason = f"No reason provided.\nKicked by {ctx.author}"

        await member.kick(reason=reason)
        await ctx.send(f'{self.bot.yes} Kicked `{member}`')


    @commands.command(aliases=['b'])
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def ban(self, ctx, member: typing.Union[discord.Member,int], *, reason=None):
        """
        Bans a member whether or not the member is in the server.
        You can ban the member using their ID or my mentioning them.

        In order for this to work, the bot must have Ban Members permissions.

        To use this command, you must have Ban Members permission.
        """
        if reason is None:
            reason = f"No reason provided\nBanned by {ctx.author}"

        if isinstance(member, int):
            await ctx.guild.ban(discord.Object(id=member), reason=f"{reason}")
            user = await self.bot.fetch_user(member)
            await ctx.send(f'{self.bot.yes} Banned `{user}`')
        else:
            await member.ban(reason=f"{reason}", delete_message_days=0)
            await ctx.send(f'{self.bot.yes} Banned `{member}`')

    @commands.command(aliases=['mb'])
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def massban(self, ctx, members: commands.Greedy[discord.Member], *, reason=None):
        """
        Mass bans multiple members from the server.
        You can only ban users, who are in the server.

        In order for this to work, the bot must have Ban Members permissions.

        To use this command, you must have Ban Members permission.
        """
        if reason is None:
            reason = f"No reason provided\nBanned by {ctx.author}"

        if not len(members):
            await ctx.send('One or more required arguments are missing.')

        else:
            for target in members:
                await target.ban(reason=reason, delete_message_days=0)
                await ctx.send(f'{self.bot.yes} Banned `{target}`')

    @commands.command(aliases=['sb'])
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def softban(self, ctx, member: discord.Member, *, reason=None):
        """Soft bans a member from the server.

        A softban is basically banning the member from the server but
        then unbanning the member as well. This allows you to essentially
        kick the member while removing their messages.

        In order for this to work, the bot must have Ban Members permissions.

        To use this command, you must have Ban Members permission.
        """
        if reason is None:
            reason = f"No reason given.\nBanned by {ctx.author}"

        await ctx.guild.ban(member, reason)
        await ctx.guild.unban(member, reason)
        await ctx.send(f"{self.bot.yes} Sucessfully soft-banned {member}.")

    @commands.command(aliases=['ub'])
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def unban(self, ctx, id: int):
        """
        Unbans a member from the server using their ID.

        In order for this to work, the bot must have Ban Members permissions.

        To use this command, you must have Ban Members permission.
        """
        try:
            user = self.bot.get_user(id)
            await ctx.guild.unban(discord.Object(id=id), reason=f'Unbanned by {ctx.author}')
            await ctx.send(f'{self.bot.yes} Unbanned `{user}`')

        except discord.NotFound:
            await ctx.send('Not a valid previously banned member or the member could not be found.')

    @commands.command(aliases=['mute'])
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def timeout(self, ctx, member: discord.Member, time, *, reason=None):
        """
        Mutes or timeouts a member for specific time.
        Use 5m for 5 mins, 1h for 1 hour etc...

        In order for this to work, the bot must have Moderate Members permissions.

        To use this command, you must have Moderate Members permission.
        """
        if reason is None:
            reason = f"Action done by {ctx.author}"

        time = humanfriendly.parse_timespan(time)

        await member.timeout(until=discord.utils.utcnow() + datetime.timedelta(seconds=time), reason=reason)
        await ctx.send(f"{self.bot.yes} {member} has been muted for {time}.\nReason: {reason}")

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def unmute(self, ctx, member: discord.Member, *, reason=None):
        """
        Unmutes or removes a member from timeout.

        In order for this to work, the bot must have Moderate Members permissions.

        To use this command, you must have Moderate Members permission.
        """
        if reason is None:
            reason = f"Action done by {ctx.author}"
        await member.remove_timeout(reason=reason)
        await ctx.send(f"{self.bot.yes} {member} has been unmuted!")

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def role(self, ctx, user: discord.Member, *, role: discord.Role):
        """
        Assign or remove role from a user just from one command.

        In order for this to work, the bot must have Manage Roles permissions.

        To use this command, you must have Manage Roles permission.
        """
        if role in user.roles:
            await user.remove_roles(role)
            await ctx.send(f'{self.bot.yes} Successfully removed `{role.name}` from {user}')

        else:
            await user.add_roles(role)
            await ctx.send(f'{self.bot.yes} Successfully added `{role.name}` to {user}')

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def warn(self, ctx, member: discord.Member, *, reason=None):
        """
        Warns a user.

        To use this command, you must have Manage Messages permission.
        """
        if reason is None:
            reason = f"No reason given.\nWarned done by {ctx.author}"
        try:
            if member == ctx.author or member == self.bot.user:
                return await ctx.send('You cant warn yourself or the bot.')
            if not ctx.author.top_role.position == member.top_role.position:
                if not ctx.author.top_role.position > member.top_role.position:
                    return await ctx.send('You cant warn someone that has higher or same role heirarchy.')
            await self.warn_entry(ctx.guild.id, member.id, reason, float(ctx.message.created_at.timestamp()))
            em = discord.Embed(
                    title=f"{self.bot.yes} Warned User",
                    description=f'Moderator: {ctx.author.mention}\nMember: {member.mention}\nReason: {reason}',
                    color=self.bot.success,
                    timestamp=datetime.datetime.utcnow()
                )
            await ctx.send(embed=em)
        except Exception as e:
            print("".join(traceback.format_exception(e, e, e.__traceback__)))

    @commands.command(aliases=['warns'])
    @commands.guild_only()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def warnings(self, ctx, member:discord.Member=None):
        """
        Displays the warnings of the user.
        If no user is given, the bot sends your warnings.
        """
        if member is None:
            member = ctx.author

        data = await self.warn_log(ctx.guild.id, member.id)
        em = discord.Embed(
            title=f'Warnings of {member.name}',
            description=f'{self.bot.yes} This user has no warns!',
            color=self.bot.success,
            timestamp=datetime.datetime.utcnow()
        )
        em.set_thumbnail(url=member.avatar.url)
        if not data:
            return await ctx.send(embed=em)
        if not len(data[2]):
            return await ctx.send(embed=em)
        for i in range(len(data[2])):
            reason = data[2][i]
        em = discord.Embed(
                title=f'Warnings of {member.name} | {len(data[2])} warns',
                description=f'Reason: {reason}\nWarn ID: `{data[3][i]}`',
                color=self.bot.color,
                timestamp=datetime.datetime.utcnow()
            )
        await ctx.send(embed=em)

    @commands.command(aliases=['delwarn'])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def deletewarn(self, ctx, member: discord.Member, warn_id: float):
        """
        Deletes a warn of the user with warn ID.

        To use this command, you must have Manage Messages permission.
        """
        try:
            data = await self.warn_log(ctx.guild.id, member.id)
            if data == []:
                return await ctx.send(f'{self.bot.no} This user has no warns!')
            if data[2] and warn_id in data[3]:
                index = data[3].index(warn_id)
                await self.delete_warn(ctx.guild.id, member.id, index)
                return await ctx.send(f'{self.bot.yes} Warn entry deleted!')
            else:
                return await ctx.send(f'{self.bot.no} No warn entry found for this user.')
        except Exception as e:
            print("".join(traceback.format_exception(e, e, e.__traceback__)))


def setup(bot):
  bot.add_cog(Mod(bot))
