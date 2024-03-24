import datetime
from typing import List, Union

import discord
from async_lru import alru_cache
from cogs.utility import format_date
from core.bot import PizzaHat
from core.cog import Cog
from discord.utils import escape_markdown
from humanfriendly import format_timespan


class GuildLogs(Cog):
    """Log everything in your server!"""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot

    @alru_cache()
    async def get_logs_channel(self, guild_id: int) -> Union[discord.TextChannel, None]:
        if self.bot.db is not None:
            return await self.bot.db.fetchval(
                "SELECT channel_id FROM guild_logs WHERE guild_id=$1", guild_id
            )

    @alru_cache()
    async def check_log_enabled(
        self, guild_id: int, module_type: str
    ) -> Union[bool, None]:
        if self.bot.db is not None:
            modules = await self.bot.db.fetchval(
                "SELECT module FROM logs_config WHERE guild_id=$1", guild_id
            )
            if modules is not None:
                if "all" in modules:
                    return True
                elif module_type.lower() in modules:
                    return True
        return False

    # ====== MESSAGE LOGS ======

    @Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or not after.guild:
            return

        channel = await self.get_logs_channel(before.guild.id)
        should_log_all = await self.check_log_enabled(before.guild.id, "all")
        should_log_messages = await self.check_log_enabled(before.guild.id, "messages")

        if not channel:
            return

        if before.author.bot:
            return

        if before.content == after.content:
            return

        if should_log_all or should_log_messages:
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
        if not msg.guild:
            return

        channel = await self.get_logs_channel(msg.guild.id)
        should_log_all = await self.check_log_enabled(msg.guild.id, "all")
        should_log_messages = await self.check_log_enabled(msg.guild.id, "messages")

        if not channel:
            return

        if msg.author.bot:
            return

        if should_log_all or should_log_messages:
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
        if not msgs[0].guild:
            return

        channel = await self.get_logs_channel(msgs[0].guild.id)
        should_log_all = await self.check_log_enabled(msgs[0].guild.id, "all")
        should_log_messages = await self.check_log_enabled(msgs[0].guild.id, "messages")

        if not channel:
            return

        if should_log_all or should_log_messages:
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
        should_log_all = await self.check_log_enabled(guild.id, "all")
        should_log_mod = await self.check_log_enabled(guild.id, "mod")

        if not channel:
            return

        if should_log_all or should_log_mod:
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
        should_log_all = await self.check_log_enabled(guild.id, "all")
        should_log_mod = await self.check_log_enabled(guild.id, "mod")

        if not channel:
            return

        if should_log_all or should_log_mod:
            em = discord.Embed(
                title="Member unbanned",
                color=discord.Color.green(),
                timestamp=datetime.datetime.now(),
            )

            em.add_field(
                name="Reason", value=discord.AuditLogAction.unban, inline=False
            )
            em.set_author(name=user, icon_url=user.avatar.url if user.avatar else None)
            em.set_footer(text=f"User ID: {user.id}")

            await channel.send(embed=em)

    @Cog.listener(name="on_member_update")
    async def member_role_update(self, before: discord.Member, after: discord.Member):
        channel = await self.get_logs_channel(before.guild.id)
        should_log_all = await self.check_log_enabled(before.guild.id, "all")
        should_log_member = await self.check_log_enabled(before.guild.id, "member")
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

        if should_log_all or should_log_member:
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
        should_log_all = await self.check_log_enabled(before.guild.id, "all")
        should_log_member = await self.check_log_enabled(before.guild.id, "member")

        if not channel:
            return

        if before.nick == after.nick:
            return

        if should_log_all or should_log_member:
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

    # ====== VOICE CHANNEL LOGS ======

    @Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        channel = await self.get_logs_channel(member.guild.id)
        should_log_all = await self.check_log_enabled(member.guild.id, "all")
        should_log_voice = await self.check_log_enabled(member.guild.id, "voice")

        if not channel:
            return

        if should_log_all or should_log_voice:
            em = discord.Embed(
                title="Voice State Update", timestamp=datetime.datetime.now()
            )
            em.set_author(
                name=member, icon_url=member.avatar.url if member.avatar else None
            )
            em.set_footer(text=f"ID: {member.id}")

            if before.channel is None:
                em.description = f"{member.mention} joined voice channel {after.channel.mention}"  # type: ignore
                em.color = discord.Color.green()

            elif after.channel is None:
                em.description = (
                    f"{member.mention} left voice channel {before.channel.mention}"
                )
                em.color = discord.Color.red()

            else:
                em.description = f"{member.mention} moved from {before.channel.mention} to {after.channel.mention}"
                em.color = discord.Color.orange()

            await channel.send(embed=em)

    # ====== GUILD ROLE LOGS ======

    @Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        channel = await self.get_logs_channel(role.guild.id)
        should_log_all = await self.check_log_enabled(role.guild.id, "all")
        should_log_role = await self.check_log_enabled(role.guild.id, "roles")

        if not channel:
            return

        if should_log_all or should_log_role:
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
        should_log_all = await self.check_log_enabled(role.guild.id, "all")
        should_log_role = await self.check_log_enabled(role.guild.id, "roles")

        if not channel:
            return

        if should_log_all or should_log_role:
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
        should_log_all = await self.check_log_enabled(before.guild.id, "all")
        should_log_role = await self.check_log_enabled(before.guild.id, "roles")

        if not channel:
            return

        if before.position - after.position in [1, -1]:
            return

        if should_log_all or should_log_role:
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
                    name="Hoisted",
                    value=f"{before.hoist} ➜ {after.hoist}",
                    inline=False,
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
        should_log_all = await self.check_log_enabled(before.id, "all")
        should_log_guild = await self.check_log_enabled(before.id, "guild")

        if not channel:
            return

        if should_log_all or should_log_guild:
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
                    name="Owner",
                    value=f"`{before.owner}` ➜ `{after.owner}`",
                    inline=False,
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
        should_log_all = await self.check_log_enabled(guild.id, "all")
        should_log_guild = await self.check_log_enabled(guild.id, "guild")

        if not channel:
            return

        if should_log_all or should_log_guild:
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
        should_log_all = await self.check_log_enabled(guild.id, "all")
        should_log_guild = await self.check_log_enabled(guild.id, "guild")

        if not channel:
            return

        if should_log_all or should_log_guild:
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

    # ====== GUILD INTEGRATION EVENTS ======

    @Cog.listener()
    async def on_integration_create(self, integration: discord.Integration):
        channel = await self.get_logs_channel(integration.guild.id)
        should_log_all = await self.check_log_enabled(integration.guild.id, "all")
        should_log_integrations = await self.check_log_enabled(
            integration.guild.id, "integrations"
        )

        if not channel:
            return

        if not should_log_all and not should_log_integrations:
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
        should_log_all = await self.check_log_enabled(integration.guild.id, "all")
        should_log_integrations = await self.check_log_enabled(
            integration.guild.id, "integrations"
        )

        if not channel:
            return

        if should_log_all or should_log_integrations:
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
        should_log_all = await self.check_log_enabled(payload.guild_id, "all")
        should_log_integrations = await self.check_log_enabled(
            payload.guild_id, "integrations"
        )

        if not channel:
            return

        if should_log_all or should_log_integrations:
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
        should_log_all = await self.check_log_enabled(rule.guild.id, "all")
        should_log_automod = await self.check_log_enabled(rule.guild.id, "automod")

        if not channel:
            return

        if should_log_all or should_log_automod:
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
        should_log_all = await self.check_log_enabled(rule.guild.id, "all")
        should_log_automod = await self.check_log_enabled(rule.guild.id, "automod")

        if not channel:
            return

        if should_log_all or should_log_automod:
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
        should_log_all = await self.check_log_enabled(rule.guild.id, "all")
        should_log_automod = await self.check_log_enabled(rule.guild.id, "automod")

        if not channel:
            return

        if should_log_all or should_log_automod:
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
        should_log_all = await self.check_log_enabled(execution.guild_id, "all")
        should_log_automod = await self.check_log_enabled(execution.guild_id, "automod")

        if not channel:
            return

        if should_log_all or should_log_automod:
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

            em.set_thumbnail(
                url=execution.guild.icon.url if execution.guild.icon else None
            )
            await channel.send(embed=em)

    # ====== GUILD INVITE LOGS ======

    @Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if invite.guild is None:
            return

        channel = await self.get_logs_channel(invite.guild.id)
        should_log_all = await self.check_log_enabled(invite.guild.id, "all")
        should_log_invites = await self.check_log_enabled(invite.guild.id, "invites")

        if not channel:
            return

        if should_log_all or should_log_invites:
            em = discord.Embed(
                title="Invite Created",
                color=discord.Color.green(),
                timestamp=invite.created_at,
            )
            em.add_field(name="Invite Code", value=invite.code, inline=False)
            em.add_field(name="Created By", value=invite.inviter, inline=False)
            em.add_field(name="Invite Expiry", value=invite.expires_at, inline=False)
            em.add_field(name="Invite Channel", value=invite.channel, inline=False)
            em.add_field(
                name="Max Invite Uses",
                value="Unlimited" if invite.max_uses == 0 else invite.max_uses,
                inline=False,
            )

            if invite.inviter:
                em.set_author(
                    name=invite.inviter,
                    icon_url=(
                        invite.inviter.avatar.url if invite.inviter.avatar else None
                    ),
                )
            em.set_footer(text=f"ID: {invite.id}")

            await channel.send(embed=em)

    @Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        if invite.guild is None:
            return

        channel = await self.get_logs_channel(invite.guild.id)
        should_log_all = await self.check_log_enabled(invite.guild.id, "all")
        should_log_invites = await self.check_log_enabled(invite.guild.id, "invites")

        if not channel:
            return

        if should_log_all or should_log_invites:
            em = discord.Embed(
                title="Invite Deleted",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now(),
            )
            em.description = f"> **Invite Code:** {invite.code}"

            if invite.inviter:
                em.set_author(
                    name=invite.inviter,
                    icon_url=(
                        invite.inviter.avatar.url if invite.inviter.avatar else None
                    ),
                )
            em.set_footer(text=f"ID: {invite.id}")

            await channel.send(embed=em)

    # ====== MEMBER JOIN/LEAVE LGOS ======

    @Cog.listener(name="on_member_join")
    async def send_join_log(self, member: discord.Member):
        channel = await self.get_logs_channel(self, member.guild.id)
        should_log_all = await self.check_log_enabled(member.guild.id, "all")
        should_log_joins = await self.check_log_enabled(member.guild.id, "joins")

        if not channel:
            return

        if should_log_all or should_log_joins:
            em = discord.Embed(
                description=f"{member.mention} {escape_markdown(str(member))}",
                color=self.bot.color,
                timestamp=member.joined_at,
            )
            em.set_author(
                name="Member Joined!",
                icon_url=member.avatar.url if member.avatar else None,
            )
            em.set_footer(text=f"ID: {member.id}")
            em.set_thumbnail(url=member.avatar.url if member.avatar else None)
            em.add_field(
                name="Account Age",
                value=format_timespan(
                    (
                        datetime.datetime.now(datetime.timezone.utc)
                        - member.created_at.replace(tzinfo=None)
                    ).total_seconds()
                ),
                inline=False,
            )

            await channel.send(embed=em)

    @Cog.listener(name="on_member_leave")
    async def send_leave_log(self, member: discord.Member):
        channel = await self.get_logs_channel(member.guild.id)
        should_log_all = await self.check_log_enabled(member.guild.id, "all")
        should_log_joins = await self.check_log_enabled(member.guild.id, "joins")

        if not channel:
            return

        if should_log_all or should_log_joins:
            em = discord.Embed(
                description=f"{member.mention} {escape_markdown(str(member))}",
                color=self.bot.color,
                timestamp=datetime.datetime.now(),
            )
            em.set_author(
                name="Member Left!",
                icon_url=member.avatar.url if member.avatar else None,
            )
            em.set_footer(text=f"ID: {member.id}")
            em.set_thumbnail(url=member.avatar.url if member.avatar else None)

            roles = ""
            for role in member.roles[::-1]:
                if len(roles) > 500:
                    roles += "and more roles..."
                    break
                if str(role) != "@everyone":
                    roles += f"{role.mention} "
            if len(roles) == 0:
                roles = "No roles."

            em.add_field(name="Roles:", value=roles, inline=False)
            await channel.send(embed=em)


async def setup(bot):
    await bot.add_cog(GuildLogs(bot))
