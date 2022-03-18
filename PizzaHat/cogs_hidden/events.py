import discord
from discord.ext import commands

from core.cog import Cog


class Events(Cog):
    """Events cog"""
    def __init__(self, bot):
        self.bot = bot

    @Cog.listener()
    async def on_ready(self):
        await self.bot.db.execute("""CREATE TABLE IF NOT EXISTS warnlogs 
                    (guild_id BIGINT, user_id BIGINT, warns TEXT[], time NUMERIC[])""")
        await self.bot.db.execute("""CREATE TABLE IF NOT EXISTS modlogs 
                    (guild_id BIGINT PRIMARY KEY, channel_id BIGINT)""")


    async def get_logs_channel(self, guild_id):
        data = await self.bot.db.fetchval("SELECT channel_id FROM modlogs WHERE guild_id=$1", guild_id)
        if data:
            return self.bot.get_channel(data)
        else:
            print(f"No modlog has been set for {guild_id}")
            return None


    @Cog.listener()
    async def on_message(self, msg):
        if msg.author.bot:
            return

        if self.bot.user == msg.author:
            return
        
        if msg.content in {"<@860889936914677770>", "<@!860889936914677770>"}:
            em = discord.Embed(color=self.bot.color)
            em.add_field(
                name='<a:wave_animated:783393435242463324> Hello! <a:wave_animated:783393435242463324>',
                value=f'Im {self.bot.user.name}, to get started, my prefix is `p!` or `P!` or <@860889936914677770>')
            await msg.channel.send(embed=em)

    @Cog.listener()
    async def on_message_edit(self, before, after):
        try:
            em = discord.Embed(
                title=f"Message edited in {before.message.channel}",
                color=self.bot.success,
                timestamp=before.created_at
            )
            em.add_field(name="-Before", value=before.content, inline=False)
            em.add_field(name="+After", value=after.content, inline=False)
            em.set_author(name=before.author, icon_url=before.author.avatar.url)
            em.set_footer(text=before.author.id)

            channel = await self.get_logs_channel(before.guild.id)
            await channel.send(embed=em)
        except Exception as e:
            print(e)

    @Cog.listener()
    async def on_message_delete(self, msg):
        try:
            em = discord.Embed(
                title=f"Message deleted in {msg.channel}",
                description=msg.content,
                color=self.bot.failed,
                timestamp=msg.created_at
            )
            em.set_author(name=msg.author, icon_url=msg.author.avatar.url)
            em.set_footer(text=msg.author.id)

            channel = await self.get_logs_channel(msg.guild.id)
            await channel.send(embed=em)
        except Exception as e:
            print(e)
    
    @Cog.listener()
    async def on_member_ban(self, guild, user):
        try:
            em = discord.Embed(
                title="Member banned",
                color=self.bot.failed,
            )
            em.set_author(name=user, icon_url=user.avatar.url)
            em.set_footer(text=user.id)

            channel = await self.get_logs_channel(guild.id)
            await channel.send(embed=em)
        except Exception as e:
            print(e)

    @Cog.listener()
    async def on_member_unban(self, guild, user):
        try:
            em = discord.Embed(
                title="Member unbanned",
                color=self.bot.success,
            )
            em.set_author(name=user, icon_url=user.avatar.url)
            em.set_footer(text=user.id)

            channel = await self.get_logs_channel(guild.id)
            await channel.send(embed=em)
        except Exception as e:
            print(e)
    
    @Cog.listener()
    async def on_guild_join(self, guild):
        if len([m for m in guild.members if m.bot]) > len(guild.members) / 2:
            try:
                await guild.text_channels[0].send(
                    '👋 I have automatically left this server since it has a high bot to member ratio.'
                )
                await guild.leave()
            except Exception as e:
                print(e)
        
    @Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            pass
        elif isinstance(error, commands.NotOwner):
            pass
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send(f'You are missing some required permissions: **{error.missing_perms}**')
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send(f"I'm missing some required permissions: **{error.missing_perms}**")
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                f'The command you tried is on cooldown. Try again in {round(error.retry_after)} seconds.'
                f'\n\n**Command name:**  {ctx.command}\n'
                f'**Cooldown time:**  {round(error.cooldown.per)} seconds'
                f'\n**Command uses:**  {error.cooldown.rate}'
            )
        elif isinstance(error, commands.RoleNotFound):
            await ctx.send('Please provide a role or the role could not be found.')
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send('Please specify a member or the member could not be found.')
        elif isinstance(error, commands.DisabledCommand):
            await ctx.send(f'**{ctx.command}**, is a disabled command in **{ctx.guild.name}**')
        elif isinstance(error, commands.ChannelNotFound):
            await ctx.send('Please specify a channel or the channel could not be found.')
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.author.send('This command cannot be used in DM\'s')
        elif isinstance(error, commands.EmojiNotFound):
            await ctx.send('Please provide an emoji or the emoji could not be found.')
        elif isinstance(error, commands.MissingRequiredArgument):
            em = discord.Embed(
                title = f'{ctx.command.name} {ctx.command.signature}',
                description = ctx.command.help,
                color = discord.Color.og_blurple()
            )
            await ctx.send(embed=em)

        else:
            await ctx.send(f"{self.bot.no} An error occured. My developer has been notified!")
            channel = self.bot.get_channel(764729444237180949)
            e = discord.Embed(
                title = "Error",
                description = f"```py\n{error}\n```",
                color = self.bot.failed
            )
            e.set_footer(text = f"From {ctx.guild}", icon_url = ctx.guild.icon.url)
            await channel.send(embed=e)

def setup(bot):
    bot.add_cog(Events(bot))
