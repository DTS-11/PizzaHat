import discord
from core.cog import Cog

LOG_CHANNEL = 980151632199299092

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
        try:
            if data:
                return self.bot.get_channel(data)
        
        except AttributeError:
            pass

# ====== MESSAGE LOGS ======

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
        if before.author.bot:
            return

        if before.content == after.content:
            return

        em = discord.Embed(
            title=f"Message edited in #{before.channel}",
            color=self.bot.success,
            timestamp=before.created_at
        )
        em.add_field(name="- Before", value=before.content, inline=False)
        em.add_field(name="+ After", value=after.content, inline=False)
        em.set_author(name=before.author, icon_url=before.author.avatar.url)
        em.set_footer(text=f"User ID: {before.author.id}")

        channel = await self.get_logs_channel(before.guild.id)
        await channel.send(embed=em)

    @Cog.listener()
    async def on_message_delete(self, msg):
        if msg.author.bot:
            return

        em = discord.Embed(
            title=f"Message deleted in #{msg.channel}",
            description=msg.content,
            color=self.bot.failed,
            timestamp=msg.created_at
        )
        em.set_author(name=msg.author, icon_url=msg.author.avatar.url)
        em.set_footer(text=f"User ID: {msg.author.id}")

        channel = await self.get_logs_channel(msg.guild.id)
        await channel.send(embed=em)

# ====== MEMBER LOGS ======
    
    @Cog.listener()
    async def on_member_ban(self, guild, user):
        em = discord.Embed(
            title="Member banned",
            color=self.bot.failed,
        )
        em.set_author(name=user, icon_url=user.avatar.url)
        em.set_footer(text=f"User ID: {user.id}")

        channel = await self.get_logs_channel(guild.id)
        await channel.send(embed=em)

    @Cog.listener()
    async def on_member_unban(self, guild, user):
        em = discord.Embed(
            title="Member unbanned",
            color=self.bot.success,
        )
        em.set_author(name=user, icon_url=user.avatar.url)
        em.set_footer(text=f"User ID: {user.id}")

        channel = await self.get_logs_channel(guild.id)
        await channel.send(embed=em)

# ====== GUILD LOGS ======

    @Cog.listener()
    async def on_guild_role_create(self, role):
        em = discord.Embed(
            title="New role created",
            color=self.bot.success,
            timestamp=role.created_at
        )
        em.add_field(name="Name", value=role.name, inline=False)
        em.add_field(name="Color", value=role.color, inline=False)
        em.set_footer(text=f"Role ID: {role.id}")

        channel = await self.get_logs_channel(role.guild.id)
        await channel.send(embed=em)

    @Cog.listener()
    async def on_guild_role_delete(self, role):
        em = discord.Embed(
            title="Role deleted",
            color=self.bot.failed,
            timestamp=role.created_at
        )
        em.add_field(name="Name", value=role.name, inline=False)
        em.add_field(name="Color", value=role.color, inline=False)
        em.set_footer(text=f"Role ID: {role.id}")

        channel = await self.get_logs_channel(role.guild.id)
        await channel.send(embed=em)

    @Cog.listener()
    async def on_guild_role_update(self, before, after):
        if before == after:
            return

        em = discord.Embed(
            title="Role updated",
            color=self.bot.color,
            timestamp=after.created_at
        )
        em.add_field(name="- Before", value="\u200b", inline=False)
        em.add_field(name="Name", value=before.name, inline=False)
        em.add_field(name="Color", value=before.color, inline=False)
        em.add_field(name="+ After", value="\u200b", inline=False)
        em.add_field(name="Name", value=after.name, inline=False)
        em.add_field(name="Color", value=after.color, inline=False)
        em.set_footer(text=f"Role ID: {before.id}")

        channel = await self.get_logs_channel(before.guild.id)
        await channel.send(embed=em)
    
    @Cog.listener()
    async def on_guild_join(self, guild):
        # if len([m for m in guild.members if m.bot]) > len(guild.members) / 2:
        #     try:
        #         await guild.text_channels[0].send(
        #             '👋 I have automatically left this server since it has a high bot to member ratio.'
        #         )
        #         await guild.leave()
        #     except:
        #         pass

        em = discord.Embed(
            title="Guild Joined",
            color=self.bot.success
        )
        em.add_field(name="Guild", value=guild.name, inline=False)
        em.add_field(name="Members", value=len([m for m in guild.members if not m.bot]), inline=False)
        em.add_field(name="Bots", value=sum(member.bot for member in guild.members), inline=False)

        channel = self.bot.get_channel(LOG_CHANNEL)
        await channel.send(embed=em)

    @Cog.listener()
    async def on_guild_remove(self, guild):
        await self.bot.db.execute("DELETE FROM modlogs WHERE guild_id=$1", guild.id)

        channel = self.bot.get_channel(LOG_CHANNEL)
        await channel.send(f"Left {guild.name}")
            

async def setup(bot):
    await bot.add_cog(Events(bot))
