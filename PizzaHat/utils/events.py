import datetime
import os

import discord
import requests
import topgg
from core.bot import PizzaHat
from core.cog import Cog
from discord.ext import tasks
from dotenv import load_dotenv
from humanfriendly import format_timespan

load_dotenv()

LOG_CHANNEL = 980151632199299092
DLIST_TOKEN = os.getenv("DLIST_AUTH")


class Events(Cog):
    """Events cog"""
    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot
        bot.loop.create_task(self.update_stats())

    @tasks.loop(minutes=30)
    async def update_stats(self):
        try:
            # Top.gg
            await self.bot.wait_until_ready()
            self.topggpy = topgg.DBLClient(self, os.getenv("DBL_TOKEN"), autopost=True)  # type: ignore
            await self.topggpy.post_guild_count()
            print(f"Posted server count: {self.topggpy.guild_count}")

        except Exception as e:
            print(f"Failed to post server count\n{e.__class__.__name__}: {e}")

        try:
            # DList.gg
            url = f"https://api.discordlist.gg/v0/bots/860889936914677770/guilds?count={len(self.bot.guilds)}"
            headers = {'Authorization': f"Bearer {DLIST_TOKEN}", "Content-Type": "application/json"}
            r = requests.put(url, headers=headers)
            print(r.json())

        except Exception as e:
            print(e)

    @Cog.listener()
    async def on_ready(self):
        await self.bot.db.execute(  # type: ignore
            """CREATE TABLE IF NOT EXISTS warnlogs 
            (guild_id BIGINT, user_id BIGINT, warns TEXT[], time NUMERIC[])"""
        )

        await self.bot.db.execute(  # type: ignore
            """CREATE TABLE IF NOT EXISTS modlogs 
            (guild_id BIGINT PRIMARY KEY, channel_id BIGINT)"""
        )

        await self.bot.db.execute(  # type: ignore
            """CREATE TABLE IF NOT EXISTS automod 
            (guild_id BIGINT PRIMARY KEY, enabled BOOL)"""
        )

        await self.bot.db.execute(  # type: ignore
            """CREATE TABLE IF NOT EXISTS staff_role 
            (guild_id BIGINT, role_id BIGINT)"""
        )

        await self.bot.db.execute( # type: ignore
            """CREATE TABLE IF NOT EXISTS tags 
            (guild_id BIGINT, tag_name TEXT, content TEXT, creator BIGINT)"""
        )


    async def get_logs_channel(self, guild_id):
        data = await self.bot.db.fetchval("SELECT channel_id FROM modlogs WHERE guild_id=$1", guild_id)  # type: ignore
        if data:
            return self.bot.get_channel(data)

# ====== MESSAGE LOGS ======

    @Cog.listener()
    async def on_message(self, msg):
        if self.bot is None:
            bot_id = self.bot.user.id

            if msg.author.bot:
                return

            if self.bot.user == msg.author:
                return

            if msg.content in {f"<@{bot_id}>" or f"<@!{bot_id}>"}:
                em = discord.Embed(color=self.bot.color)
                em.add_field(
                    name="<a:wave_animated:783393435242463324> Hello! <a:wave_animated:783393435242463324>",
                    value=f"I'm {self.bot.user.name}, to get started, my prefix is `p!` or `P!` or <@860889936914677770>")
                    
                await msg.channel.send(embed=em)

    @Cog.listener()
    async def on_message_edit(self, before, after):
        channel = await self.get_logs_channel(before.guild.id)

        if not channel:
            return

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

        await channel.send(embed=em)  # type: ignore

    @Cog.listener()
    async def on_message_delete(self, msg):
        channel = await self.get_logs_channel(msg.guild.id)

        if not channel:
            return

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

        await channel.send(embed=em)  # type: ignore

# ====== MEMBER LOGS ======
    
    @Cog.listener()
    async def on_member_ban(self, guild, user):
        channel = await self.get_logs_channel(guild.id)

        if not channel:
            return

        em = discord.Embed(
            title="Member banned",
            color=self.bot.failed,
            timestamp=datetime.datetime.utcnow()
        )

        em.add_field(name="Reason", value=discord.AuditLogAction.ban, inline=False)

        em.set_author(name=user, icon_url=user.avatar.url)
        em.set_footer(text=f"User ID: {user.id}")

        await channel.send(embed=em)  # type: ignore

    @Cog.listener()
    async def on_member_unban(self, guild, user):
        channel = await self.get_logs_channel(guild.id)

        if not channel:
            return

        em = discord.Embed(
            title="Member unbanned",
            color=self.bot.success,
            timestamp=datetime.datetime.utcnow()
        )

        em.add_field(name="Reason", value=discord.AuditLogAction.unban, inline=False)

        em.set_author(name=user, icon_url=user.avatar.url)
        em.set_footer(text=f"User ID: {user.id}")

        await channel.send(embed=em)  # type: ignore

    @Cog.listener(name="on_member_update")
    async def member_role_update(self, before, after):
        channel = await self.get_logs_channel(before.guild.id)
        roles = []
        role_text = ""

        if not channel:
            return

        if before.roles == after.roles:
            return

        if len(before.roles) > len(after.roles):
            for e in before.roles:
                if e not in after.roles:
                    roles.append(e)

        else:
            for e in after.roles:
                if e not in before.roles:
                    roles.append(e)

        for h in roles:
            role_text += f"`{h.name}`, "
        role_text = role_text[:-2]

        em = discord.Embed(
            description=f"Role{'s' if len(roles) > 1 else ''} {role_text} "
                        f"{'were' if len(roles) > 1 else 'was'} "
                        f"{'added to' if len(before.roles) < len(after.roles) else 'removed from'} "
                        f"{after.mention}",
            color=self.bot.color,
            timestamp=datetime.datetime.utcnow(),
        )
        em.set_author(name=after, icon_url=after.display_avatar.url)
        em.set_footer(text=f"ID: {after.id}")

        await channel.send(embed=em)  # type: ignore

    @Cog.listener("on_member_update")
    async def member_nickname_update(self, before, after):
        channel = await self.get_logs_channel(before.guild.id)

        if not channel:
            return

        if before.nick == after.nick:
            return

        em = discord.Embed(
            title="Nickname updated",
            description=f"`{before.nick}` ➜ `{after.nick}`",
            color=self.bot.color,
            timestamp=datetime.datetime.utcnow()
        )
        em.set_author(name=after, icon_url=after.display_avatar.url)
        em.set_footer(text=f"ID: {after.id}")

        await channel.send(embed=em)  # type: ignore

# ====== ROLE LOGS ======

    @Cog.listener()
    async def on_guild_role_create(self, role):
        channel = await self.get_logs_channel(role.guild.id)

        if not channel:
            return

        em = discord.Embed(
            title="New role created",
            color=self.bot.success,
            timestamp=role.created_at
        )
        em.add_field(name="Name", value=role.name, inline=False)
        em.add_field(name="Color", value=role.color, inline=False)
        em.set_footer(text=f"Role ID: {role.id}")

        await channel.send(embed=em)  # type: ignore

    @Cog.listener()
    async def on_guild_role_delete(self, role):
        channel = await self.get_logs_channel(role.guild.id)

        if not channel:
            return

        em = discord.Embed(
            title="Role deleted",
            color=self.bot.failed,
            timestamp=datetime.datetime.utcnow()
        )
        em.add_field(name="Name", value=role.name, inline=False)
        em.add_field(name="Color", value=role.color, inline=False)
        em.set_footer(text=f"Role ID: {role.id}")

        await channel.send(embed=em)  # type: ignore

    @Cog.listener(name="on_guild_role_update")
    async def guild_role_update(self, before, after):
        channel = await self.get_logs_channel(before.guild.id)

        if not channel:
            return

        if before.position - after.position in [1, -1]:
            return

        em = discord.Embed(
            title="Role updated",
            color=self.bot.color,
            timestamp=after.created_at
        )

        if before.name != after.name:
            em.add_field(name="Name", value=f"{before.name} ➜ {after.name}", inline=False)

        if before.color != after.color:
            em.add_field(name="Color", value=f"{before.color} ➜ {after.color}", inline=False)

        if before.hoist != after.hoist:
            em.add_field(name="Hoisted", value=f"{before.hoist} ➜ {after.hoist}", inline=False)

        if before.mentionable != after.mentionable:
            em.add_field(name="Mentionable", value=f"{before.mentionable} ➜ {after.mentionable}", inline=False)

        if before.position != after.position:
            em.add_field(name="Position", value=f"{before.position} ➜ {after.position}", inline=False)

        if before.permissions != after.permissions:
            all_perms = ""

            before_perms = {}
            after_perms = {}

            for b, B in before.permissions:
                before_perms.update({b: B})

            for a, A in after.permissions:
                after_perms.update({a: A})

            for g in before_perms:
                if before_perms[g] != after_perms[g]:
                    all_perms += f"**{' '.join(g.split('_')).title()}:** {before_perms[g]} ➜ {after_perms[g]}\n"

            em.add_field(name="Permissions", value=all_perms, inline=False)

        em.set_footer(text=f"Role ID: {before.id}")

        await channel.send(embed=em)  # type: ignore

# ===== GUILD LOGS =====

    @Cog.listener("on_guild_update")
    async def guild_update_log(self, before, after):
        channel = await self.get_logs_channel(before.guild.id)

        if not channel:
            return

        em = discord.Embed(
            title="Server updated",
            color=self.bot.color,
            timestamp=datetime.datetime.utcnow()
        )
            
        em.set_author(name=after, icon_url=after.icon.url)
        em.set_footer(text=f"ID: {after.id}")

        if before.afk_channel != after.afk_channel:
            em.add_field(
                name="AFK Channel",
                value=f"`{before.afk_channel}` ➜ `{after.afk_channel}`",
                inline=False
            )

        if before.afk_timeout != after.afk_timeout:
            em.add_field(
                name="AFK Timeout",
                value=f"`{format_timespan(before.afk_timeout)}` ➜ `{format_timespan(after.afk_timeout)}`",
                inline=False
            )

        if before.banner != after.banner:
            em.add_field(
                name="Banner updated!",
                value=f"{'`None`' if before.banner is None else '[`Before`]('+str(before.banner.url)+')'} ➜ {'`None`' if after.banner is None else '[`After`]('+str(after.banner.url)+')'}",
                inline=False
            )

        if before.default_notifications != after.default_notifications:
            em.add_field(
                name="Default Notifications",
                value=f"`{before.default_notifications}` ➜ `{after.default_notifications}`",
                inline=False
            )

        if before.description != after.description:
            em.add_field(
                name="Description",
                value=f"```{before.description}``` ➜ ```{after.description}```",
                inline=False
            )

        if before.icon != after.icon:
            em.add_field(
                name="Icon",
                value=f"{'`None`' if before.icon is None else '[`Before`]('+str(before.icon.url)+')'} ➜ {'`None`' if after.icon is None else '[`After`]('+str(after.icon.url)+')'}",
                inline=False
            )

        if before.mfa_level != after.mfa_level:
            em.add_field(
                name="2FA Requirement",
                value=f"`{'True' if before.mfa_level == 1 else 'False'}` ➜ `{'True' if after.mfa_level == 1 else 'False'}`",
                inline=False
            )

        if before.name != after.name:
            em.add_field(
                name="Name",
                value=f"`{before.name}` ➜ `{after.name}`",
                inline=False
            )

        if before.owner != after.owner:
            em.add_field(
                name="Owner",
                value=f"`{before.owner}` ➜ `{after.owner}`",
                inline=False
            )

        if before.public_updates_channel != after.public_updates_channel:
            em.add_field(
                name="New community updates channel",
                value=f"`{before.public_updates_channel}` ➜ `{after.public_updates_channel}`",
                inline=False
            )

        if before.region != after.region:
            em.add_field(
                name="Region",
                value=f"`{before.region}` ➜ `{after.region}`",
                inline=False
            )

        if before.rules_channel != after.rules_channel:
            em.add_field(
                name="Rules channel",
                value=f"`{before.rules_channel}` ➜ `{after.rules_channel}`",
                inline=False
            )

        if before.splash != after.splash:
            em.add_field(
                name="Invite splash banner",
                value=f"{'`None`' if before.splash is None else '[`Before`]('+str(before.splash.url)+')'} ➜ {'`None`' if after.splash is None else '[`After`]('+str(after.splash.url)+')'}",
                inline=False
            )

        if before.system_channel != after.system_channel:
            em.add_field(
                name="System channel",
                value=f"`{before.system_channel}` ➜ `{after.system_channel}`",
                inline=False
            )

        await channel.send(embed=em)  # type: ignore
    
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
        em.add_field(name="Owner", value=guild.owner, inline=False)

        channel = self.bot.get_channel(LOG_CHANNEL)
        await channel.send(embed=em)  # type: ignore

    @Cog.listener()
    async def on_guild_remove(self, guild):
        await self.bot.db.execute("DELETE FROM modlogs WHERE guild_id=$1", guild.id)  # type: ignore

        channel = self.bot.get_channel(LOG_CHANNEL)
        await channel.send(f"Left {guild.name}")  # type: ignore
            

async def setup(bot):
    await bot.add_cog(Events(bot))
