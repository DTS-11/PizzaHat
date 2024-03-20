import datetime
import os
from typing import List, Union

import discord
from async_lru import alru_cache
from cogs.utility import format_date
from core.bot import PizzaHat
from core.cog import Cog
from dotenv import load_dotenv
from humanfriendly import format_timespan

load_dotenv()

LOG_CHANNEL = 980151632199299092
DLIST_TOKEN = os.getenv("DLIST_AUTH")


class Events(Cog):
    """Events cog"""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot
        # bot.loop.create_task(self.update_stats())

    @alru_cache()
    async def get_logs_channel(self, guild_id: int) -> Union[discord.TextChannel, None]:
        return (
            await self.bot.db.fetchval(
                "SELECT channel_id FROM modlogs WHERE guild_id=$1", guild_id
            )
            if self.bot.db
            else None
        )

    @alru_cache()
    async def get_starboard_config(self, guild_id: int) -> Union[dict, None]:
        data = (
            await self.bot.db.fetchrow(
                "SELECT channel_id, star_count, self_star FROM star_config WHERE guild_id=$1",
                guild_id,
            )
            if self.bot.db
            else None
        )

        return (
            {
                "channel_id": data["channel_id"],
                "star_count": data["star_count"],
                "self_star": data["self_star"],
            }
            if data
            else None
        )

    # @tasks.loop(hours=24)
    # async def update_stats(self):
    #     try:
    #         # Top.gg
    #         await self.bot.wait_until_ready()
    #         self.topggpy = topgg.DBLClient(self, os.getenv("DBL_TOKEN"), autopost=True)  # type: ignore
    #         await self.topggpy.post_guild_count()
    #         print(f"Posted server count: {self.topggpy.guild_count}")

    #     except Exception as e:
    #         print(f"Failed to post server count\n{e.__class__.__name__}: {e}")

    #     try:
    #         # DList.gg
    #         url = f"https://api.discordlist.gg/v0/bots/860889936914677770/guilds?count={len(self.bot.guilds)}"
    #         headers = {'Authorization': f"Bearer {DLIST_TOKEN}", "Content-Type": "application/json"}
    #         r = requests.put(url, headers=headers)
    #         print(r.json())

    #     except Exception as e:
    #         print(e)

    @Cog.listener()
    async def on_ready(self):
        if self.bot.db is not None:
            await self.bot.db.execute(
                """CREATE TABLE IF NOT EXISTS afk 
                (guild_id BIGINT, user_id BIGINT, reason TEXT)"""
            )

            await self.bot.db.execute(
                """CREATE TABLE IF NOT EXISTS warnlogs 
                (id SERIAL PRIMARY KEY, guild_id BIGINT, user_id BIGINT, mod_id BIGINT, reason TEXT)"""
            )

            await self.bot.db.execute(
                """CREATE TABLE IF NOT EXISTS modlogs 
                (guild_id BIGINT PRIMARY KEY, channel_id BIGINT)"""
            )

            await self.bot.db.execute(
                """CREATE TABLE IF NOT EXISTS automod 
                (guild_id BIGINT PRIMARY KEY, enabled BOOL DEFAULT false)"""
            )

            await self.bot.db.execute(
                """CREATE TABLE IF NOT EXISTS antialt 
                (guild_id BIGINT PRIMARY KEY, enabled BOOL DEFAULT false, min_age INT, restricted_role BIGINT, level INT)"""
            )

            await self.bot.db.execute(
                """CREATE TABLE IF NOT EXISTS staff_role 
                (guild_id BIGINT PRIMARY KEY, role_id BIGINT)"""
            )

            await self.bot.db.execute(
                """CREATE TABLE IF NOT EXISTS tags 
                (guild_id BIGINT PRIMARY KEY, tag_name TEXT, content TEXT, creator BIGINT)"""
            )

            await self.bot.db.execute(
                """CREATE TABLE IF NOT EXISTS star_config 
                (guild_id BIGINT PRIMARY KEY, channel_id BIGINT, star_count INT DEFAULT 5, self_star BOOL DEFAULT true)"""
            )

            await self.bot.db.execute(
                """CREATE TABLE IF NOT EXISTS star_info 
                (guild_id BIGINT, user_msg_id BIGINT PRIMARY KEY, bot_msg_id BIGINT)"""
            )

    # ====== MESSAGE LOGS ======

    @Cog.listener()
    async def on_message(self, msg: discord.Message):
        if self.bot and self.bot.user is not None:
            bot_id = self.bot.user.id

            if msg.author.bot:
                return

            if self.bot.user == msg.author:
                return

            if msg.content in {f"<@{bot_id}>" or f"<@!{bot_id}>"}:
                em = discord.Embed(color=self.bot.color)
                em.add_field(
                    name="Hello! <a:wave_animated:783393435242463324>",
                    value=f"I'm {self.bot.user.name} — Your Ultimate Discord Companion.\nTo get started, my prefix is `p!` or `P!` or <@{bot_id}>",
                )

                await msg.channel.send(embed=em)

    @Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        channel = await self.get_logs_channel(before.guild.id) if before.guild else None

        if not channel:
            return

        if before.author.bot:
            return

        if before.content == after.content:
            return

        em = discord.Embed(
            title=f"Message edited in #{before.channel}",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(),
        )
        em.add_field(name="- Before", value=before.content, inline=False)
        em.add_field(name="+ After", value=after.content, inline=False)
        em.set_author(
            name=before.author,
            icon_url=before.author.avatar.url if before.author.avatar else None,
        )
        em.set_footer(text=f"User ID: {before.author.id}")

        await channel.send(embed=em)

    @Cog.listener()
    async def on_message_delete(self, msg: discord.Message):
        channel = await self.get_logs_channel(msg.guild.id) if msg.guild else None

        if not channel:
            return

        if msg.author.bot:
            return

        em = discord.Embed(
            title=f"Message deleted in #{msg.channel}",
            description=msg.content,
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(),
        )
        em.set_author(
            name=msg.author,
            icon_url=msg.author.avatar.url if msg.author.avatar else None,
        )
        em.set_footer(text=f"User ID: {msg.author.id}")

        await channel.send(embed=em)

    @Cog.listener()
    async def on_bulk_message_delete(self, msgs: List[discord.Message]):
        channel = (
            await self.get_logs_channel(msgs[0].guild.id) if msgs[0].guild else None
        )

        if not channel:
            return

        em = discord.Embed(
            title="Bulk message deleted",
            description=f"**{len(msgs)}** messages deleted in {msgs[0].channel}",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(),
        )
        em.set_author(
            name=msgs[0].author,
            icon_url=msgs[0].author.avatar.url if msgs[0].author.avatar else None,
        )
        em.set_footer(text=f"User ID: {msgs[0].author.id}")

        await channel.send(embed=em)

    # ====== MEMBER LOGS ======

    @Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        channel = await self.get_logs_channel(guild.id)

        if not channel:
            return

        em = discord.Embed(
            title="Member banned",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(),
        )

        em.add_field(name="Reason", value=discord.AuditLogAction.ban, inline=False)

        em.set_author(name=user, icon_url=user.avatar.url if user.avatar else None)
        em.set_footer(text=f"User ID: {user.id}")

        await channel.send(embed=em)

    @Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        channel = await self.get_logs_channel(guild.id)

        if not channel:
            return

        em = discord.Embed(
            title="Member unbanned",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(),
        )

        em.add_field(name="Reason", value=discord.AuditLogAction.unban, inline=False)
        em.set_author(name=user, icon_url=user.avatar.url if user.avatar else None)
        em.set_footer(text=f"User ID: {user.id}")

        await channel.send(embed=em)

    @Cog.listener(name="on_member_update")
    async def member_role_update(self, before: discord.Member, after: discord.Member):
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
            timestamp=datetime.datetime.now(),
        )
        em.set_author(
            name=after,
            icon_url=after.display_avatar.url if after.display_avatar else None,
        )
        em.set_footer(text=f"ID: {after.id}")

        await channel.send(embed=em)

    @Cog.listener(name="on_member_update")
    async def member_nickname_update(
        self, before: discord.Member, after: discord.Member
    ):
        channel = await self.get_logs_channel(before.guild.id)

        if not channel:
            return

        if before.nick == after.nick:
            return

        em = discord.Embed(
            title="Nickname updated",
            description=f"`{before.nick}` ➜ `{after.nick}`",
            color=self.bot.color,
            timestamp=datetime.datetime.now(),
        )
        em.set_author(
            name=after,
            icon_url=after.display_avatar.url if after.display_avatar else None,
        )
        em.set_footer(text=f"ID: {after.id}")

        await channel.send(embed=em)

    # ====== ROLE LOGS ======

    @Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        channel = await self.get_logs_channel(role.guild.id)

        if not channel:
            return

        em = discord.Embed(
            title="New role created",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(),
        )
        em.add_field(name="Name", value=role.name, inline=False)
        em.add_field(name="Color", value=role.color, inline=False)
        em.set_footer(text=f"Role ID: {role.id}")

        await channel.send(embed=em)

    @Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        channel = await self.get_logs_channel(role.guild.id)

        if not channel:
            return

        em = discord.Embed(
            title="Role deleted",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(),
        )
        em.add_field(name="Name", value=role.name, inline=False)
        em.add_field(name="Color", value=role.color, inline=False)
        em.set_footer(text=f"Role ID: {role.id}")

        await channel.send(embed=em)

    @Cog.listener(name="on_guild_role_update")
    async def guild_role_update(self, before: discord.Role, after: discord.Role):
        channel = await self.get_logs_channel(before.guild.id)

        if not channel:
            return

        if before.position - after.position in [1, -1]:
            return

        em = discord.Embed(
            title="Role updated",
            color=self.bot.color,
            timestamp=datetime.datetime.now(),
        )

        if before.name != after.name:
            em.add_field(
                name="Name", value=f"{before.name} ➜ {after.name}", inline=False
            )

        if before.color != after.color:
            em.add_field(
                name="Color", value=f"{before.color} ➜ {after.color}", inline=False
            )

        if before.hoist != after.hoist:
            em.add_field(
                name="Hoisted", value=f"{before.hoist} ➜ {after.hoist}", inline=False
            )

        if before.mentionable != after.mentionable:
            em.add_field(
                name="Mentionable",
                value=f"{before.mentionable} ➜ {after.mentionable}",
                inline=False,
            )

        if before.position != after.position:
            em.add_field(
                name="Position",
                value=f"{before.position} ➜ {after.position}",
                inline=False,
            )

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

        await channel.send(embed=em)

    # ===== GUILD LOGS =====

    @Cog.listener(name="on_guild_update")
    async def guild_update_log(self, before: discord.Guild, after: discord.Guild):
        channel = await self.get_logs_channel(before.id)

        if not channel:
            return

        em = discord.Embed(
            title="Server updated",
            color=self.bot.color,
            timestamp=datetime.datetime.now(),
        )

        em.set_author(name=after, icon_url=after.icon.url if after.icon else None)
        em.set_footer(text=f"ID: {after.id}")

        if before.afk_channel != after.afk_channel:
            em.add_field(
                name="AFK Channel",
                value=f"`{before.afk_channel}` ➜ `{after.afk_channel}`",
                inline=False,
            )

        if before.afk_timeout != after.afk_timeout:
            em.add_field(
                name="AFK Timeout",
                value=f"`{format_timespan(before.afk_timeout)}` ➜ `{format_timespan(after.afk_timeout)}`",
                inline=False,
            )

        if before.banner != after.banner:
            em.add_field(
                name="Banner updated!",
                value=f"{'`None`' if before.banner is None else '[`Before`]('+str(before.banner.url)+')'} ➜ {'`None`' if after.banner is None else '[`After`]('+str(after.banner.url)+')'}",
                inline=False,
            )

        if before.default_notifications != after.default_notifications:
            em.add_field(
                name="Default Notifications",
                value=f"`{before.default_notifications}` ➜ `{after.default_notifications}`",
                inline=False,
            )

        if before.description != after.description:
            em.add_field(
                name="Description",
                value=f"```{before.description}``` ➜ ```{after.description}```",
                inline=False,
            )

        if before.icon != after.icon:
            em.add_field(
                name="Icon",
                value=f"{'`None`' if before.icon is None else '[`Before`]('+str(before.icon.url)+')'} ➜ {'`None`' if after.icon is None else '[`After`]('+str(after.icon.url)+')'}",
                inline=False,
            )

        if before.mfa_level != after.mfa_level:
            em.add_field(
                name="2FA Requirement",
                value=f"`{'True' if before.mfa_level == 1 else 'False'}` ➜ `{'True' if after.mfa_level == 1 else 'False'}`",
                inline=False,
            )

        if before.name != after.name:
            em.add_field(
                name="Name", value=f"`{before.name}` ➜ `{after.name}`", inline=False
            )

        if before.owner != after.owner:
            em.add_field(
                name="Owner", value=f"`{before.owner}` ➜ `{after.owner}`", inline=False
            )

        if before.public_updates_channel != after.public_updates_channel:
            em.add_field(
                name="New community updates channel",
                value=f"`{before.public_updates_channel}` ➜ `{after.public_updates_channel}`",
                inline=False,
            )

        if before.rules_channel != after.rules_channel:
            em.add_field(
                name="Rules channel",
                value=f"`{before.rules_channel}` ➜ `{after.rules_channel}`",
                inline=False,
            )

        if before.splash != after.splash:
            em.add_field(
                name="Invite splash banner",
                value=f"{'`None`' if before.splash is None else '[`Before`]('+str(before.splash.url)+')'} ➜ {'`None`' if after.splash is None else '[`After`]('+str(after.splash.url)+')'}",
                inline=False,
            )

        if before.system_channel != after.system_channel:
            em.add_field(
                name="System channel",
                value=f"`{before.system_channel}` ➜ `{after.system_channel}`",
                inline=False,
            )

        await channel.send(embed=em)

    @Cog.listener()
    async def on_guild_emojis_update(
        self, guild: discord.Guild, before: discord.Emoji, after: discord.Emoji
    ):
        channel = await self.get_logs_channel(guild.id)

        if not channel:
            return

        em = discord.Embed(
            title="Emoji Updated",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(),
        )
        em.description = f"""
    > **Emoji ID:** {before.id}
    > **Guild ID:** {guild.id}
    > **Created by:** {before.user}
    > **Created at:** {format_date(before.created_at)}
    > **URL:** [Click here]({before.url})
        """

        if before.name != after.name:
            em.add_field(
                name="Name", value=f"{before.name} ➜ {after.name}", inline=False
            )

        if before.animated != after.animated:
            em.add_field(
                name="Animated",
                value=f"{before.animated} ➜ {after.animated}",
                inline=False,
            )

        if before.available != after.available:
            em.add_field(
                name="Available",
                value=f"{before.available} ➜ {after.available}",
                inline=False,
            )

        if before.is_usable() != after.is_usable():
            em.add_field(
                name="Usable",
                value=f"{before.is_usable()} ➜ {after.is_usable()}",
                inline=False,
            )

        if before.managed != after.managed:
            em.add_field(
                name="Managed",
                value=f"{before.managed} ➜ {after.managed}",
                inline=False,
            )

        if before.require_colons != after.require_colons:
            em.add_field(
                name="Colons Required",
                value=f"{before.require_colons} ➜ {after.require_colons}",
                inline=False,
            )

        await channel.send(embed=em)

    @Cog.listener()
    async def on_guild_stickers_update(
        self,
        guild: discord.Guild,
        before: discord.GuildSticker,
        after: discord.GuildSticker,
    ):
        channel = await self.get_logs_channel(guild.id)

        if not channel:
            return

        em = discord.Embed(
            title="Sticker Updated",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(),
        )
        em.description = f"""
    > **Sticker ID:** {before.id}
    > **Guild ID:** {guild.id}
    > **Format:** {after.format}
    > **Created by:** {before.user}
    > **Created at:** {format_date(before.created_at)}
    > **URL:** [Click here]({before.url})
        """

        if before.name != after.name:
            em.add_field(
                name="Name", value=f"{before.name} ➜ {after.name}", inline=False
            )

        if before.description != after.description:
            em.add_field(
                name="Description",
                value=f"{before.description} ➜ {after.description}",
                inline=False,
            )

        if before.available != after.available:
            em.add_field(
                name="Available",
                value=f"{before.available} ➜ {after.available}",
                inline=False,
            )

        if before.emoji != after.emoji:
            em.add_field(
                name="Emoji",
                value=f"{before.emoji} ➜ {after.emoji}",
                inline=False,
            )

        await channel.send(embed=em)

    @Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        # if len([m for m in guild.members if m.bot]) > len(guild.members) / 2:
        #     try:
        #         await guild.text_channels[0].send(
        #             '👋 I have automatically left this server since it has a high bot to member ratio.'
        #         )
        #         await guild.leave()
        #     except:
        #         pass

        em = discord.Embed(title="Guild Joined", color=discord.Color.green())
        em.add_field(name="Guild", value=guild.name, inline=False)
        em.add_field(
            name="Members",
            value=len([m for m in guild.members if not m.bot]),
            inline=False,
        )
        em.add_field(
            name="Bots", value=sum(member.bot for member in guild.members), inline=False
        )
        (
            em.add_field(
                name="Owner", value=f"{guild.owner} ({guild.owner.id})", inline=False
            )
            if guild and guild.owner
            else None
        )

        channel = self.bot.get_channel(LOG_CHANNEL)
        await channel.send(embed=em)  # type: ignore

    @Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        (
            await self.bot.db.execute("DELETE FROM modlogs WHERE guild_id=$1", guild.id)
            if self.bot.db
            else None
        )

        channel = self.bot.get_channel(LOG_CHANNEL)
        await channel.send(f"Left {guild.name}")  # type: ignore

    # ====== GUILD INTEGRATION EVENTS ======

    @Cog.listener()
    async def on_integration_create(self, integration: discord.Integration):
        channel = await self.get_logs_channel(integration.guild.id)

        if not channel:
            return

        em = discord.Embed(
            title="Integration Created",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(),
        )

        em.description = f"""
    > **ID:** {integration.id}
    > **Name:** {integration.name}
    > **Type:** {integration.type}
    > **Enabled**: {integration.enabled}
    > **Created by:** {integration.user}
    """

        em.set_footer(
            text=integration.user,
            icon_url=(
                integration.user.avatar.url
                if integration.user and integration.user.avatar
                else None
            ),
        )

        await channel.send(embed=em)

    @Cog.listener()
    async def on_integration_update(self, integration: discord.Integration):
        channel = await self.get_logs_channel(integration.guild.id)

        if not channel:
            return

        em = discord.Embed(
            title="Integration Updated",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(),
        )

        em.description = f"""
    > **ID:** {integration.id}
    > **Name:** {integration.name}
    > **Type:** {integration.type}
    > **Enabled**: {integration.enabled}
    > **Created by:** {integration.user}
    """

        em.set_footer(
            text=integration.user,
            icon_url=(
                integration.user.avatar.url
                if integration.user and integration.user.avatar
                else None
            ),
        )

        await channel.send(embed=em)

    @Cog.listener()
    async def on_raw_integration_delete(
        self, payload: discord.RawIntegrationDeleteEvent
    ):
        guild = self.bot.get_guild(payload.guild_id)
        channel = await self.get_logs_channel(payload.guild_id)

        if not channel:
            return

        em = discord.Embed(
            title="Integration Deleted",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(),
        )

        em.description = f"""
    > **Integration ID:** {payload.integration_id}
    > **Application ID:** {payload.application_id}
    > **Guild ID:** {payload.guild_id}
    """

        if guild:
            em.set_footer(
                text=guild.name,
                icon_url=(guild.icon.url if guild.icon else None),
            )

        await channel.send(embed=em)

    # ====== GUILD AUTOMOD LOGS ======
    @Cog.listener()
    async def on_automod_rule_create(self, rule: discord.AutoModRule):
        channel = await self.get_logs_channel(rule.guild.id)

        if not channel:
            return

        em = discord.Embed(
            title="New Automod Rule Created",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(),
        )
        em.description = f"""
    **Name and ID:** {rule.name} ({rule.id})
    **Creator:** {rule.creator} ({rule.creator_id})
    **Trigger(s):** {rule.trigger}
    **Action(s):** {rule.actions}
    **Enabled:** {rule.enabled}
    **Ignored Channels:** {rule.exempt_channels}
    **Ignored Roles:** {rule.exempt_roles}
        """

        em.set_thumbnail(url=rule.guild.icon.url if rule.guild.icon else None)
        await channel.send(embed=em)

    @Cog.listener()
    async def on_automod_rule_update(self, rule: discord.AutoModRule):
        channel = await self.get_logs_channel(rule.guild.id)

        if not channel:
            return

        em = discord.Embed(
            title="New Automod Rule Updated",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(),
        )
        em.description = f"""
    **Name and ID:** {rule.name} ({rule.id})
    **Creator:** {rule.creator} ({rule.creator_id})
    **Trigger(s):** {rule.trigger}
    **Action(s):** {rule.actions}
    **Enabled:** {rule.enabled}
    **Ignored Channels:** {rule.exempt_channels}
    **Ignored Roles:** {rule.exempt_roles}
        """

        em.set_thumbnail(url=rule.guild.icon.url if rule.guild.icon else None)
        await channel.send(embed=em)

    @Cog.listener()
    async def on_automod_rule_delete(self, rule: discord.AutoModRule):
        channel = await self.get_logs_channel(rule.guild.id)

        if not channel:
            return

        em = discord.Embed(
            title="New Automod Rule Deleted",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(),
        )
        em.description = f"""
    **Name and ID:** {rule.name} ({rule.id})
    **Creator:** {rule.creator} ({rule.creator_id})
    **Trigger(s):** {rule.trigger}
    **Action(s):** {rule.actions}
    **Enabled:** {rule.enabled}
    **Ignored Channels:** {rule.exempt_channels}
    **Ignored Roles:** {rule.exempt_roles}
        """

        em.set_thumbnail(url=rule.guild.icon.url if rule.guild.icon else None)
        await channel.send(embed=em)

    @Cog.listener()
    async def on_automod_action(self, execution: discord.AutoModAction):
        channel = await self.get_logs_channel(execution.guild_id)

        if not channel:
            return

        em = discord.Embed(
            title="Automod Action Taken",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(),
        )
        em.description = f"""
    **Action:** {execution.action}
    **Rule Trigger Type:** {execution.rule_trigger_type}
    **User:** {execution.member} ({execution.user_id})
    **Channel:** {execution.channel} ({execution.channel_id})
    **Message Content:** {execution.content}
    **Matched Keyword:** {execution.matched_keyword}
    **Matched Content:** {execution.matched_content}
    **System Alert Message ID:** {execution.alert_system_message_id}
    **Message ID:** {execution.message_id}
    **Rule ID:** {execution.rule_id}
        """

        em.set_thumbnail(url=execution.guild.icon.url if execution.guild.icon else None)
        await channel.send(embed=em)

    # ====== STARBOARD REACTION EVENTS ======

    @Cog.listener(name="on_raw_reaction_add")
    async def starboard_reaction_add(self, payload: discord.RawReactionActionEvent):
        guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
        channel = guild.get_channel(payload.channel_id) if guild else None
        message = await channel.fetch_message(payload.message_id)  # type: ignore

        if message.author.bot or payload.emoji.name != "⭐":
            return

        starboard_config = await self.get_starboard_config(guild.id) if guild else None

        if starboard_config is not None:
            star_channel = (
                guild.get_channel(starboard_config["channel_id"]) if guild else None
            )

            if not star_channel:
                return

            star_count = starboard_config["star_count"]
            self_star = starboard_config["self_star"]

            for reaction in message.reactions:
                if reaction.count >= star_count:
                    if not self_star:
                        if message.author == payload.member:
                            return await message.remove_reaction(payload.emoji, payload.member)  # type: ignore

                    em = discord.Embed(
                        description=message.content,
                        color=discord.Color.blurple(),
                        timestamp=datetime.datetime.now(),
                    )
                    em.set_footer(text=f"Message ID: {message.id}")

                    em.add_field(
                        name="Source",
                        value=f"[Jump to message!]({message.jump_url})",
                        inline=False,
                    )

                    for sticker in message.stickers:
                        em.add_field(
                            name=f"Sticker: `{sticker.name}`",
                            value=f"ID: [`{sticker.id}`]({sticker.url})",
                        )
                    if len(message.stickers) == 1:
                        em.set_thumbnail(url=message.stickers[0].url)

                    em.set_author(
                        name=message.author.name,
                        icon_url=(
                            message.author.avatar.url if message.author.avatar else None
                        ),
                    )
                    em.set_image(
                        url=(
                            message.attachments[0].url if message.attachments else None
                        )
                    )

                    try:
                        em_id = (
                            await self.bot.db.fetchval(
                                "SELECT bot_msg_id FROM star_info WHERE guild_id=$1 AND user_msg_id=$2",
                                guild.id,
                                payload.message_id,
                            )
                            if self.bot.db and guild
                            else None
                        )

                        if em_id is not None:
                            star_embed = await star_channel.fetch_message(em_id)  # type: ignore
                            await star_embed.edit(content=f"⭐ **{reaction.count}** | {channel.mention}", embed=em)  # type: ignore

                        else:
                            star_embed = await star_channel.send(content=f"⭐ **{reaction.count}** | {channel.mention}", embed=em)  # type: ignore
                        (
                            await self.bot.db.execute(
                                "INSERT INTO star_info (guild_id, user_msg_id, bot_msg_id) VALUES ($1, $2, $3) ON CONFLICT ON CONSTRAINT star_info_pkey DO NOTHING",
                                guild.id,
                                payload.message_id,
                                star_embed.id,
                            )
                            if guild and self.bot.db
                            else None
                        )

                    except discord.NotFound:
                        pass
                    except discord.Forbidden:
                        pass
                    except Exception as e:
                        print(f"Error in starboard reaction add: {e}")

    @Cog.listener(name="on_raw_reaction_remove")
    async def starboard_reaction_remove(self, payload: discord.RawReactionActionEvent):
        guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
        channel = guild.get_channel(payload.channel_id) if guild else None
        message = await channel.fetch_message(payload.message_id)  # type: ignore
        emoji = discord.utils.get(message.reactions, emoji="⭐")

        em_id = (
            await self.bot.db.fetchval(
                "SELECT bot_msg_id FROM star_info WHERE guild_id=$1 AND user_msg_id=$2",
                guild.id,
                payload.message_id,
            )
            if self.bot.db and guild
            else None
        )

        if message.author.bot:
            return

        starboard_config = await self.get_starboard_config(guild.id) if guild else None

        if starboard_config is not None:
            star_channel = (
                guild.get_channel(starboard_config["channel_id"]) if guild else None
            )

            if not star_channel:
                return

            if not emoji:
                msg = await star_channel.fetch_message(em_id)  # type:ignore
                await msg.delete()
                (
                    await self.bot.db.execute(
                        "DELETE FROM star_info WHERE guild_id=$1 AND bot_msg_id=$2",
                        guild.id,
                        em_id,
                    )
                    if self.bot.db and guild
                    else None
                )
                return

            star_count = starboard_config["star_count"]
            self_star = starboard_config["self_star"]

            try:
                for reaction in message.reactions:
                    if reaction.count < star_count:
                        if not self_star:
                            if message.author == payload.member:
                                return await message.remove_reaction(payload.emoji, payload.member)  # type: ignore

                        star_embed = await star_channel.fetch_message(em_id)  # type: ignore
                        await star_embed.edit(content=f"⭐ **{reaction.count}** | {channel.mention}")  # type: ignore

            # except discord.NotFound:
            #     pass
            # except discord.Forbidden:
            #     pass
            except Exception as e:
                print(f"Error in starboard reaction remove: {e}")

    @Cog.listener(name="on_message_delete")
    async def starred_msg_delete(self, msg: discord.Message):
        guild = msg.guild
        starboard_config = await self.get_starboard_config(guild.id) if guild else None
        star_info = (
            await self.bot.db.fetchrow(
                "SELECT user_msg_id, bot_msg_id FROM star_info WHERE guild_id=$1",
                guild.id,
            )
            if self.bot.db and guild
            else None
        )

        if starboard_config is not None:
            star_channel = (
                guild.get_channel(starboard_config["channel_id"]) if guild else None
            )

            if not star_channel:
                return

            if star_info is not None:
                try:
                    em_id = (
                        await self.bot.db.fetchval(
                            "SELECT bot_msg_id FROM star_info WHERE guild_id=$1 AND user_msg_id=$2",
                            guild.id,
                            msg.id,
                        )
                        if self.bot.db and guild
                        else None
                    )

                    star_embed = await star_channel.fetch_message(em_id)  # type: ignore
                    await star_embed.delete()
                    (
                        await self.bot.db.execute(
                            "DELETE FROM star_info WHERE guild_id=$1 AND bot_msg_id=$2",
                            guild.id,
                            em_id,
                        )
                        if self.bot.db and guild
                        else None
                    )

                except discord.NotFound:
                    pass
                except discord.Forbidden:
                    pass
                except Exception as e:
                    print(f"Error in starboard msg delete event: {e}")

    # ====== MEMBER PING - AFK EVENT ======
    @Cog.listener(name="on_message")
    async def member_ping_in_afk(self, msg: discord.Message):
        if msg.author.bot or not msg.guild:
            return

        data = (
            await self.bot.db.fetch(
                "SELECT reason FROM afk WHERE guild_id=$1 AND user_id=$2", msg.guild.id, msg.author.id
            )
            if self.bot.db
            else None
        )

        if data:
            (
                await self.bot.db.execute(
                    "DELETE FROM afk WHERE user_id=$1 AND guild_id=$2",
                    msg.author.id,
                    msg.guild.id,
                )
                if self.bot.db
                else None
            )
            return await msg.channel.send(
                f"Welcome back {msg.author.mention}.\nI have removed your AFK status."
            )

        if msg.mentions:
            for mention in msg.mentions:
                d2 = (
                    await self.bot.db.fetch(
                        "SELECT reason FROM afk WHERE guild_id=$1 AND user_id=$2",
                        msg.guild.id,
                        mention.id,
                    )
                    if self.bot.db
                    else None
                )

                if d2 and mention.id != msg.author.id:
                    em = discord.Embed(
                        title="Member AFK",
                        description=f"{mention.name} is AFK\n**Reason:** {d2[0]['reason']}",
                        color=discord.Color.og_blurple(),
                        timestamp=msg.created_at,
                    )
                    em.set_author(
                        name=mention.name,
                        icon_url=mention.avatar.url if mention.avatar else None,
                    )
                    em.set_footer(
                        text=msg.author,
                        icon_url=msg.author.avatar.url if msg.author.avatar else None,
                    )

                    await msg.channel.send(embed=em)


async def setup(bot):
    await bot.add_cog(Events(bot))
