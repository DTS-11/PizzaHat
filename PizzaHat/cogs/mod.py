import datetime
import uuid
from typing import List, Optional, Union

import discord
import humanfriendly
from discord.ext import commands
from discord.ext.commands import Context

from core.bot import PizzaHat
from core.cog import Cog
from utils.config import ANTIHOIST_CHARS
from utils.embed import green_embed, normal_embed, orange_embed, red_embed
from utils.ui import ConfirmationView, Paginator


class Mod(Cog, emoji=1268851270136107048):
    """Keep your server safe!"""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(2, 60, commands.BucketType.user)
    @commands.has_permissions(manage_guild=True)
    async def logs(self, ctx: Context, channel: discord.TextChannel):
        """
        Set a guild logs channel.
        To replace the log channel, simply run this command again.
        """

        if not ctx.guild or self.bot.db is None:
            return

        await self.bot.db.execute(
            "INSERT INTO guild_logs (guild_id, channel_id) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET channel_id=$2",
            ctx.guild.id,
            channel.id,
        )
        await self.bot.db.execute(
            "INSERT INTO logs_config (guild_id, module) VALUES ($1, $2)",
            ctx.guild.id,
            ["all"],
        )

        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Guild logs channel set to {channel.mention}\nDefault logging config set to `all`. Please use the `logconfig` command to change the logging configs."
            )
        )

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.has_permissions(manage_guild=True)
    async def logconfig(self, ctx: Context, *log_modules: str):
        """
        Choose what events the bot needs to log.

        **Available Modules**
        `All:` Log everything
        `Automod:` Log every automod action
        `Guild:` Log every guild updates
        `Integrations:` Log every integration creations/updates/deletions
        `Invites:` Log every invite creations/deletions
        `Joins:` Log every member joins/leaves
        `Member:` Log every member updates
        `Messages:` Log every message edits/deletions
        `Mod:` Log every moderation action
        `Roles:` Log every guild role updates
        `Voice:` Log every voice state updates

        **Usage**
        `1.` `p!logconfig messages mod ...`
        `2.` `p!logconfig all`
        """

        if not ctx.guild or self.bot.db is None:
            return

        available_modules = [
            "all",
            "automod",
            "guild",
            "integrations",
            "invites",
            "joins",
            "member",
            "messages",
            "mod",
            "roles",
            "voice",
        ]

        for module in log_modules:
            if module.lower() not in available_modules:
                return await ctx.send(
                    embed=red_embed(
                        title=f"{self.bot.no} Invalid Module",
                        description=f"{module} is not an available module.\n\nAvailable modules: {', '.join(available_modules)}",
                    )
                )

        # Remove duplicates and convert all modules to lowercase
        lowercase_modules: List[str] = list(
            set(module.lower() for module in log_modules)
        )

        # If "all" is chosen, remove other modules
        if "all" in lowercase_modules:
            lowercase_modules = ["all"]
            removed_modules = available_modules[:-1]  # Exclude "all"
        else:
            # Determine removed modules
            existing_modules = await self.bot.db.fetchval(
                "SELECT module FROM logs_config WHERE guild_id = $1", ctx.guild.id
            )
            if existing_modules:
                existing_modules = set(existing_modules)
                removed_modules = [
                    module
                    for module in existing_modules
                    if module not in lowercase_modules
                ]
            else:
                removed_modules = []

        # Update log configurations
        await self.bot.db.execute(
            "UPDATE logs_config SET module = $2 WHERE guild_id = $1",
            ctx.guild.id,
            lowercase_modules,
        )

        # Send confirmation message
        enabled_modules = ", ".join(lowercase_modules)
        confirmation_em = green_embed(
            description=f"{self.bot.yes} Logging enabled for: {enabled_modules}."
        )
        await ctx.send(embed=confirmation_em)

        # Send confirmation message for disabled modules
        if removed_modules:
            disabled_modules = ", ".join(removed_modules)
            disabled_confirmation_em = green_embed(
                description=f"{self.bot.yes} Logging disabled for: {disabled_modules}."
            )
            await ctx.send(embed=disabled_confirmation_em)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(kick_members=True, manage_guild=True)
    @commands.bot_has_permissions(kick_members=True, manage_guild=True)
    @commands.cooldown(1, 10, commands.BucketType.guild)
    async def prune(self, ctx: Context, days: int, *roles: discord.Role):
        """Kicks inactive members."""

        if not ctx.guild:
            return

        reason = f"Prune members initiated by {ctx.author}"
        confirm = ConfirmationView(ctx, 60)
        est_pruned = await ctx.guild.estimate_pruned_members(days=days, roles=roles)
        msg = await ctx.send(
            embed=orange_embed(
                description=f"<:warning:1268855244033363968> Are you sure that you want to prune **{est_pruned}** members?"
            ),
            view=confirm,
        )
        await confirm.wait()

        if not confirm.value:
            return await ctx.send(
                embed=red_embed(description="Aborted pruning members.")
            )
        await msg.delete()
        m = await ctx.send(embed=orange_embed(description="Pruning members..."))

        try:
            await ctx.guild.prune_members(
                days=days, roles=roles, reason=reason, compute_prune_count=False
            )

        except discord.HTTPException:
            await m.edit(
                embed=red_embed(description=f"{self.bot.no} Failed to prune members.")
            )

        else:
            await m.edit(
                embed=green_embed(
                    description=f"{self.bot.yes} Members have been pruned."
                )
            )

    @commands.command(aliases=["mn"])
    @commands.guild_only()
    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def modnick(self, ctx: Context, member: discord.Member):
        """Sets a random moderated nickname."""

        try:
            nick = f"Moderated Nickname {uuid.uuid4()}"[:24]
            await member.edit(nick=nick)
            await ctx.send(
                embed=green_embed(
                    description=f"{self.bot.yes} Nickname changed to `{nick}`"
                )
            )

        except discord.HTTPException:
            await ctx.send(
                embed=red_embed(description=f"{self.bot.no} Something went wrong.")
            )

    @commands.command(aliases=["sn"])
    @commands.guild_only()
    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def setnick(self, ctx: Context, member: discord.Member, *, nick: str):
        """Sets a custom nickname."""

        try:
            await member.edit(nick=nick)
            await ctx.send(
                embed=green_embed(
                    description=f"{self.bot.yes} Nickname for {member.name} was changed to {member.mention}"
                )
            )

        except discord.HTTPException:
            await ctx.send(
                embed=red_embed(description=f"{self.bot.no} Something went wrong.")
            )

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def decancer(self, ctx: Context, member: discord.Member):
        """
        Removes special characters from the user's name
        and renames them as "Moderated Nickname"
        """

        try:
            if member.display_name[
                0
            ] in ANTIHOIST_CHARS and not member.display_name.startswith("[AFK] "):
                await member.edit(
                    nick="Moderated Nickname",
                    reason=f"Decancered member (req. by: {ctx.author}).",
                )
                await ctx.send(
                    embed=green_embed(
                        description=f"{self.bot.yes} Successfully decancered {member.mention}"
                    )
                )

            if ANTIHOIST_CHARS not in member.display_name[0]:
                await ctx.send(
                    embed=red_embed(
                        description=f"{self.bot.no} No special characters found."
                    )
                )

        except discord.HTTPException:
            await ctx.send(
                embed=red_embed(description=f"{self.bot.no} Something went wrong.")
            )

    @commands.command(aliases=["sm"])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def slowmode(self, ctx: Context, seconds: Optional[int] = None):
        """
        Change the slowmode.
        If no values are given, the bot returns slowmode of the current channel.
        """

        if ctx.channel is discord.DMChannel:
            return await ctx.send(
                embed=red_embed(description="Slow-mode cannot be checked/added.")
            )

        if isinstance(
            ctx.channel,
            Union[
                discord.TextChannel,
                discord.StageChannel,
                discord.ForumChannel,
                discord.Thread,
            ],
        ):
            if seconds is None:
                seconds = ctx.channel.slowmode_delay
                return await ctx.send(
                    embed=normal_embed(
                        description=f"The slowmode in this channel is `{seconds}` seconds"
                    )
                )

            elif seconds < 0:
                return await ctx.send(
                    embed=red_embed(
                        description=f"{self.bot.no} Slowmode must be a positive number"
                    )
                )

            await ctx.channel.edit(slowmode_delay=seconds)
            await ctx.send(
                embed=green_embed(
                    description=f"{self.bot.yes} Slow-mode in this channel has been set to {f'`{seconds}` seconds.' if seconds != 0 else 'none. Chat goes brrrr...'}"
                )
            )

    @commands.group(aliases=["lockdown"])
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def lock(self, ctx: Context):
        """Lock management commands."""

        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    @lock.command(name="channel")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def lock_channel(
        self,
        ctx: Context,
        role: Optional[discord.Role] = None,
        channel: Optional[Union[discord.TextChannel, discord.abc.Messageable]] = None,
    ):
        """
        Locks a channel with role requirement.
        If role is not given, the bot takes the default role of the guild which is @everyone.
        """

        if ctx.guild is not None:
            role = role or ctx.guild.default_role
            channel = channel or ctx.channel

            if isinstance(channel, discord.TextChannel):
                overwrite = channel.overwrites_for(role)
                overwrite.send_messages = False
                overwrite.add_reactions = False

                await channel.set_permissions(role, overwrite=overwrite)
                await ctx.message.add_reaction("🔒")
                await ctx.send(
                    embed=green_embed(
                        title="🔒 Locked",
                        description=f"{self.bot.yes} Channel has been locked for {role.mention}",
                        timestamp=True,
                    )
                )

            else:
                await ctx.send(
                    embed=red_embed(
                        description=f"{self.bot.no} This command can only be used on text channels."
                    )
                )

    @lock.command(name="server")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def lock_server(self, ctx: Context, role: discord.Role | None):
        """
        Locks the whole server with role requirement.
        If role is not given, the bot takes the default role of the guild which is @everyone.
        """

        if ctx.guild is not None:
            role = ctx.guild.default_role or role
            reason = f"Action done by {ctx.author}"
            confirm = ConfirmationView(ctx, 60)
            msg = await ctx.send(
                embed=orange_embed(
                    description="<:warning:1268855244033363968> Are you sure you want to lock the server?"
                ),
                view=confirm,
            )
            await confirm.wait()

            if not confirm.value:
                return await ctx.send(
                    embed=red_embed(
                        description=f"{self.bot.no} Aborted lockdown process."
                    )
                )
            await msg.delete()
            m = await ctx.send(
                embed=orange_embed(description="Server lockdown initiated...")
            )

            for tc in ctx.guild.text_channels:
                await tc.set_permissions(
                    role, send_messages=False, add_reactions=False, reason=reason
                )

            for vc in ctx.guild.voice_channels:
                await vc.set_permissions(
                    role, connect=False, speak=False, reason=reason
                )

            em = green_embed(
                title="🔒 Server Locked",
                description="The server has been locked by a staff member. You are **not muted**.",
                timestamp=True,
            )
            em.set_author(
                name=ctx.author,
                url=ctx.author.avatar.url if ctx.author.avatar else None,
            )
            em.set_footer(
                text=ctx.guild.name,
                icon_url=ctx.guild.icon.url if ctx.guild.icon else None,
            )

            await m.edit(embed=em)

    @commands.group()
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unlock(self, ctx: Context):
        """Unlock management commands."""

        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    @unlock.command(name="channel")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def unlock_channel(
        self,
        ctx: Context,
        role: Optional[discord.Role] = None,
        channel: Optional[Union[discord.TextChannel, discord.abc.Messageable]] = None,
    ):
        """
        Unlocks a channel with role requirement.
        If role is not given, the bot takes the default role of the guild which is @everyone.
        """

        if ctx.guild is not None:
            role = role or ctx.guild.default_role
            channel = channel or ctx.channel

            if isinstance(channel, discord.TextChannel):
                overwrite = channel.overwrites_for(role)
                overwrite.send_messages = True
                overwrite.add_reactions = True

                await channel.set_permissions(role, overwrite=overwrite)
                await ctx.message.add_reaction("🔓")
                await ctx.send(
                    embed=green_embed(
                        title="🔓 Unlocked",
                        description=f"{self.bot.yes} Channel has been unlocked for {role.mention}",
                        timestamp=True,
                    )
                )

            else:
                await ctx.send(
                    embed=red_embed(
                        description=f"{self.bot.no} This command can only be used on text channels."
                    )
                )

    @unlock.command(name="server")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def unlock_server(self, ctx: Context, role: discord.Role | None):
        """
        Unlocks the whole server with role requirement.
        If role is not given, the bot takes the default role of the guild which is @everyone.
        """

        if ctx.guild is not None:
            role = ctx.guild.default_role or role
            reason = f"Action done by {ctx.author}"
            confirm = ConfirmationView(ctx, 60)
            msg = await ctx.send(
                embed=orange_embed(
                    description="<:warning:1268855244033363968> Are you sure you want to unlock the server?"
                ),
                view=confirm,
            )
            await confirm.wait()

            if not confirm.value:
                return await ctx.send(
                    embed=red_embed(
                        description=f"{self.bot.no} Aborted unlock process."
                    )
                )
            await msg.delete()
            m = await ctx.send(
                embed=orange_embed(description="Server unlock initiated...")
            )

            for tc in ctx.guild.text_channels:
                await tc.set_permissions(
                    role,
                    send_messages=True,
                    add_reactions=True,
                    read_message_history=True,
                    reason=reason,
                )

            for vc in ctx.guild.voice_channels:
                await vc.set_permissions(role, connect=True, speak=True, reason=reason)

            em = green_embed(
                title="🔓 Server Unlocked",
                description="The server has been unlocked.",
                timestamp=True,
            )
            em.set_author(
                name=ctx.author,
                url=ctx.author.avatar.url if ctx.author.avatar else None,
            )
            em.set_footer(
                text=ctx.guild.name,
                icon_url=ctx.guild.icon.url if ctx.guild.icon else None,
            )

            await m.edit(embed=em)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def hide(
        self,
        ctx: Context,
        role: Optional[discord.Role] = None,
        channel: Optional[Union[discord.TextChannel, discord.abc.Messageable]] = None,
    ):
        """
        Hides a channel.
        If no role is given, defaults to @everyone.
        """

        if ctx.guild is not None:
            role = role or ctx.guild.default_role
            channel = channel or ctx.channel

            if isinstance(channel, discord.TextChannel):
                overwrite = channel.overwrites_for(role)
                overwrite.view_channel = False

                await channel.set_permissions(role, overwrite=overwrite)
                await ctx.send(
                    embed=green_embed(
                        title="🔓 Hidden",
                        description=f"{self.bot.yes} Channel has been hidden from {role.mention}",
                        timestamp=True,
                    )
                )

            else:
                await ctx.send(
                    embed=red_embed(
                        description=f"{self.bot.no} This command can only be used on text channels."
                    )
                )

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def expose(
        self,
        ctx: Context,
        role: Optional[discord.Role] = None,
        channel: Optional[Union[discord.TextChannel, discord.abc.Messageable]] = None,
    ):
        """
        Exposes a channel.
        If no role is given, defaults to @everyone."""

        if ctx.guild is not None:
            role = role or ctx.guild.default_role
            channel = channel or ctx.channel

            if isinstance(channel, discord.TextChannel):
                overwrite = channel.overwrites_for(role)
                overwrite.view_channel = True

                await channel.set_permissions(role, overwrite=overwrite)
                await ctx.send(
                    embed=green_embed(
                        title="🔓 Exposed",
                        description=f"{self.bot.yes} Channel has been exposed to {role.mention}",
                        timestamp=True,
                    )
                )

            else:
                await ctx.send(
                    embed=red_embed(
                        description=f"{self.bot.no} This command can only be used on text channels."
                    )
                )

    @commands.command(aliases=["purge"])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def clear(self, ctx: Context, amount: int = 100):
        """
        Deletes certain amount of messages.
        If no amount is given, it deletes upto 100 messages.
        """

        if ctx.channel is discord.DMChannel:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Messages cannot be cleared."
                )
            )

        if amount > 100:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} I can only purge 100 messages at a time."
                )
            )

        elif amount < 0:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Purge amount must be a positive number."
                )
            )

        else:
            await ctx.message.delete()
            if isinstance(
                ctx.channel,
                Union[
                    discord.TextChannel,
                    discord.StageChannel,
                    discord.VoiceChannel,
                    discord.Thread,
                ],
            ):
                await ctx.channel.purge(limit=amount)
                await ctx.send(
                    embed=green_embed(
                        description=f"{self.bot.yes} {amount} messages cleared by {ctx.author.mention}"
                    ),
                    delete_after=2.5,
                )
            else:
                await ctx.send(
                    embed=red_embed(
                        description=f"{self.bot.no} This command is not supported in this channel type."
                    )
                )

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def cleanup(self, ctx: Context, amount: int = 100):
        """
        Cleans up bot's messages in the current channel.
        If no amount is given, it deletes upto 100 messages.
        """

        def is_bot(m: discord.Message) -> bool:
            return m.author == self.bot.user

        if ctx.channel is discord.DMChannel:
            return await ctx.send(
                embed=red_embed(description=f"{self.bot.no} Cannot clear messages.")
            )

        if amount > 100:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} I can only clear upto 100 messages at a time."
                )
            )

        else:
            if isinstance(
                ctx.channel,
                Union[
                    discord.TextChannel,
                    discord.StageChannel,
                    discord.ForumChannel,
                    discord.Thread,
                ],
            ):
                await ctx.channel.purge(limit=amount, check=is_bot)
                await ctx.send(
                    embed=green_embed(
                        description=f"{self.bot.yes} {amount} messages cleared by {ctx.author.mention}"
                    ),
                    delete_after=2.5,
                )
            else:
                await ctx.send(
                    embed=red_embed(
                        description=f"{self.bot.no} This command is not supported in this channel type."
                    )
                )

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def kick(self, ctx: Context, member: discord.Member, *, reason: str | None):
        """Kicks a member."""

        reason = f"Kicked by {ctx.author} (ID: {ctx.author.id})"
        await member.kick(reason=reason)
        await ctx.send(
            embed=green_embed(description=f"{self.bot.yes} Kicked {member.mention}")
        )

    @commands.command(aliases=["mk"])
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def masskick(
        self,
        ctx: Context,
        members: commands.Greedy[discord.Member],
        *,
        reason: str | None,
    ):
        """
        Kick multiple members.
        You can only kick users who are in the server.
        """

        if not len(members):
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} One or more required arguments are missing."
                )
            )

        for member in members:
            reason = reason or f"Kicked by {ctx.author} (ID: {ctx.author.id})"
            await member.kick(reason=reason)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Kicked {len(members)} members"
            )
        )

    @commands.command(aliases=["b"])
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def ban(
        self, ctx: Context, member: Union[discord.Member, int], *, reason: str | None
    ):
        """
        Bans a member whether or not they're in the server.
        You can ban the member using their ID or my mentioning them.
        """

        reason = reason or f"Banned by {ctx.author} (ID: {ctx.author.id})"

        if ctx.guild is not None:
            if isinstance(member, int):
                await ctx.guild.ban(discord.Object(id=member), reason=f"{reason}")
                user = await self.bot.fetch_user(member)
                await ctx.send(
                    embed=green_embed(description=f"{self.bot.yes} Banned {user}")
                )

            else:
                await member.ban(reason=f"{reason}", delete_message_days=0)
                await ctx.send(
                    embed=green_embed(
                        description=f"{self.bot.yes} Banned {member.mention}"
                    )
                )

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.cooldown(1, 10, commands.BucketType.guild)
    async def banlist(self, ctx: Context):
        """Get a list of all the banned members."""

        if not ctx.guild:
            return

        try:
            banned_users = []
            embeds = []

            async for ban_entry in ctx.guild.bans(limit=None):
                banned_users.append(f"{ban_entry.user} (ID: {ban_entry.user.id})")

            if not banned_users:
                return await ctx.send(
                    embed=red_embed(
                        title="Banned Users",
                        description="There are no banned users in this server.",
                        timestamp=True,
                    )
                )

            for i in range(0, len(banned_users), 10):
                em = normal_embed(
                    title="Banned Users",
                    description="- " + "\n- ".join(banned_users[i : i + 10]),
                    timestamp=True,
                )
                em.set_footer(
                    text=f"Page {len(embeds) + 1}/{-(-len(banned_users) // 10)}",
                )
                embeds.append(em)

            if len(embeds) == 1:
                return await ctx.send(embed=embeds[0])
            else:
                paginator = Paginator(ctx, embeds)
                return await ctx.send(embed=embeds[0], view=paginator)

        except discord.Forbidden:
            await ctx.send("I don't have permission to view the ban list.")
        except discord.HTTPException as e:
            await ctx.send(f"An error occurred while fetching the ban list: {str(e)}")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred: {str(e)}")

    @commands.command(aliases=["mb"])
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def massban(
        self,
        ctx: Context,
        members: commands.Greedy[discord.Member],
        *,
        reason: str | None,
    ):
        """
        Mass bans multiple members.
        You can only ban users, who are in the server.
        """

        if not len(members):
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} One or more required arguments are missing."
                )
            )

        else:
            for target in members:
                reason = f"Banned by {ctx.author} (ID: {ctx.author.id})"
                await target.ban(reason=reason, delete_message_days=0)
                await ctx.send(
                    embed=green_embed(description=f"{self.bot.yes} Banned {target}")
                )

    @commands.command(aliases=["sb"])
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def softban(
        self, ctx: Context, member: discord.Member, *, reason: str | None
    ):
        """Soft bans a member.

        A softban is basically banning the member from the server but
        then unbanning the member as well. This allows you to essentially
        kick the member while removing their messages.
        """

        if not ctx.guild:
            return

        reason = f"Banned by {ctx.author} (ID: {ctx.author.id})"
        await ctx.guild.ban(member, reason=reason)
        await ctx.guild.unban(member, reason=reason)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Sucessfully soft-banned {member.mention}."
            )
        )

    @commands.command(aliases=["ub"])
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def unban(self, ctx: Context, id: int):
        """Unbans a member."""

        try:
            if ctx.guild is not None:
                user = self.bot.get_user(id)
                await ctx.guild.unban(
                    discord.Object(id=id),
                    reason=f"Unbanned by {ctx.author} (ID: {ctx.author.id})",
                )
                await ctx.send(
                    embed=green_embed(description=f"{self.bot.yes} Unbanned {user}")
                )

        except discord.NotFound:
            await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Not a valid previously banned member or the member could not be found."
                )
            )

    @commands.command(aliases=["timeout"])
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def mute(
        self, ctx: Context, member: discord.Member, duration, *, reason: str | None
    ):
        """
        Mutes or timeouts a member for specific time.
        Maximum duration of timeout: 28 days (API limitation)
        Use 5m for 5 mins, 1h for 1 hour etc...
        """

        reason = reason or f"Action done by {ctx.author}"
        humanly_duration = humanfriendly.parse_timespan(duration)

        await member.timeout(
            discord.utils.utcnow() + datetime.timedelta(seconds=humanly_duration),
            reason=reason,
        )
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} {member.mention} has been timed out for {duration}."
            )
        )

    @commands.command(aliases=["untimeout"])
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def unmute(self, ctx: Context, member: discord.Member, *, reason: str | None):
        """Unmutes or removes a member from timeout."""

        reason = reason or f"Action done by {ctx.author}"
        await member.timeout(None, reason=reason)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} {member.mention} has been unmuted!"
            )
        )

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def addrole(self, ctx: Context, user: discord.Member, *, role: discord.Role):
        """Assign role to a user."""

        if role not in user.roles:
            await user.add_roles(role)
            await ctx.send(
                embed=green_embed(
                    description=f"{self.bot.yes} Successfully added {role.mention} to {user.mention}"
                )
            )

        else:
            await ctx.send(
                embed=normal_embed(
                    description=f"{user.mention} already has {role.mention} role."
                )
            )

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def removerole(
        self, ctx: Context, user: discord.Member, *, role: discord.Role
    ):
        """Remove role from a user."""

        if role in user.roles:
            await user.remove_roles(role)
            await ctx.send(
                embed=green_embed(
                    description=f"{self.bot.yes} Successfully removed {role.mention} from {user.mention}"
                )
            )
        else:
            await ctx.send(
                embed=normal_embed(
                    description=f"{user.mention} does not have {role.mention} role."
                )
            )

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def createrole(
        self,
        ctx: Context,
        *,
        role: discord.Role,
        color: discord.Color = discord.Color.default(),
        hoist: bool = False,
    ):
        """Create a new role with color and hoist options."""

        if ctx.guild is not None:
            await ctx.guild.create_role(
                reason=f"Role created by {ctx.author}",
                name=role.name,
                color=color,
                hoist=hoist,
            )
            await ctx.send(
                embed=green_embed(
                    description=f"{self.bot.yes} Role created successfully!"
                )
            )

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def role_delete(self, ctx: Context, *, role: discord.Role):
        """Delete a role."""

        if ctx.guild is not None:
            if role in ctx.guild.roles:
                await role.delete()
                await ctx.send(
                    embed=green_embed(
                        description=f"{self.bot.yes} Role deleted successfully!"
                    )
                )

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def rolelist(self, ctx: Context):
        """List all the server roles."""

        if ctx.guild is not None:
            roles = sorted(ctx.guild.roles, key=lambda x: x.position, reverse=True)
            embeds = []

            chunk_size = 10
            role_chunks = [
                roles[i : i + chunk_size] for i in range(0, len(roles), chunk_size)
            ]

            for i, chunk in enumerate(role_chunks, 1):
                description = "\n\n".join(
                    [f"{role.mention} `({role.id})` • {role.name}" for role in chunk]
                )
                embeds.append(
                    normal_embed(
                        title=f"{ctx.guild.name} Roles ({len(roles)})",
                        description=description,
                        timestamp=True,
                    )
                    .set_thumbnail(url=ctx.guild.icon.url)  # type: ignore
                    .set_footer(text=f"Page {i}/{len(role_chunks)}")
                )

            if not embeds:
                return await ctx.send("No roles to display.")

            if len(embeds) == 1:
                return await ctx.send(embed=embeds[0])
            else:
                view = Paginator(ctx, embeds)
                return await ctx.send(embed=embeds[0], view=view)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def createchannel(self, ctx: Context, name: str):
        """Creates a new channel."""

        if ctx.guild is not None:
            await ctx.guild.create_text_channel(name)
            await ctx.send(
                embed=green_embed(
                    description=f"{self.bot.yes} Channel created successfully!"
                )
            )

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def deletechannel(self, ctx: Context, channel: discord.TextChannel):
        """Delete a channel."""

        await channel.delete()
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Channel deleted successfully!"
            )
        )

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def channellist(self, ctx: Context):
        """List all the server channels."""

        if ctx.guild is not None:
            channels = [
                channel
                for channel in ctx.guild.channels
                if not isinstance(channel, discord.CategoryChannel)
            ]
            embeds = []

            # Group channels by category
            channels_by_category = {}
            channels_without_category = []

            for channel in channels:
                if isinstance(channel, discord.TextChannel) and channel.category:
                    category_id = str(channel.category.id)
                    if category_id not in channels_by_category:
                        channels_by_category[category_id] = {
                            "category": channel.category,
                            "channels": [],
                        }
                    channels_by_category[category_id]["channels"].append(channel)
                else:
                    channels_without_category.append(channel)

            # Create embed for channels without categories
            if channels_without_category:
                description = "".join(
                    [
                        f"```asciidoc\nNo category\n\t{channel.name} :: {channel.type} :: {channel.id}\n```"
                        for channel in channels_without_category
                    ]
                )

                embeds.append(
                    normal_embed(
                        title=f"{ctx.guild.name} Channels ({len(channels)})",
                        description=description,
                        timestamp=True,
                    )
                    .set_thumbnail(url=ctx.guild.icon.url)  # type: ignore
                    .set_footer(text=f"Page 1/{len(channels_by_category) + 1}")
                )

            # Create embeds for channels with categories
            total_category_pages = len(channels_by_category)
            category_page_count = 1 if channels_without_category else 0

            for i, category_info in enumerate(
                channels_by_category.values(), category_page_count + 1
            ):
                category = category_info["category"]
                category_name = category.name if category else "No category"
                category_id = category.id if category else "No category"

                description = "".join(
                    [
                        f"```asciidoc\n{category_name} :: '{category_id}'\n\t{channel.name} :: {channel.type} :: {channel.id}\n```"
                        for channel in category_info["channels"]
                    ]
                )

                embeds.append(
                    normal_embed(
                        title=f"{ctx.guild.name} Channels ({len(channels)})",
                        description=description,
                        timestamp=True,
                    )
                    .set_thumbnail(url=ctx.guild.icon.url)  # type: ignore
                    .set_footer(text=f"Page {i}/{total_category_pages + 1}")
                )

            if not embeds:
                return await ctx.send("No channels to display.")

            if len(embeds) == 1:
                return await ctx.send(embed=embeds[0])
            else:
                view = Paginator(ctx, embeds)
                return await ctx.send(embed=embeds[0], view=view)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def channeltopic(
        self,
        ctx: Context,
        channel: Optional[Union[discord.TextChannel, discord.ForumChannel]] = None,
        *,
        text: str,
    ):
        """
        Change the channel topic.
        If no channel is given, it will default to the current channel.
        """

        channel = channel or ctx.channel  # type: ignore

        try:
            await channel.edit(topic=text)  # type: ignore

        except discord.HTTPException:
            await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} You can only change the topic of text/forum channels."
                )
            )

        else:
            await ctx.send(
                embed=green_embed(
                    description=f"{self.bot.yes} Channel topic changed successfully!"
                )
            )

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def warn(self, ctx: Context, member: discord.Member, *, reason: str | None):
        """Warns a user."""

        reason = f"No reason given.\nWarned done by {ctx.author}"

        if ctx.guild is not None:
            if member == ctx.author or member == self.bot.user:
                return await ctx.send(
                    embed=red_embed(description="You cant warn yourself or the bot.")
                )

            if not ctx.author.top_role.position == member.top_role.position:  # type: ignore
                if not ctx.author.top_role.position > member.top_role.position:  # type: ignore
                    return await ctx.send(
                        embed=red_embed(
                            description="You cant warn someone that has higher or same role heirarchy."
                        )
                    )

            (
                await self.bot.db.execute(
                    "INSERT INTO warnlogs (guild_id, user_id, mod_id, reason) VALUES ($1, $2, $3, $4)",
                    ctx.guild.id,
                    member.id,
                    ctx.author.id,
                    reason,
                )
                if self.bot.db
                else None
            )

            em = green_embed(
                title=f"{self.bot.yes} Warned User",
                description=f"Moderator: {ctx.author.mention}\nMember: {member.mention}\nReason: {reason}",
                timestamp=True,
            )
            em.set_author(
                name=ctx.author,
                url=ctx.author.avatar.url if ctx.author.avatar else None,
            )
            em.set_thumbnail(url=member.avatar.url if member.avatar else None)

            await ctx.send(embed=em)

    @commands.command(aliases=["warns"])
    @commands.guild_only()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def warnings(
        self, ctx: Context, member: Optional[Union[discord.Member, discord.User]] = None
    ):
        """
        Displays the warnings of the user.
        If no user is given, the bot sends your warnings.
        """

        member = member or ctx.author

        if ctx.guild is not None:
            records = (
                await self.bot.db.fetch(
                    "SELECT * FROM warnlogs WHERE user_id = $1 AND guild_id = $2",
                    member.id,
                    ctx.guild.id,
                )
                if self.bot.db
                else None
            )

            if not records:
                em = green_embed(
                    title=f"Warnings of {member.name}",
                    description="✨ This user has no warns!",
                    timestamp=True,
                )
                em.set_thumbnail(url=member.avatar.url if member.avatar else None)
                return await ctx.send(embed=em)

            else:
                embeds = []
                warning_list = [
                    f"**ID:** {record['id']}\n**Reason:** {record['reason']}\n**Moderator:** {ctx.guild.get_member(record['mod_id'])}\n"
                    for record in records
                ]
                chunks = [
                    warning_list[i : i + 5] for i in range(0, len(warning_list), 5)
                ]

                for chunk in chunks:
                    em = normal_embed(
                        title=f"Warnings of {member.name} | {len(records)} warns",
                        description="\n".join(chunk),
                        timestamp=True,
                    )
                    em.set_thumbnail(url=member.avatar.url if member.avatar else None)
                    embeds.append(em)

                if len(embeds) == 1:
                    return await ctx.send(embed=embeds[0])
                else:
                    paginator = Paginator(ctx, embeds)
                    return await ctx.send(embed=embeds[0], view=paginator)

    @commands.command(aliases=["delwarn"])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def deletewarn(self, ctx: Context, member: discord.Member, warn_id: int):
        """Deletes a warn of the user with warn ID."""

        result = (
            await self.bot.db.execute(
                "DELETE FROM warnlogs WHERE id = $1 AND user_id = $2 AND guild_id = $3",
                warn_id,
                member.id,
                ctx.guild.id,
            )
            if self.bot.db and ctx.guild
            else None
        )

        if result == "DELETE 0":
            await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Warn ID: `{warn_id}` not found for {member.mention}."
                )
            )

        else:
            await ctx.send(
                embed=green_embed(
                    description=f"{self.bot.yes} Warn ID `{warn_id}` for {member.mention} has been deleted."
                )
            )


async def setup(bot):
    await bot.add_cog(Mod(bot))
