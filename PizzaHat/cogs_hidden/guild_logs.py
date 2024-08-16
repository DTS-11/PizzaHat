import asyncio
import datetime
from collections import defaultdict
from typing import List, Union

import discord
from async_lru import alru_cache
from discord.utils import escape_markdown
from humanfriendly import format_timespan

from cogs.utility import format_date
from core.bot import PizzaHat
from core.cog import Cog
from utils.embed import green_embed, normal_embed, orange_embed, red_embed


class GuildLogs(Cog):
    """Log everything in your server!"""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot
        self.recent_kicks = defaultdict(set)
        self.lock = asyncio.Lock()

    @alru_cache()
    async def get_logs_channel(self, guild_id: int) -> Union[discord.TextChannel, None]:
        if self.bot.db is not None:
            data = await self.bot.db.fetchval(
                "SELECT channel_id FROM guild_logs WHERE guild_id=$1", guild_id
            )
            guild = self.bot.get_guild(guild_id)

            if not guild or not data:
                return

            channel = await guild.fetch_channel(data)
            assert isinstance(
                channel, discord.TextChannel
            ), "channel will always be a textchannel"
            return channel

    @alru_cache()
    async def check_log_enabled(self, guild_id: int, module_type: str) -> bool:
        if self.bot.db is not None:
            modules = await self.bot.db.fetchval(
                "SELECT module FROM logs_config WHERE guild_id=$1", guild_id
            )

            if modules:
                if "all" in modules:
                    return True
                elif module_type.lower() in modules:
                    return True
            return False
        else:
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
            em = green_embed(
                title=f"Message edited in #{before.channel}",
                timestamp=True,
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
            em = red_embed(
                title=f"Message Deleted in #{msg.channel}",
                description=msg.content,
                timestamp=True,
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
            em = red_embed(
                title="Bulk Message Deleted",
                description=f"**{len(msgs)}** messages deleted in {msgs[0].channel}",
                timestamp=True,
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
            em = red_embed(
                title="Member Banned",
                timestamp=True,
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
            em = green_embed(
                title="Member Unbanned",
                timestamp=True,
            )

            em.add_field(
                name="Reason", value=discord.AuditLogAction.unban, inline=False
            )
            em.set_author(name=user, icon_url=user.avatar.url if user.avatar else None)
            em.set_footer(text=f"User ID: {user.id}")

            await channel.send(embed=em)

    @Cog.listener(name="on_member_join")
    async def send_join_log(self, member: discord.Member):
        channel = await self.get_logs_channel(member.guild.id)
        should_log_all = await self.check_log_enabled(member.guild.id, "all")
        should_log_joins = await self.check_log_enabled(member.guild.id, "joins")

        if not channel:
            return

        if should_log_all or should_log_joins:
            em = green_embed(
                description=f"{member.mention} {escape_markdown(str(member))}",
                timestamp=True,
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
                        - member.created_at.replace(tzinfo=datetime.timezone.utc)
                    ).total_seconds()
                ),
                inline=False,
            )
            em.add_field(name="Members:", value=member.guild.member_count, inline=False)

            await channel.send(embed=em)

    @Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        async with self.lock:
            if member.id in self.recent_kicks[member.guild.id]:
                self.recent_kicks[member.guild.id].remove(member.id)
                return

            is_kick = await self.check_if_kick(member)
            if is_kick:
                await self.handle_kick(member, is_kick)
            else:
                await self.handle_leave(member)

    async def check_if_kick(self, member: discord.Member):
        try:
            async for entry in member.guild.audit_logs(
                limit=1, action=discord.AuditLogAction.kick
            ):
                if (
                    entry.target
                    and entry.target.id == member.id
                    and (discord.utils.utcnow() - entry.created_at).total_seconds() < 5
                ):
                    return entry.user
        except discord.errors.Forbidden:
            pass
        return None

    async def handle_kick(
        self, member: discord.Member, kicker: Union[discord.Member, discord.User]
    ):
        if isinstance(kicker, discord.User):
            kicker = member.guild.get_member(kicker.id) or kicker

        channel = await self.get_logs_channel(member.guild.id)
        should_log_all = await self.check_log_enabled(member.guild.id, "all")
        should_log_mod = await self.check_log_enabled(member.guild.id, "mod")

        if channel and (should_log_all or should_log_mod):
            em = red_embed(
                title="<:danger:1268855303768903733> Member Kicked",
                description=f"{member.mention} was kicked by {kicker.mention}",
                timestamp=True,
            )
            em.set_author(
                name=member,
                icon_url=member.avatar.url if member.avatar else None,
            )
            em.set_footer(text=f"ID: {member.id}")

            await channel.send(embed=em)

        async with self.lock:
            self.recent_kicks[member.guild.id].add(member.id)
            self.bot.loop.create_task(
                self.remove_from_recent_kicks(member.guild.id, member.id)
            )

    async def remove_from_recent_kicks(self, guild_id: int, member_id: int):
        await asyncio.sleep(10)  # Wait for 10 seconds
        async with self.lock:
            self.recent_kicks[guild_id].discard(member_id)

    async def handle_leave(self, member: discord.Member):
        channel = await self.get_logs_channel(member.guild.id)
        should_log_all = await self.check_log_enabled(member.guild.id, "all")
        should_log_joins = await self.check_log_enabled(member.guild.id, "joins")

        if not channel:
            return

        if should_log_all or should_log_joins:
            em = red_embed(
                description=f"{member.mention} {escape_markdown(str(member))}",
                timestamp=True,
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

            em.add_field(
                name="Joined:", value=format_date(member.joined_at), inline=False
            )
            em.add_field(name="Roles:", value=roles, inline=False)
            em.add_field(name="Members:", value=member.guild.member_count, inline=False)
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

        for role in roles:
            role_text += f"{role.mention} "
        role_text = role_text[:-2]

        if should_log_all or should_log_member:
            em = normal_embed(
                description=f"Role{'s' if len(roles) > 1 else ''} {role_text} "
                f"{'were' if len(roles) > 1 else 'was'} "
                f"{'added to' if len(before.roles) < len(after.roles) else 'removed from'} "
                f"{after.mention}",
                timestamp=True,
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
            em = orange_embed(
                title="Nickname Updated",
                description=f"`{before.nick}` ➜ `{after.nick}`",
                timestamp=True,
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
                em.description = (
                    f"{member.mention} joined voice channel {after.channel.mention}"  # type: ignore
                )
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
            em = green_embed(
                title="Role Created",
                description=role.mention,
                timestamp=True,
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
            em = red_embed(
                title="Role Deleted",
                timestamp=True,
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
            em = orange_embed(
                title="Role Updated",
                description=after.mention,
                timestamp=True,
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
            em = orange_embed(
                title="Server Updated",
                timestamp=True,
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
                    name="Banner Updated!",
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
                    name="New Community Updates Channel",
                    value=f"`{before.public_updates_channel}` ➜ `{after.public_updates_channel}`",
                    inline=False,
                )

            if before.rules_channel != after.rules_channel:
                em.add_field(
                    name="Rules Channel",
                    value=f"`{before.rules_channel}` ➜ `{after.rules_channel}`",
                    inline=False,
                )

            if before.splash != after.splash:
                em.add_field(
                    name="Invite Splash Banner",
                    value=f"{'`None`' if before.splash is None else '[`Before`]('+str(before.splash.url)+')'} ➜ {'`None`' if after.splash is None else '[`After`]('+str(after.splash.url)+')'}",
                    inline=False,
                )

            if before.system_channel != after.system_channel:
                em.add_field(
                    name="System Channel",
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
            em = orange_embed(
                title="Emoji Updated",
                timestamp=True,
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
            em = orange_embed(
                title="Sticker Updated",
                timestamp=True,
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

    # ====== GUILD CHANNEL UPDATES  ======

    @Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        log_channel = await self.get_logs_channel(channel.guild.id)
        should_log_all = await self.check_log_enabled(channel.guild.id, "all")
        should_log_guild = await self.check_log_enabled(channel.guild.id, "guild")

        if not log_channel:
            return

        if should_log_all or should_log_guild:
            em = green_embed(
                title="Channel Created",
                description=channel.mention,
                timestamp=True,
            )
            em.set_author(
                name=channel.guild,
                icon_url=(
                    channel.guild.icon.url
                    if channel.guild.icon is not None
                    else "https://cdn.discordapp.com/embed/avatars/1.png"
                ),
            )
            em.set_footer(text=f"ID: {channel.id}")

            if isinstance(log_channel, discord.TextChannel):
                await log_channel.send(embed=em)

    @Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        log_channel = await self.get_logs_channel(channel.guild.id)
        should_log_all = await self.check_log_enabled(channel.guild.id, "all")
        should_log_guild = await self.check_log_enabled(channel.guild.id, "guild")

        if not log_channel:
            return

        if should_log_all or should_log_guild:
            em = red_embed(
                description=f"> Name: {channel.name}\n> ID: {channel.id}",
                timestamp=True,
            )
            em.set_author(
                name=channel.guild,
                icon_url=(
                    channel.guild.icon.url
                    if channel.guild.icon is not None
                    else "https://cdn.discordapp.com/embed/avatars/1.png"
                ),
            )
            em.set_footer(text=f"ID: {channel.id}")

            if isinstance(channel, discord.CategoryChannel):
                em.title = "Category Deleted"
            else:
                em.title = "Channel Deleted"

            if isinstance(log_channel, discord.TextChannel):
                await log_channel.send(embed=em)

    @Cog.listener()
    async def on_guild_channel_update(self, before, after):
        if before.position - after.position in [1, -1]:
            return

        channel = await self.get_logs_channel(before.guild.id)
        should_log_all = await self.check_log_enabled(before.guild.id, "all")
        should_log_guild = await self.check_log_enabled(before.guild.id, "guild")

        if not channel:
            return

        if should_log_all or should_log_guild:
            em = orange_embed(
                title="Channel Updated",
                description=after.mention,
                timestamp=True,
            )
            em.set_author(
                name=after.guild,
                icon_url=(
                    after.guild.icon.url
                    if after.guild.icon is not None
                    else "https://cdn.discordapp.com/embed/avatars/1.png"
                ),
            )
            em.set_footer(text=f"ID: {after.id}")

            if before.name != after.name:
                em.add_field(
                    name="Name:",
                    value=f"`{before.name}` ➜ `{after.name}`",
                    inline=False,
                )
            if before.category != after.category:
                em.add_field(
                    name="Category:",
                    value=f"`{before.category}` ➜ `{after.category}`",
                    inline=False,
                )
            if before.permissions_synced != after.permissions_synced:
                em.add_field(
                    name="Permissions Synced:",
                    value=f"`{before.permissions_synced}` ➜ `{after.permissions_synced}`",
                    inline=False,
                )
            if before.position != after.position:
                em.add_field(
                    name="Position Changed:",
                    value=f"`{before.position}` ➜ `{after.position}`",
                    inline=False,
                )
            if isinstance(before, discord.TextChannel) and before.topic != after.topic:
                em.add_field(
                    name="Topic Updated:",
                    value=f"```{before.topic}``` ➜ ```{after.topic}```",
                    inline=False,
                )
            if (
                isinstance(before, discord.TextChannel)
                and before.slowmode_delay != after.slowmode_delay
            ):
                em.add_field(
                    name="Slowmode Changed:",
                    value=f"`{format_timespan(before.slowmode_delay)}` ➜ `{format_timespan(after.slowmode_delay)}`",
                    inline=False,
                )
            if (
                isinstance(before, discord.TextChannel)
                and before.is_nsfw() != after.is_nsfw()
            ):
                em.add_field(
                    name="NSFW Channel:",
                    value=f"`{before.is_nsfw()}` ➜ `{after.is_nsfw()}`",
                    inline=False,
                )
            if (
                isinstance(before, discord.TextChannel)
                and before.is_news() != after.is_news()
            ):
                em.add_field(
                    name="Announcement Channel:",
                    value=f"`{before.is_news()}` ➜ `{after.is_news()}`",
                    inline=False,
                )

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
            em = green_embed(
                title="Integration Created",
                timestamp=True,
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
            em = orange_embed(
                title="Integration Updated",
                timestamp=True,
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
            em = red_embed(
                title="Integration Deleted",
                timestamp=True,
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
            em = green_embed(
                title="New Automod Rule Created",
                timestamp=True,
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
            em = orange_embed(
                title="New Automod Rule Updated",
                timestamp=True,
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
            em = red_embed(
                title="New Automod Rule Deleted",
                timestamp=True,
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
            em = red_embed(
                title="Automod Action Taken",
                timestamp=True,
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
            em = green_embed(
                title="Invite Created",
                timestamp=True,
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
            em = red_embed(
                title="Invite Deleted",
                timestamp=True,
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


async def setup(bot):
    await bot.add_cog(GuildLogs(bot))
