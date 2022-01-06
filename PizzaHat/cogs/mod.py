import discord
from discord.ext import commands
import asyncio
import typing
import uuid
from datetime import datetime

class Mod(commands.Cog):
    """<:moderation:847248846526087239> Moderation Commands"""
    def __init__(self,bot):
        self.bot = bot
    

    async def warn_log(self, guild_id, user_id):
        data = await self.bot.db.fetchrow("SELECT * FROM warnlogs WHERE guild_id=$1 AND user_id=$2", guild_id, user_id)
        if not data:
            return []
        return data

    async def warn_entry(self, guild_id, user_id, reason, time):
        data = await self.warn_log(guild_id, user_id)
        if data == []:
            await self.bot.db.execute("INSERT INTO warnlogs (guild_id, user_id, warns, times) VALUES ($1, $2, $3, $4)", guild_id, user_id, [reason], [time])
            return
        warns = data[2]
        times = data[3]

        if not warns:
            warns = [reason]
            times = [time]
        else:
            warns.append(reason)
            times.append(time)

        await self.bot.db.execute("UPDATE warnlogs SET times = $1, warns = $2 WHERE guild_id = $3 AND user_id = $4", times, warns, guild_id, user_id)
    
    async def delete_warn(self, guild_id, user_id, index):
        data = await self.warn_log(guild_id, user_id)
        if len(data[2])>=1:
            data[2].remove(data[2][index])
            data[3].remove(data[3][index])
            return await self.bot.db.execute("UPDATE warnlogs SET warns = $1, times = $2 WHERE guild_id = $3 AND user_id = $4", data[2], data[3], guild_id, user_id)
        else:
            await self.bot.db.execute("DELETE FROM warnlogs WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)


        # self.conn = sqlite3.connect("db's/moderation.db")
        # self.c = self.conn.cursor()
        # self.c.execute("""CREATE TABLE IF NOT EXISTS warns_data
        #             (guild_id int, admin_id int, user_id int, reason text)""")
        # self.c.execute("""CREATE TABLE IF NOT EXISTS mod_logs
        #             (channel_id bigint, guild_id bigint)""")


    @commands.command(aliases=['mn', 'mod-nick'])
    @commands.has_guild_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def modnick(self, ctx, member: discord.Member):
        """
        Set a random moderated nickname.
        """
        nick = f"Moderated Nickname {uuid.uuid4()}"[:24]
        await member.edit(nick = nick)
        await ctx.send(f'{self.bot.yes} Nickname changed to `{nick}`')

    @commands.command(aliases=['sn','set-nick'])
    @commands.has_guild_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def setnick(self, ctx, member: discord.Member, *, nick):
        """
        Set a custom nick-name.
        """
        await member.edit(nick=nick)
        await ctx.send(f'{self.bot.yes} Nickname for {member.name} was changed to {member.mention}')

    @commands.command(aliases=['sm','slow-mode'])
    @commands.has_guild_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def slowmode(self, ctx, seconds: int=None):
        """
        Change the slow-mode in the current channel. If no values are given,  returns slowmode of the current channel.
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

    @commands.group(invoke_without_command=True, aliases=['lockdown'])
    @commands.has_guild_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def lock(self, ctx):
        """Lock commands."""
        await ctx.send('Need to use a sub-command.')

    @lock.command(name='channel')
    @commands.has_guild_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def lock_channel(self, ctx, role:discord.Role=None, channel:discord.TextChannel=None):
        """
        Lock a channel with role requirement.
        When role is not given, returns the default role of the guild.
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
    @commands.has_guild_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def lock_server(self, ctx, role:discord.Role=None):
        """
        Lock whole server with role requirement.
        When role is not given, returns the default role of the guild.
        """
        role = ctx.guild.default_role or role

        for tc in ctx.guild.text_channels:
            await tc.set_permissions(role, send_messages=False, add_reactions=False)
        for vc in ctx.guild.voice_channels:
            await vc.set_permissions(role, connect=False, speak=False)

        em = discord.Embed(
            title=f'{self.bot.yes} Server Locked',
            description=f'The server has been locked by a staff member. You are **not muted**.',
            color=self.bot.color
        )
        await ctx.send(embed=em)

    @commands.group(invoke_without_command=True)
    @commands.has_guild_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unlock(self, ctx):
        """Unlock commands."""
        await ctx.send('Need to use a sub-command.')

    @unlock.command(name='channel')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def unlock_channel(self, ctx, role:discord.Role=None, channel:discord.TextChannel=None):
        """
        Unlock channel with role requirement.
        When role is not given, returns the default role of the guild.
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
    @commands.has_guild_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def unlock_server(self, ctx, role:discord.Role=None):
        """
        Unlock the whole server with role requirement.
        When role is not given, returns the default role of the guild.
        """
        role = ctx.guild.default_role or role
        for tc in ctx.guild.text_channels:
            await tc.set_permissions(role, send_messages=True, add_reactions=True, read_message_history=True)
        for vc in ctx.guild.voice_channels:
            await vc.set_permissions(role, connect=True, speak=True)

        em = discord.Embed(
            title=f'{self.bot.yes} Server Unlocked',
            description=f'The server has been unlocked.',
            color=self.bot.color
        )
        await ctx.send(embed=em)

    @commands.command(aliases=['purge'])
    @commands.has_guild_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def clear(self, ctx, amount:int=100):
        """
        Delete certain amount of messages in the current channel (max: 100).
        """
        if amount > 100:
            await ctx.send(f'{self.bot.no} I can only purge 100 messages (max) at a time.')
            return
        else:
            await ctx.channel.purge(limit=amount)
            await ctx.send(f'{self.bot.yes} {amount} messages cleared by {ctx.author}', delete_after=2.0)

    @commands.command()
    @commands.guild_only()
    @commands.has_guild_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def kick(self, ctx, member:discord.Member, *, reason=None):
        """
        Kicks a member from the server.
        """
        if reason is None:
            reason = f'No reason provided.\n- Kicked by {ctx.author}'

        await member.kick(reason=reason)
        await ctx.send(f'{self.bot.yes} Kicked `{member}`')

    @commands.command(aliases=['b'])
    @commands.has_guild_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def ban(self, ctx, member:typing.Union[discord.Member,int], *, reason=None):
        """
        Bans a member from the server.
        You can also ban someone that is not in the server using their user ID.
        """
        if reason is None:
            reason = f'No reason provided.\n- Banned by {ctx.author}'
        
        if isinstance(member, int):
            await ctx.guild.ban(discord.Object(id=member), reason=f"{reason}")
            user = await self.bot.fetch_user(member)
            await ctx.send(f'{self.bot.yes} Banned `{user}`')

        else:
            await member.ban(reason=f"{reason}", delete_message_days=0)
            await ctx.send(f'{self.bot.yes} Banned `{member}`')

    @commands.command(aliases=['mb','mass-ban'])
    @commands.guild_only()
    @commands.has_guild_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def massban(self, ctx, members:commands.Greedy[discord.Member], *, reason=None):
        """
        Mass bans multiple members from the server.
        You can only ban users who are in the server.
        """
        if reason is None:
            reason = f'No reason provided.\n- Banned by {ctx.author}'

        if not len(members):
            await ctx.send('One or more required arguments are missing.')

        else:
            for target in members:
                await target.ban(reason=reason, delete_message_days=0)
                await ctx.send(f'{self.bot.yes} Banned `{target}`')

    @commands.command(aliases=['ub'])
    @commands.has_guild_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def unban(self, ctx, id:int):
        """
        Unbans a member from the server.
        You can unban using their user ID.
        """
        try:
            user = self.bot.get_user(id)
            await ctx.guild.unban(discord.Object(id=id), reason=f'Unbanned by {ctx.author}')
            await ctx.send(f'{self.bot.yes} Unbanned `{user}`')

        except discord.NotFound:
            await ctx.send('Not a valid previously banned member or the member could not be found.')

    @commands.command()
    @commands.guild_only()
    @commands.has_guild_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def mute(self, ctx, member: discord.Member, *, reason=None):
        """
        Mutes a member, must be unmuted manually.
        """
        if reason is None:
            reason = 'No reason provided'
        role = discord.utils.get(ctx.guild.roles, name="Muted")
        await member.add_roles(role)
        await ctx.send(f"{self.bot.yes} {member.mention} has been muted, reason: {reason}")

    @commands.command()
    @commands.guild_only()
    @commands.has_guild_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def tempmute(self, ctx, member: discord.Member,time,*,reason=None):
        """
        Mutes a member for some time, unmutes automatically.
        """
        if reason is None:
            reason = 'No reason provided'
        muted_role=discord.utils.get(ctx.guild.roles, name="Muted")
        time_convert = {"s":1, "m":60, "h":3600,"d":86400}
        tempmute= int(time[0]) * time_convert[time[-1]]
        await member.add_roles(muted_role)
        embed = discord.Embed(description= f"{self.bot.yes} {member.mention} has been temprarily muted. \n\nReason: {reason}", color=self.bot.color)
        await ctx.send(embed=embed)
        await asyncio.sleep(tempmute)
        await member.remove_roles(muted_role)

    @commands.command()
    @commands.guild_only()
    @commands.has_guild_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def unmute(self, ctx, member: discord.Member):
        """
        Unmutes a member.
        """
        if not member:
            await ctx.send("Please specify a member")
            return
        role = discord.utils.get(ctx.guild.roles, name="Muted")
        await member.remove_roles(role)
        await ctx.send(f"{self.bot.yes} {member.mention} has been unmuted!")
    
    @commands.command(aliases=['create-role'], usage='<name> [mentionable] [hoisted] [reason]')
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def createrole(self, ctx, name, mentionable:bool=False, hoisted:bool=False, reason=None):
        """
        Creates a role in the server.
        """
        if reason is None:
            reason = f'Role created by {ctx.author}'
    
        await ctx.guild.create_role(name=name, hoist=hoisted, mentionable=mentionable)
        e = discord.Embed(
            title=f'{self.bot.yes} Role created',
            description=f'Name: {name}\nMentionable: {mentionable}\nHoisted: {hoisted}',
            color=self.bot.color
        )
        await ctx.send(embed=e)

    @commands.command(aliases=['delrole','delete-role'])
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def deleterole(self, ctx, *, role: discord.Role):
        """
        Deletes a role in the server.
        """
        await role.delete()
        await ctx.send(f'{self.bot.yes} Role has been deleted.')
    
    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def role(self, ctx, user: discord.Member, *, role: discord.Role):
        """
        Assign or remove role from a user just from one command.
        """
        if role in user.roles:
            await user.remove_roles(role)
            await ctx.send(f'{self.bot.yes} Successfully removed `{role.name}` from `{user}`')
        
        else:
            await user.add_roles(role)
            await ctx.send(f'{self.bot.yes} Successfully added `{role.name}` to `{user}`')

    # @commands.command()
    # @commands.guild_only()
    # @commands.has_guild_permissions(manage_messages=True)
    # @commands.bot_has_permissions(manage_messages=True)
    # async def warn(self, ctx, member:discord.Member, *, reason=None):
    #     """
    #     Warns a user.
        
    #     Works only if you and the bot has `Manage Messages` permissions.
    #     """
    #     warndb = self.conn
    #     cursor = warndb.cursor()

    #     if member == ctx.author:
    #         emb = discord.Embed(title=f'{self.bot.no} Error',description = "You can't warn yourself!", color=discord.Color.red())
    #         await ctx.send(embed = emb)
    #         return

    #     else:
    #         cursor.execute('INSERT OR IGNORE INTO warns_data (guild_id, admin_id, user_id, reason) VALUES (?,?,?,?)', (ctx.guild.id, ctx.author.id, member.id, reason))
    #         warndb.commit()

    #         em = discord.Embed(
    #             title=f"{self.bot.yes} Warned",
    #             description=f'Moderator: {ctx.author.mention}\nMember: {member.mention}\nReason: {reason}',
    #             color=self.bot.color
    #         )
    #         await ctx.send(embed=em)

    #         try:
    #             emb = discord.Embed(
    #                 title="You have been warned",
    #                 description=f'Moderator: {ctx.author.mention}\nMember: {member.mention}\nReason: {reason}\nGuild: {ctx.guild.name}',
    #                 color=self.bot.color
    #             )
    #             await member.send(embed = emb)

    #         except HTTPException:
    #             await ctx.send("Coudn't warn that user thru DM's.")

    # @commands.command(aliases=['clear-warns','remove-warns'])
    # @commands.guild_only()
    # @commands.has_guild_permissions(manage_messages=True)
    # @commands.bot_has_permissions(manage_messages=True)
    # async def clearwarn(self, ctx, member:discord.Member):
    #     """
    #     Clears every warns of the user.
        
    #     Works only if you and the bot has `Manage Messages` permissions.
    #     """
    #     warndb = self.conn
    #     cursor = warndb.cursor()

    #     if member == ctx.author:
    #         emb = discord.Embed(title='Error',description = "You can't remove warns from yourself", color=discord.Color.red())
    #         await ctx.send(embed = emb)
    #         return

    #     else:
    #         cursor.execute("DELETE FROM warns_data WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
    #         warndb.commit()
    #         emb = discord.Embed(title=f"{self.bot.yes} Warning Removed",color=self.bot.color)
    #         emb.add_field(name='Moderator:',value=ctx.message.author.mention,inline=False)
    #         emb.add_field(name='Member:',value=member.mention,inline=False)
    #         await ctx.send(embed = emb)

    # @commands.command(aliases=['warns'])
    # @commands.guild_only()
    # @commands.has_guild_permissions(manage_messages=True)
    # @commands.bot_has_permissions(manage_messages=True)
    # async def warnings(self, ctx, member:discord.Member=None):
    #     """
    #     Displays the warnings of the user.
    #     If no user is given, returns your warnings.
        
    #     Works only if you and the bot has `Manage Messages` permissions.
    #     """
    #     if member is None:
    #         member = ctx.author

    #     warndb = self.conn
    #     cursor = warndb.cursor()
    #     index = 0

    #     embed=discord.Embed(title=f"{member.name}'s Warnings", description="", color=self.bot.color)
    #     embed.set_thumbnail(url=member.avatar_url)
    #     msg = await ctx.send(embed=embed)
    #     db = cursor.execute('SELECT admin_id, reason FROM warns_data WHERE guild_id = ? AND user_id = ?', (ctx.guild.id, member.id,))
    #     for entry in db:
    #         index += 1
    #         admin_id, reason = entry
    #         admin_name = ctx.guild.get_member(admin_id)

    #         embed=discord.Embed(
    #             title=f"{member.name}'s Warnings",
    #             description=f"__Warn {index}__\n\nModerator: {admin_name.mention}\n Reason: {reason}",
    #             color=self.bot.color
    #         )
    #         embed.set_thumbnail(url=member.avatar_url)

    #         if embed.description =='':
    #             embed.description = f'{self.bot.yes} This user has no warnings!'

    #         await msg.edit(embed=embed)

    @commands.command()
    @commands.guild_only()
    @commands.has_guild_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def warn(self, ctx, member:discord.Member, *, reason="No reason provided"):
        """
        Warns a user.
        """
        data = self.warn_log(ctx.guild.id, member.id)
        count = len(data[3])

        if member == ctx.author or self.bot.user:
            return await ctx.send('You cant warn yourself or the bot.')
        
        if not ctx.author.top_role.position>member.top_role.position:
            return await ctx.send('You cant warn someone that has higher or same role heirarchy.')

        await self.warn_entry(ctx.guild.id, member.id, reason, ctx.message.created_at.timestamp)
        em = discord.Embed(
                title=f"{self.bot.yes} Warned User",
                description=f'Moderator: {ctx.author.mention}\nMember: {member.mention}\nReason: {reason}\nTotal Warns: {count} warns',
                color=self.bot.color,
                timestamp=datetime.datetime.utcnow()
            )
        await ctx.send(embed=em)
    
    @commands.command(aliases=['warns'])
    @commands.guild_only()
    @commands.has_guild_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def warnings(self, ctx, member:discord.Member=None):
        """
        Displays the warnings of the user.
        If no user is given, returns your warnings.
        """
        if member is None:
            member = ctx.author
        
        data = self.warn_log(ctx.guild.id, member.id)
        for i in range(len(data[2])):
            reason = data[2][i]

        if not data:
            em = discord.Embed(
                title=f'Warnings of {member.name}',
                description=f'{self.bot.yes} This user has no warns!',
                color=self.bot.color,
                timestamp=datetime.datetime.utcnow()
            )
            em.set_thumbnail(url=member.avatar_url)
            await ctx.send(embed=em)
        
        em = discord.Embed(
                title=f'Warnings of {member.name} | {len(data[2])} warns',
                description=f'Reason: {reason}\nWarn ID: `{data[3][i]}`',
                color=self.bot.color,
                timestamp=datetime.datetime.utcnow()
            )
        await ctx.send(embed=em)
    
    @commands.command(aliases=['delete-warn','delwarn'])
    @commands.guild_only()
    @commands.has_guild_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def deletewarn(self, ctx, member:discord.Member, warn_id:float):
        """
        Deletes a warn of the user.
        """
        data = await self.warn_log(ctx.guild.id, member.id)
        if data == []:
            return await ctx.send(f'{self.bot.no} This user has no warns!')
        if data[2] and warn_id in data[3]:
            index = data[3].index(warn_id)
            await self.delete_warn(ctx.guild.id, member.id, index)
            return await ctx.send(f'{self.bot.yes} Warn entry deleted!')
        else:
            return await ctx.send(f'{self.bot.no} No warn entry found for this user.')


def setup(bot):
  bot.add_cog(Mod(bot))
