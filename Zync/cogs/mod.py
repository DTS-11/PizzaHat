"""Moderation and server-insight commands.

Contains the public ``Mod`` cog for staff actions such as bans, timeouts, warnings,
prune, slowmode, and the ``/insights`` overview with workflow analytics.
"""

from __future__ import annotations

import datetime
import re
import uuid
from typing import Any, List, Literal, Optional, cast

import discord
import humanfriendly
from discord.ext import commands
from discord.ext.commands import Context

from core.bot import Tier, Zync
from core.cog import Cog
from utils.config import ANTIHOIST_CHARS
from utils.custom_checks import premium
from utils.embed import ctx_embed, green_embed, orange_embed, red_embed
from utils.ui import ConfirmationView, Paginator

_LOG_MODULES = (
    "all", "automod", "guild", "integrations", "invites", "joins", "member",
    "messages", "mod", "roles", "voice",
)


class _InteractionContext:
    """Minimal ``Context`` shim so context menus reuse the slash command bodies."""

    def __init__(self, interaction: discord.Interaction) -> None:
        self.interaction = interaction
        self.author = interaction.user
        self.guild = interaction.guild
        self.bot = interaction.client

    async def send(self, *args: Any, **kwargs: Any) -> Any:
        """Send moderation feedback privately for context-menu invocations."""
        kwargs.setdefault("ephemeral", True)
        if self.interaction.response.is_done():
            return await self.interaction.followup.send(*args, **kwargs)
        return await self.interaction.response.send_message(*args, **kwargs)


async def _invoke(
    command: Any, cog: Mod, ctx: Context, *args: Any, **kwargs: Any
) -> None:
    """Call a cog command body with an explicit cog instance."""
    await command.callback(cog, ctx, *args, **kwargs)


def _validate_duration(value: str) -> tuple[float | None, str | None]:
    """Parse a human-friendly duration, returning seconds or an error message."""
    try:
        seconds = humanfriendly.parse_timespan(value.strip())
    except (humanfriendly.InvalidTimespan, ValueError, TypeError):
        return None, "Use a duration like `30m`, `1h`, or `7d`."
    if seconds <= 0:
        return None, "Duration must be greater than zero."
    if seconds > 28 * 24 * 60 * 60:
        return None, "Discord limits timeouts to 28 days."
    return seconds, None


class _ReasonModal(discord.ui.Modal):
    """Reason prompt shared by the Ban, Kick, and Warn context menus."""

    reason = discord.ui.TextInput(
        label="Reason",
        placeholder="No reason provided.",
        required=False,
        max_length=200,
    )

    def __init__(self, cog: Mod, member: discord.Member, action: str) -> None:
        super().__init__(title=f"{action.title()} {member.display_name}"[:45])
        self.cog = cog
        self.member = member
        self.action = action

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        ctx = cast(Context, _InteractionContext(interaction))
        reason = self.reason.value or None
        if self.action == "ban":
            await _invoke(
                self.cog.ban, self.cog, ctx, str(self.member.id), reason=reason
            )
        elif self.action == "kick":
            await _invoke(
                self.cog.kick, self.cog, ctx, str(self.member.id), reason=reason
            )
        else:
            await _invoke(
                self.cog.warn,
                self.cog,
                ctx,
                self.member,
                reason=reason or "No reason provided.",
            )


class _TimeoutModal(discord.ui.Modal, title="Timeout member"):
    duration = discord.ui.TextInput(
        label="Duration", placeholder="1h", default="1h", max_length=20
    )
    reason = discord.ui.TextInput(
        label="Reason", placeholder="No reason provided.", required=False, max_length=200
    )

    def __init__(self, cog: Mod, member: discord.Member) -> None:
        super().__init__()
        self.cog = cog
        self.member = member

    async def on_submit(self, interaction: discord.Interaction) -> None:
        _, error = _validate_duration(self.duration.value)
        if error is not None:
            bot = cast(Zync, interaction.client)
            await interaction.response.send_message(
                embed=red_embed(description=f"{bot.no} {error}"), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        ctx = cast(Context, _InteractionContext(interaction))
        await _invoke(
            self.cog.timeout,
            self.cog,
            ctx,
            self.member,
            self.duration.value,
            reason=self.reason.value or None,
        )


class Mod(Cog, emoji=1268851270136107048):
    """Keep your server safe!"""

    def __init__(self, bot: Zync):
        self.bot: Zync = bot

    def clear_log_config_cache(self, guild_id: int | None = None) -> None:
        guild_logs_cog = self.bot.get_cog("GuildLogs")
        clear_cache = getattr(guild_logs_cog, "clear_config_cache", None)
        if callable(clear_cache):
            clear_cache(guild_id)

        for cog_name in ("AutoModConfig", "AntiAltsConfig"):
            cog = self.bot.get_cog(cog_name)
            clear_cache = getattr(cog, "clear_config_cache", None)
            if callable(clear_cache):
                clear_cache(guild_id)

    @staticmethod
    def _hierarchy_error(ctx: Context, member: discord.Member) -> str | None:
        """Return a clear reason why a member cannot be moderated, if any."""
        if not ctx.guild:
            return "This action can only be used in a server."
        if member.id == ctx.author.id:
            return "You can't target yourself."
        if ctx.bot.user is not None and member.id == ctx.bot.user.id:
            return "You can't target me."
        author = ctx.author if isinstance(ctx.author, discord.Member) else None
        if (
            author is not None
            and author.top_role <= member.top_role
            and ctx.guild.owner_id != author.id
        ):
            return "You can't target someone with an equal or higher role."
        me = ctx.guild.me
        if me is not None and me.top_role <= member.top_role:
            return "I can't target someone with an equal or higher role."
        return None

    @staticmethod
    def _extract_ids(value: str) -> list[int]:
        """Extract Discord snowflakes from mentions, raw IDs, or a mixed string."""
        return [int(match) for match in re.findall(r"\d{17,20}", value)]

    @staticmethod
    def _member_choices(
        guild: discord.Guild | None, current: str
    ) -> list[discord.app_commands.Choice[str]]:
        """Suggest guild members by name or ID for target options."""
        if guild is None:
            return []
        query = current.casefold()
        matches = [
            member
            for member in guild.members
            if not query or query in f"{member.display_name} {member.id}".casefold()
        ]
        return [
            discord.app_commands.Choice(
                name=f"{member.display_name} ({member.id})", value=str(member.id)
            )
            for member in matches[:25]
        ]

    @classmethod
    def _parse_members(cls, ctx: Context, value: str) -> list[discord.Member]:
        """Resolve space/comma separated member mentions or IDs in this guild."""
        if not ctx.guild:
            return []

        members: list[discord.Member] = []
        for member_id in cls._extract_ids(value):
            member = ctx.guild.get_member(member_id)
            if member is not None and member not in members:
                members.append(member)
        return members

    @classmethod
    def _parse_roles(cls, ctx: Context, value: str) -> list[discord.Role] | None:
        """Resolve role mentions or IDs, returning None if any token is invalid."""
        if not ctx.guild:
            return []

        roles: list[discord.Role] = []
        for token in value.replace(",", " ").split():
            ids = cls._extract_ids(token)
            role = ctx.guild.get_role(ids[0]) if ids else None
            if role is None:
                return None
            if role not in roles:
                roles.append(role)
        return roles

    @staticmethod
    def _parse_channel(
        ctx: Context, value: str
    ) -> discord.abc.GuildChannel | discord.Thread | None:
        """Resolve a channel mention or ID in this guild."""
        ids = Mod._extract_ids(value)
        if not ids or ctx.guild is None:
            return None
        return ctx.guild.get_channel_or_thread(ids[0])

    async def _set_logs(self, ctx: Context, channel: discord.TextChannel):
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
            "INSERT INTO logs_config (guild_id, module) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET module=$2",
            ctx.guild.id,
            ["all"],
        )
        self.clear_log_config_cache(ctx.guild.id)

        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Guild logs channel set to {channel.mention}\nDefault logging config set to `all`. Use `/mod logs modules:...` to change it."
            )
        )

    async def _set_logconfig(self, ctx: Context, modules: str = ""):
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
        `1.` `/logconfig modules:messages mod ...`
        `2.` `/logconfig modules:all`
        """

        if not ctx.guild or self.bot.db is None:
            return

        log_modules = modules.replace(",", " ").split()

        available_modules = list(_LOG_MODULES)

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
            "INSERT INTO logs_config (guild_id, module) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET module=$2",
            ctx.guild.id,
            lowercase_modules,
        )
        self.clear_log_config_cache(ctx.guild.id)

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

    async def _insights(self, ctx: Context):
        """Get detailed server insights."""

        if not ctx.guild or not self.bot.db:
            return

        guild = ctx.guild
        db = self.bot.db

        if ctx.interaction is not None:
            await ctx.defer()

        async with ctx.typing():
            today = datetime.datetime.utcnow().date()
            today_start = datetime.datetime.combine(today, datetime.time.min)

            total_members = guild.member_count
            online_members = sum(
                1 for m in guild.members if m.status != discord.Status.offline
            )
            leaves_today = 0

            try:
                async for _ in guild.audit_logs(
                    limit=50, action=discord.AuditLogAction.member_prune
                ):
                    if _.created_at.replace(tzinfo=None) >= today_start:
                        leaves_today += _.target.value  # type: ignore
            except (discord.HTTPException, AttributeError):
                pass

            warning_count = (
                await db.fetchval(
                    "SELECT COUNT(*) FROM warnlogs WHERE guild_id=$1", guild.id
                )
                or 0
            )

            starboard_count = (
                await db.fetchval(
                    "SELECT COUNT(*) FROM star_info WHERE guild_id=$1", guild.id
                )
                or 0
            )

            ticket_stats = await db.fetchrow(
                "SELECT COUNT(*) as total, COUNT(closed_at) as closed "
                "FROM ticket_logs WHERE guild_id=$1",
                guild.id,
            )
            active_tickets = (ticket_stats["total"] or 0) - (
                ticket_stats["closed"] or 0
            )

            top_warned = await db.fetch(
                "SELECT user_id, COUNT(*) as count FROM warnlogs "
                "WHERE guild_id=$1 GROUP BY user_id ORDER BY count DESC LIMIT 5",
                guild.id,
            )

            top_mods = await db.fetch(
                "SELECT mod_id, COUNT(*) as count FROM warnlogs "
                "WHERE guild_id=$1 GROUP BY mod_id ORDER BY count DESC LIMIT 5",
                guild.id,
            )

            warned_lines = []
            for w in top_warned:
                user = guild.get_member(w["user_id"])
                name = user.name if user else f"<@{w['user_id']}>"
                warned_lines.append(f"`{w['count']}` • {name}")

            mods_lines = []
            for m in top_mods:
                user = guild.get_member(m["mod_id"])
                name = user.name if user else f"<@{m['mod_id']}>"
                mods_lines.append(f"`{m['count']}` • {name}")

            total_tickets = ticket_stats["total"] or 0
            closed_tickets = ticket_stats["closed"] or 0
            open_tickets = total_tickets - closed_tickets

            closed_stats = await db.fetchrow(
                "SELECT COUNT(*) as closed, "
                "COALESCE(AVG(EXTRACT(EPOCH FROM (closed_at - opened_at))/60), 0) as avg_resolution "
                "FROM ticket_logs WHERE guild_id=$1 AND closed_at IS NOT NULL",
                guild.id,
            )
            avg_res = closed_stats["avg_resolution"] or 0

            top_staff = await db.fetch(
                "SELECT closed_by, COUNT(*) as count FROM ticket_logs "
                "WHERE guild_id=$1 AND closed_by IS NOT NULL "
                "GROUP BY closed_by ORDER BY count DESC LIMIT 5",
                guild.id,
            )

            staff_lines = []
            for s in top_staff:
                user = guild.get_member(s["closed_by"])
                name = user.name if user else f"<@{s['closed_by']}>"
                staff_lines.append(f"`{s['count']}` • {name}")

            automod_config = await db.fetchval(
                "SELECT enabled FROM automod WHERE guild_id=$1", guild.id
            )
            antialt_config = await db.fetchval(
                "SELECT enabled FROM antialt WHERE guild_id=$1", guild.id
            )
            logs_config = await db.fetchval(
                "SELECT channel_id FROM guild_logs WHERE guild_id=$1", guild.id
            )

            def check_enabled(val):
                return f"{self.bot.yes} Enabled" if val else f"{self.bot.no} Disabled"

            stats_em = await ctx_embed(
                ctx,
                title="📊 Server Insights",
                description=(
                    f"**{guild.name}**\n\n"
                    f"<:members:1268853443968106547> **Members:** `{total_members:,}`\n"
                    f"<:newmember:1268853457855709255> **Online:** `{online_members:,}`\n"
                    f"<:leave:1268858477997199436> **Leaves Today:** `{leaves_today}`\n"
                    f"<:ticketbadge:1268879389324611595> **Active Tickets:** `{active_tickets}`\n"
                    f"<:danger:1268855303768903733> **Warnings:** `{warning_count}`\n"
                    f"<:star:1268881885480620075> **Starboard:** `{starboard_count}`"
                ),
                timestamp=True,
            )
            stats_em.set_thumbnail(url=guild.icon.url if guild.icon else None)

            mod_em = await ctx_embed(
                ctx,
                title="<:certified_mod_badge:1268876753883889706> Moderation Insights",
                description=(
                    f"**Most Warned Users**\n"
                    f"{'- ' + chr(10) + '- '.join(warned_lines) if warned_lines else '`None`'}\n\n"
                    f"**Active Moderators**\n"
                    f"{'- ' + chr(10) + '- '.join(mods_lines) if mods_lines else '`None`'}\n\n"
                    f"⚡ AutoMod triggers • Check logs for details"
                ),
                timestamp=True,
            )
            mod_em.set_thumbnail(url=guild.icon.url if guild.icon else None)

            ticket_em = await ctx_embed(
                ctx,
                title="<:ticketbadge:1268879389324611595> Ticket Analytics",
                description=(
                    f"**Stats**\n"
                    f"📬 **Created:** `{total_tickets}`\n"
                    f"<:Unlocked:1390689325234258030> **Open:** `{open_tickets}`\n"
                    f"<:Locked:1390689313930608701> **Closed:** `{closed_tickets}`\n"
                    f"<:timer:1268872526549745736> **Avg Resolution:** `{f'{avg_res:.1f}m' if avg_res else 'N/A'}`\n\n"
                    f"<:squaredstaff:1268863165542961172> **Staff Leaderboard**\n"
                    f"{'- ' + chr(10) + '- '.join(staff_lines) if staff_lines else '`None`'}"
                ),
                timestamp=True,
            )
            ticket_em.set_thumbnail(url=guild.icon.url if guild.icon else None)

            config_em = await ctx_embed(
                ctx,
                title="<:discordcog:1497265278550016110> Configuration Status",
                description=(
                    f"<:wrench:1268855253768339476> **AutoMod:** {check_enabled(automod_config)}\n"
                    f"<:raidreport:1268857575919714376> **Anti-Alt:** {check_enabled(antialt_config)}\n"
                    f"<:logs:1497265635183431770> **Logs:** {check_enabled(logs_config)}\n"
                    f"<:ticketbadge:1268879389324611595> **Tickets:** {self.bot.yes} Enabled"
                ),
                timestamp=True,
            )
            config_em.set_thumbnail(url=guild.icon.url if guild.icon else None)

            # Workflow analytics
            workflow_total = (
                await db.fetchval(
                    "SELECT COUNT(*) FROM workflows WHERE guild_id=$1", guild.id
                )
                or 0
            )
            workflow_active = (
                await db.fetchval(
                    "SELECT COUNT(*) FROM workflows WHERE guild_id=$1 AND enabled=TRUE",
                    guild.id,
                )
                or 0
            )
            top_trigger = await db.fetchrow(
                "SELECT trigger_type, COUNT(*) AS count FROM workflows "
                "WHERE guild_id=$1 GROUP BY trigger_type ORDER BY count DESC LIMIT 1",
                guild.id,
            )
            top_trigger_str = (
                f"`{top_trigger['trigger_type']}` — `{top_trigger['count']}`"
                if top_trigger
                else "`None`"
            )

            workflow_em = await ctx_embed(
                ctx,
                title="⚡ Workflow Analytics",
                timestamp=True,
            )
            workflow_em.set_thumbnail(url=guild.icon.url if guild.icon else None)
            workflow_em.add_field(
                name="Workflows",
                value=(
                    f"`{workflow_active}` active / `{workflow_total}` total\n"
                    f"Top trigger: {top_trigger_str}"
                ),
                inline=False,
            )

            embeds = [stats_em, mod_em, ticket_em, config_em, workflow_em]
            for i, em in enumerate(embeds, 1):
                em.set_footer(text=f"Page {i}/{len(embeds)}")

            paginator = Paginator(ctx, embeds)
            await ctx.send(embed=stats_em, view=paginator)

    async def _prune(self, ctx: Context, days: int, roles: str = ""):
        """Kicks inactive members. Roles are space/comma separated mentions or IDs."""

        if not ctx.guild:
            return

        parsed_roles = self._parse_roles(ctx, roles)
        if parsed_roles is None:
            return await ctx.send(
                embed=red_embed(description=f"{self.bot.no} Invalid role provided.")
            )

        if ctx.interaction is not None:
            await ctx.defer()

        reason = f"Prune members initiated by {ctx.author}"
        confirm = ConfirmationView(ctx, 60)
        est_pruned = await ctx.guild.estimate_pruned_members(
            days=days, roles=parsed_roles
        )
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
                days=days, roles=parsed_roles, reason=reason, compute_prune_count=False
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

    async def _modnick(self, ctx: Context, member: discord.Member):
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

    async def _setnick(self, ctx: Context, member: discord.Member, *, nick: str):
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

    async def _decancer(self, ctx: Context, member: discord.Member):
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

    async def _slowmode(self, ctx: Context, seconds: Optional[int] = None):
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
            (
                discord.TextChannel,
                discord.StageChannel,
                discord.ForumChannel,
                discord.Thread,
            ),
        ):
            if seconds is None:
                seconds = ctx.channel.slowmode_delay
                return await ctx.send(
                    embed=await ctx_embed(
                        ctx,
                        description=f"The slowmode in this channel is `{seconds}` seconds",
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

    async def _lock_group(self, ctx: Context):
        """Lock management commands."""

        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    async def _lock_channel(
        self,
        ctx: Context,
        role: discord.Role | None = None,
        channel: discord.TextChannel | None = None,
    ):
        """
        Locks a channel with role requirement.
        If role is not given, the bot takes the default role of the guild which is @everyone.
        """

        if ctx.guild is not None:
            role = role or ctx.guild.default_role
            if channel is None and isinstance(ctx.channel, discord.TextChannel):
                channel = ctx.channel

            if isinstance(channel, discord.TextChannel):
                overwrite = channel.overwrites_for(role)
                overwrite.send_messages = False
                overwrite.add_reactions = False

                await channel.set_permissions(role, overwrite=overwrite)
                if ctx.interaction is None:
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

    async def _lock_server(self, ctx: Context, role: discord.Role | None):
        """
        Locks the whole server with role requirement.
        If role is not given, the bot takes the default role of the guild which is @everyone.
        """

        if ctx.guild is not None:
            role = ctx.guild.default_role or role
            reason = f"Action done by {ctx.author}"
            if ctx.interaction is not None:
                await ctx.defer()
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
                description="The server has been locked by a staff member. You are **not timed out**.",
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

    async def _unlock_group(self, ctx: Context):
        """Unlock management commands."""

        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    async def _unlock_channel(
        self,
        ctx: Context,
        role: discord.Role | None = None,
        channel: discord.TextChannel | None = None,
    ):
        """
        Unlocks a channel with role requirement.
        If role is not given, the bot takes the default role of the guild which is @everyone.
        """

        if ctx.guild is not None:
            role = role or ctx.guild.default_role
            if channel is None and isinstance(ctx.channel, discord.TextChannel):
                channel = ctx.channel

            if isinstance(channel, discord.TextChannel):
                overwrite = channel.overwrites_for(role)
                overwrite.send_messages = True
                overwrite.add_reactions = True

                await channel.set_permissions(role, overwrite=overwrite)
                if ctx.interaction is None:
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

    async def _unlock_server(self, ctx: Context, role: discord.Role | None):
        """
        Unlocks the whole server with role requirement.
        If role is not given, the bot takes the default role of the guild which is @everyone.
        """

        if ctx.guild is not None:
            role = ctx.guild.default_role or role
            reason = f"Action done by {ctx.author}"
            if ctx.interaction is not None:
                await ctx.defer()
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

    async def _hide(
        self,
        ctx: Context,
        role: discord.Role | None = None,
        channel: discord.TextChannel | None = None,
    ):
        """
        Hides a channel.
        If no role is given, defaults to @everyone.
        """

        if ctx.guild is not None:
            role = role or ctx.guild.default_role
            if channel is None and isinstance(ctx.channel, discord.TextChannel):
                channel = ctx.channel

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

    async def _expose(
        self,
        ctx: Context,
        role: discord.Role | None = None,
        channel: discord.TextChannel | None = None,
    ):
        """
        Exposes a channel.
        If no role is given, defaults to @everyone."""

        if ctx.guild is not None:
            role = role or ctx.guild.default_role
            if channel is None and isinstance(ctx.channel, discord.TextChannel):
                channel = ctx.channel

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

    async def _purge_messages(self, ctx: Context, amount: int = 100):
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
            if ctx.interaction is None:
                await ctx.message.delete()
            if isinstance(
                ctx.channel,
                (
                    discord.TextChannel,
                    discord.StageChannel,
                    discord.VoiceChannel,
                    discord.Thread,
                ),
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

    async def _cleanup_bots(self, ctx: Context, amount: int = 100):
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
                (
                    discord.TextChannel,
                    discord.StageChannel,
                    discord.ForumChannel,
                    discord.Thread,
                ),
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

    async def _kick(self, ctx: Context, member: discord.Member, *, reason: str | None):
        """Kicks a member."""

        reason = reason or f"Kicked by {ctx.author} (ID: {ctx.author.id})"
        await member.kick(reason=reason)
        await ctx.send(
            embed=green_embed(description=f"{self.bot.yes} Kicked {member.mention}")
        )

    async def _masskick(
        self,
        ctx: Context,
        members: str,
        *,
        reason: str | None,
    ):
        """
        Kick multiple members.
        You can only kick users who are in the server.
        Supply space/comma separated member mentions or IDs.
        """

        targets = self._parse_members(ctx, members)
        if not targets:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} One or more required arguments are missing."
                )
            )

        for member in targets:
            reason = reason or f"Kicked by {ctx.author} (ID: {ctx.author.id})"
            await member.kick(reason=reason)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Kicked {len(targets)} members"
            )
        )

    async def _ban(self, ctx: Context, member: str, *, reason: str | None):
        """
        Bans a member whether or not they're in the server.
        Supply a member mention or a user ID.
        """

        reason = reason or f"Banned by {ctx.author} (ID: {ctx.author.id})"

        if ctx.guild is None:
            return

        ids = self._extract_ids(member)
        if not ids:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Could not resolve a member mention or user ID."
                )
            )

        user_id = ids[0]
        target = ctx.guild.get_member(user_id)
        if target is not None:
            await target.ban(reason=f"{reason}")
            await ctx.send(
                embed=green_embed(description=f"{self.bot.yes} Banned {target.mention}")
            )
        else:
            await ctx.guild.ban(discord.Object(id=user_id), reason=f"{reason}")
            try:
                user = await self.bot.fetch_user(user_id)
            except discord.HTTPException:
                user = None
            display = str(user) if user is not None else f"<@{user_id}>"
            await ctx.send(
                embed=green_embed(description=f"{self.bot.yes} Banned {display}")
            )

    async def _banlist(self, ctx: Context):
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
                em = await ctx_embed(
                    ctx,
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

    async def _massban(
        self,
        ctx: Context,
        members: str,
        *,
        reason: str | None,
    ):
        """
        Mass bans multiple members.
        You can only ban users, who are in the server.
        Supply space/comma separated member mentions or IDs.
        """

        targets = self._parse_members(ctx, members)
        if not targets:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} One or more required arguments are missing."
                )
            )

        audit = reason or f"Banned by {ctx.author} (ID: {ctx.author.id})"
        for target in targets:
            await target.ban(reason=audit)
            await ctx.send(
                embed=green_embed(description=f"{self.bot.yes} Banned {target}")
            )

    async def _softban(
        self, ctx: Context, member: discord.Member, *, reason: str | None
    ):
        """Soft bans a member.

        A softban is basically banning the member from the server but
        then unbanning the member as well. This allows you to essentially
        kick the member while removing their messages.
        """

        if not ctx.guild:
            return

        reason = reason or f"Banned by {ctx.author} (ID: {ctx.author.id})"
        await ctx.guild.ban(member, reason=reason)
        await ctx.guild.unban(member, reason=reason)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Sucessfully soft-banned {member.mention}."
            )
        )

    async def _unban(self, ctx: Context, id: int):
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

    async def _timeout(
        self,
        ctx: Context,
        member: discord.Member,
        duration: str,
        *,
        reason: str | None,
    ):
        """
        Timeouts a member for a specific duration.
        Maximum duration of timeout: 28 days (API limitation)
        Use 5m for 5 mins, 1h for 1 hour etc...
        """

        reason = reason or f"Action done by {ctx.author}"
        _, error = _validate_duration(duration)
        if error is not None:
            return await ctx.send(
                embed=red_embed(description=f"{self.bot.no} {error}")
            )
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

    async def _remove_timeout(self, ctx: Context, member: discord.Member, *, reason: str | None):
        """Removes a member from timeout."""

        reason = reason or f"Action done by {ctx.author}"
        await member.timeout(None, reason=reason)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} {member.mention} has been removed from timeout!"
            )
        )

    async def _addrole(self, ctx: Context, user: discord.Member, *, role: discord.Role):
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
                embed=await ctx_embed(
                    ctx, description=f"{user.mention} already has {role.mention} role."
                )
            )

    async def _removerole(
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
                embed=await ctx_embed(
                    ctx,
                    description=f"{user.mention} does not have {role.mention} role.",
                )
            )

    async def _clone_role(self, ctx: Context, role: discord.Role):
        """Clone a role."""
        if not ctx.guild:
            return

        if role.position >= ctx.guild.me.top_role.position:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} You can't clone a role that is above the highest role in the server."
                )
            )

        new_role = await ctx.guild.create_role(
            name=role.name,
            permissions=role.permissions,
            colour=role.colour,
            hoist=role.hoist,
            mentionable=role.mentionable,
            reason=f"Role cloned by {ctx.author}",
        )

        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Role **{new_role.mention}** cloned successfully!"
            )
        )

    async def _create_role(
        self,
        ctx: Context,
        name: str,
        color: str | None = None,
        hoist: bool = False,
    ):
        """Create a new role with color and hoist options."""

        parsed_color: discord.Color = discord.Color.default()
        if color:
            try:
                parsed_color = discord.Color.from_str(color)
            except ValueError:
                named = getattr(
                    discord.Color, color.strip().lower().replace(" ", "_"), None
                )
                if not callable(named):
                    return await ctx.send(
                        embed=red_embed(
                            description=f"{self.bot.no} Invalid color: `{color}`."
                        )
                    )
                parsed_color = cast(discord.Color, named())

        if ctx.guild is not None:
            await ctx.guild.create_role(
                reason=f"Role created by {ctx.author}",
                name=name,
                color=parsed_color,
                hoist=hoist,
            )
            await ctx.send(
                embed=green_embed(
                    description=f"{self.bot.yes} Role created successfully!"
                )
            )

    async def _delete_role(self, ctx: Context, *, role: discord.Role):
        """Delete a role."""

        if ctx.guild is not None:
            if role in ctx.guild.roles:
                await role.delete()
                await ctx.send(
                    embed=green_embed(
                        description=f"{self.bot.yes} Role deleted successfully!"
                    )
                )

    async def _role_list(self, ctx: Context):
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
                    (
                        await ctx_embed(
                            ctx,
                            title=f"{ctx.guild.name} Roles ({len(roles)})",
                            description=description,
                            timestamp=True,
                        )
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

    async def _create_channel(self, ctx: Context, name: str):
        """Creates a new channel."""

        if ctx.guild is not None:
            await ctx.guild.create_text_channel(name)
            await ctx.send(
                embed=green_embed(
                    description=f"{self.bot.yes} Channel created successfully!"
                )
            )

    async def _delete_channel(self, ctx: Context, channel: discord.TextChannel):
        """Delete a channel."""

        await channel.delete()
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Channel deleted successfully!"
            )
        )

    async def _channel_list(self, ctx: Context):
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
                    (
                        await ctx_embed(
                            ctx,
                            title=f"{ctx.guild.name} Channels ({len(channels)})",
                            description=description,
                            timestamp=True,
                        )
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
                    (
                        await ctx_embed(
                            ctx,
                            title=f"{ctx.guild.name} Channels ({len(channels)})",
                            description=description,
                            timestamp=True,
                        )
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

    async def _channel_topic(
        self,
        ctx: Context,
        channel: str | None = None,
        *,
        text: str,
    ):
        """
        Change the channel topic.
        If no channel is given, it will default to the current channel.
        Supply a channel mention or ID when specifying one.
        """

        target = self._parse_channel(ctx, channel) if channel else ctx.channel
        if target is None or not isinstance(
            target, (discord.TextChannel, discord.ForumChannel)
        ):
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} You can only change the topic of text/forum channels."
                )
            )

        try:
            await target.edit(topic=text)  # type: ignore

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

    async def _warn(
        self,
        ctx: Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided.",
    ):
        """Warn a member. Auto-actions fire if warn thresholds are configured."""

        if not ctx.guild or not self.bot.db:
            return

        if member.id in (ctx.author.id, self.bot.user.id):  # type: ignore
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} You can't warn yourself or the bot."
                )
            )

        if (
            ctx.author.top_role.position <= member.top_role.position  # type: ignore
            and ctx.guild.owner_id != ctx.author.id
        ):
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} You can't warn someone with an equal or higher role."
                )
            )

        if ctx.guild.me.top_role.position <= member.top_role.position:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} I can't warn someone with a higher or equal role to mine."
                )
            )

        full_reason = f"{reason}  [by {ctx.author} ({ctx.author.id})]"
        await self.bot.db.execute(
            "INSERT INTO warnlogs (guild_id, user_id, mod_id, reason) VALUES ($1,$2,$3,$4)",
            ctx.guild.id,
            member.id,
            ctx.author.id,
            full_reason,
        )

        warn_count: int = (
            await self.bot.db.fetchval(
                "SELECT COUNT(*) FROM warnlogs WHERE user_id=$1 AND guild_id=$2",
                member.id,
                ctx.guild.id,
            )
            or 0
        )

        automod_cog = self.bot.get_cog("AutoModConfig")
        thresholds: list[dict] = []

        if automod_cog and hasattr(automod_cog, "_get_thresholds"):
            thresholds = await automod_cog._get_thresholds(ctx.guild.id)  # type: ignore[union-attr]

        next_action_str = ""
        for t in sorted(thresholds, key=lambda x: x["warns"]):
            if t["warns"] > warn_count:
                next_action_str = (
                    f"\n⚠️ Next action at **{t['warns']} warns**: "
                    f"{t['action'].replace('_', ' ').title()}"
                )
                break

        em = orange_embed(
            title="<:warning:1268855244033363968>  Member Warned",
            description=(
                f"**Member:** {member.mention}\n"
                f"**Moderator:** {ctx.author.mention}\n"
                f"**Reason:** {reason}\n"
                f"**Total warns:** `{warn_count}`" + next_action_str
            ),
            timestamp=True,
        )
        em.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        em.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=em)

        try:
            dm_em = orange_embed(
                title=f"You received a warning in {ctx.guild.name}",
                description=(
                    f"**Reason:** {reason}\n"
                    f"**Moderator:** {ctx.author}\n"
                    f"**Your total warns:** `{warn_count}`" + next_action_str
                ),
                timestamp=True,
            )
            dm_em.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else None)
            await member.send(embed=dm_em)
        except discord.HTTPException:
            pass

        if automod_cog and hasattr(automod_cog, "check_warn_threshold"):
            await automod_cog.check_warn_threshold(member.id, ctx.guild.id)  # type: ignore[union-attr]

    async def _warnings(
        self,
        ctx: Context,
        member: discord.User | discord.Member | None = None,
    ):
        """Show all warnings for a member (defaults to yourself)."""

        member = member or ctx.author
        if not ctx.guild or not self.bot.db:
            return

        records = await self.bot.db.fetch(
            "SELECT id, reason, mod_id, created_at FROM warnlogs "
            "WHERE user_id=$1 AND guild_id=$2 ORDER BY id DESC",
            member.id,
            ctx.guild.id,
        )

        if not records:
            em = green_embed(
                title=f"Warnings — {member.name}",
                description="✨ This member has no warnings.",
                timestamp=True,
            )
            em.set_thumbnail(url=member.display_avatar.url)
            return await ctx.send(embed=em)

        automod_cog = self.bot.get_cog("AutoModConfig")
        thresholds: list[dict] = []
        if automod_cog and hasattr(automod_cog, "_get_thresholds"):
            thresholds = await automod_cog._get_thresholds(ctx.guild.id)  # type: ignore[union-attr]

        total = len(records)
        threshold_note = ""
        for t in sorted(thresholds, key=lambda x: x["warns"]):
            if total >= t["warns"]:
                threshold_note = (
                    f"\n⚠️ **{t['warns']}-warn threshold** reached → "
                    f"**{t['action'].replace('_', ' ').title()}**"
                )

        chunks = [records[i : i + 5] for i in range(0, total, 5)]
        embeds: list[discord.Embed] = []

        for i, chunk in enumerate(chunks, 1):
            lines = []
            for r in chunk:
                mod = ctx.guild.get_member(r["mod_id"])
                mod_str = mod.mention if mod else f"`{r['mod_id']}`"
                reason_display = r["reason"].split("  [by ")[0]
                ts = (
                    f"<t:{int(r['created_at'].timestamp())}:R>"
                    if r["created_at"]
                    else ""
                )
                lines.append(
                    f"**ID `{r['id']}`** {ts}\n"
                    f"Reason: {reason_display}\n"
                    f"Moderator: {mod_str}\n"
                )

            em = await ctx_embed(
                ctx,
                title=f"Warnings — {member.name}  ({total} total)",
                description="\n".join(lines) + threshold_note,
                timestamp=True,
            )
            em.set_thumbnail(url=member.display_avatar.url)
            em.set_footer(text=f"Page {i}/{len(chunks)}")
            embeds.append(em)

        if len(embeds) == 1:
            return await ctx.send(embed=embeds[0])

        view = Paginator(ctx, embeds)
        await ctx.send(embed=embeds[0], view=view)

    async def _deletewarn(self, ctx: Context, member: discord.Member, warn_id: int):
        """Delete a specific warning by its ID."""

        if not ctx.guild or not self.bot.db:
            return

        result = await self.bot.db.execute(
            "DELETE FROM warnlogs WHERE id=$1 AND user_id=$2 AND guild_id=$3",
            warn_id,
            member.id,
            ctx.guild.id,
        )

        if result == "DELETE 0":
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Warn ID `{warn_id}` not found for {member.mention}."
                )
            )
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Warn ID `{warn_id}` deleted for {member.mention}."
            )
        )

    async def _clearwarns(self, ctx: Context, member: discord.Member):
        """Clear ALL warnings for a member.  [Basic]"""

        if not ctx.guild or not self.bot.db:
            return

        count: int = (
            await self.bot.db.fetchval(
                "SELECT COUNT(*) FROM warnlogs WHERE user_id=$1 AND guild_id=$2",
                member.id,
                ctx.guild.id,
            )
            or 0
        )

        if count == 0:
            return await ctx.send(
                embed=orange_embed(
                    description=f"{self.bot.no} {member.mention} has no warnings to clear."
                )
            )

        if ctx.interaction is not None:
            await ctx.defer()
        confirm = ConfirmationView(ctx, 30)
        msg = await ctx.send(
            embed=orange_embed(
                description=(
                    f"<:warning:1268855244033363968> This will permanently delete "
                    f"**{count}** warning(s) for {member.mention}. Are you sure?"
                )
            ),
            view=confirm,
        )
        await confirm.wait()

        if not confirm.value:
            return await msg.edit(
                embed=red_embed(description="Cancelled — no warns were deleted."),
                view=None,
            )

        await self.bot.db.execute(
            "DELETE FROM warnlogs WHERE user_id=$1 AND guild_id=$2",
            member.id,
            ctx.guild.id,
        )
        await msg.edit(
            embed=green_embed(
                description=f"{self.bot.yes} Cleared **{count}** warning(s) for {member.mention}."
            ),
            view=None,
        )


    # ── grouped moderation surface ────────────────────────────────────────────

    @commands.hybrid_group(name="mod", help="Moderation and server management.")
    @commands.guild_only()
    async def mod(self, ctx: Context) -> Any:
        """Moderation and server management commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send(
                embed=green_embed(
                    description=(
                        "Use `/mod <command>`. Popular options: `/mod ban`, "
                        "`/mod kick`, `/mod warn`, `/mod clear`, `/mod role`, "
                        "`/mod channel`."
                    )
                )
            )

    @mod.command(name="ban")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    @discord.app_commands.describe(
        targets="One or more member mentions or user IDs",
        soft="Ban and immediately unban to purge recent messages",
        reason="Reason shown in the audit log",
    )
    async def ban(
        self,
        ctx: Context,
        targets: str,
        soft: bool = False,
        *,
        reason: str | None = None,
    ) -> Any:
        """Ban one or more members; soft:true bans then unbans them."""
        ids = self._extract_ids(targets)
        if not ids or ctx.guild is None:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Provide at least one member mention or user ID."
                )
            )

        audit = reason or f"Banned by {ctx.author} (ID: {ctx.author.id})"
        if soft:
            banned: list[str] = []
            for user_id in ids:
                member = ctx.guild.get_member(user_id)
                try:
                    await ctx.guild.ban(member or discord.Object(id=user_id), reason=audit)
                    await ctx.guild.unban(discord.Object(id=user_id), reason=audit)
                    banned.append(f"<@{user_id}>")
                except discord.HTTPException:
                    continue
            if not banned:
                return await ctx.send(
                    embed=red_embed(
                        description=f"{self.bot.no} Could not soft-ban those users."
                    )
                )
            return await ctx.send(
                embed=green_embed(
                    description=f"{self.bot.yes} Soft-banned {', '.join(banned)}."
                )
            )

        if len(ids) == 1:
            await self._ban(ctx, targets, reason=reason)
        else:
            await self._massban(ctx, targets, reason=reason)

    @ban.autocomplete("targets")
    async def ban_target_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[discord.app_commands.Choice[str]]:
        """Suggest members for /mod ban."""
        return self._member_choices(interaction.guild, current)

    @mod.command(name="unban")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @discord.app_commands.describe(user_id="Discord user ID to unban")
    async def unban(self, ctx: Context, user_id: int) -> Any:
        """Unban a user by ID."""
        await self._unban(ctx, user_id)

    @mod.command(name="banlist")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.cooldown(1, 10, commands.BucketType.guild)
    async def banlist(self, ctx: Context) -> Any:
        """List banned users in this server."""
        await self._banlist(ctx)

    @mod.command(name="kick")
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    @discord.app_commands.describe(
        targets="One or more member mentions or IDs (members must be in the server)",
        reason="Reason shown in the audit log",
    )
    async def kick(
        self, ctx: Context, targets: str, *, reason: str | None = None
    ) -> Any:
        """Kick one or more members currently in the server."""
        ids = self._extract_ids(targets)
        if not ids or ctx.guild is None:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Provide at least one member mention or ID."
                )
            )
        if len(ids) == 1:
            member = ctx.guild.get_member(ids[0])
            if member is None:
                return await ctx.send(
                    embed=red_embed(
                        description=f"{self.bot.no} That member is not in this server."
                    )
                )
            await self._kick(ctx, member, reason=reason)
        else:
            await self._masskick(ctx, targets, reason=reason)

    @kick.autocomplete("targets")
    async def kick_target_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[discord.app_commands.Choice[str]]:
        """Suggest members for /mod kick."""
        return self._member_choices(interaction.guild, current)

    @mod.command(name="timeout")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @discord.app_commands.describe(
        member="Member to time out",
        duration="e.g. 10m or 1h; omit to remove an existing timeout",
        reason="Reason shown in the audit log",
    )
    async def timeout(
        self,
        ctx: Context,
        member: discord.Member,
        duration: str | None = None,
        *,
        reason: str | None = None,
    ) -> Any:
        """Timeout a member; omit the duration to remove their timeout."""
        if duration is None:
            await self._remove_timeout(ctx, member, reason=reason)
        else:
            await self._timeout(ctx, member, duration, reason=reason)

    @mod.command(name="warn")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @discord.app_commands.describe(
        member="Member to warn", reason="Why they are being warned"
    )
    async def warn(
        self, ctx: Context, member: discord.Member, *, reason: str = "No reason provided."
    ) -> Any:
        """Warn a member. Automod thresholds fire when configured."""
        await self._warn(ctx, member, reason=reason)

    @mod.command(name="warnings")
    @commands.guild_only()
    @commands.cooldown(1, 3, commands.BucketType.user)
    @discord.app_commands.describe(
        member="Member whose warnings to inspect (defaults to you)",
        warn_id="Delete this warning ID instead of listing",
        clear="Clear all warnings for the member (Basic tier)",
    )
    async def warnings(
        self,
        ctx: Context,
        member: discord.Member | None = None,
        warn_id: int | None = None,
        clear: bool = False,
    ) -> Any:
        """List warnings; supply warn_id to delete one or clear:true for all."""
        if clear:
            if member is None:
                return await ctx.send(
                    embed=red_embed(
                        description=f"{self.bot.no} Specify a member to clear warnings for."
                    )
                )
            try:
                await premium(Tier.BASIC).predicate(ctx)
            except commands.CheckFailure as exc:
                return await ctx.send(str(exc))
            await self._clearwarns(ctx, member)
        elif warn_id is not None:
            if member is None:
                return await ctx.send(
                    embed=red_embed(
                        description=f"{self.bot.no} Specify a member and warn ID."
                    )
                )
            await self._deletewarn(ctx, member, warn_id)
        else:
            await self._warnings(ctx, member)

    @mod.command(name="clear")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @discord.app_commands.describe(
        amount="How many messages to remove (max 100)",
        bot_only="Only remove messages sent by this bot",
    )
    async def clear(
        self, ctx: Context, amount: int = 100, bot_only: bool = False
    ) -> Any:
        """Clear messages; bot_only:true removes only this bot's messages."""
        if bot_only:
            await self._cleanup_bots(ctx, amount)
        else:
            await self._purge_messages(ctx, amount)

    @mod.command(name="slowmode")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @discord.app_commands.describe(
        seconds="Slowmode delay in seconds (0-21600); omit to view the current delay"
    )
    async def slowmode(self, ctx: Context, seconds: int | None = None) -> Any:
        """Show or set this channel's slowmode delay in seconds."""
        await self._slowmode(ctx, seconds)

    @mod.command(name="prune")
    @commands.guild_only()
    @commands.has_permissions(kick_members=True, manage_guild=True)
    @commands.bot_has_permissions(kick_members=True, manage_guild=True)
    @commands.cooldown(1, 10, commands.BucketType.guild)
    @discord.app_commands.describe(
        days="Inactivity window in days (1-30)",
        roles="Optional space/comma separated role mentions or IDs to include",
    )
    async def prune(self, ctx: Context, days: int, roles: str = "") -> Any:
        """Kick inactive members; roles are space/comma separated mentions or IDs."""
        await self._prune(ctx, days, roles)

    @mod.command(name="nick")
    @commands.guild_only()
    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @discord.app_commands.describe(
        member="Member to rename", nickname="New nickname; omit for a moderated one"
    )
    async def nick(
        self, ctx: Context, member: discord.Member, nickname: str | None = None
    ) -> Any:
        """Set a nickname; omit it to apply a moderated placeholder."""
        if nickname:
            await self._setnick(ctx, member, nick=nickname)
        else:
            await self._modnick(ctx, member)

    @mod.command(name="decancer")
    @commands.guild_only()
    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @discord.app_commands.describe(member="Member to rename")
    async def decancer(self, ctx: Context, member: discord.Member) -> Any:
        """Rename a member whose name starts with hoisting characters."""
        await self._decancer(ctx, member)

    @mod.command(name="visibility")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @discord.app_commands.describe(
        hide="True hides the channel, false exposes it",
        role="Role to apply this to (defaults to @everyone)",
        channel="Channel to change (defaults to the current one)",
    )
    async def visibility(
        self,
        ctx: Context,
        hide: bool = True,
        role: discord.Role | None = None,
        channel: discord.TextChannel | None = None,
    ) -> Any:
        """Hide or expose a channel for a role."""
        if hide:
            await self._hide(ctx, role, channel)
        else:
            await self._expose(ctx, role, channel)

    @mod.command(name="lock")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @discord.app_commands.describe(
        target="Lock just this channel or the whole server",
        locked="True locks, false unlocks",
        role="Role to restrict (defaults to @everyone)",
        channel="Channel to change (defaults to the current one)",
    )
    async def lock(
        self,
        ctx: Context,
        target: Literal["channel", "server"] = "channel",
        locked: bool = True,
        role: discord.Role | None = None,
        channel: discord.TextChannel | None = None,
    ) -> Any:
        """Lock or unlock a channel or the whole server."""
        if target == "channel":
            if locked:
                await self._lock_channel(ctx, role, channel)
            else:
                await self._unlock_channel(ctx, role, channel)
        elif locked:
            await self._lock_server(ctx, role)
        else:
            await self._unlock_server(ctx, role)

    @mod.command(name="role")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @discord.app_commands.describe(
        action="What to do with roles",
        member="Member for add/remove",
        role="Role for add/remove/delete/clone",
        name="Role name for create",
        color="Role color for create (hex or name)",
        hoist="Whether the created role is displayed separately",
    )
    async def role(
        self,
        ctx: Context,
        action: Literal["add", "remove", "create", "delete", "clone", "list"],
        member: discord.Member | None = None,
        role: discord.Role | None = None,
        name: str | None = None,
        color: str | None = None,
        hoist: bool = False,
    ) -> Any:
        """Manage roles with a single command."""
        missing = f"{self.bot.no} Provide the arguments needed for `{action}`."
        if action in ("add", "remove"):
            if member is None or role is None:
                return await ctx.send(embed=red_embed(description=missing))
            if action == "add":
                await self._addrole(ctx, member, role=role)
            else:
                await self._removerole(ctx, member, role=role)
        elif action == "create":
            if not name:
                return await ctx.send(embed=red_embed(description=missing))
            await self._create_role(ctx, name, color=color, hoist=hoist)
        elif action in ("delete", "clone"):
            if role is None:
                return await ctx.send(embed=red_embed(description=missing))
            if action == "delete":
                await self._delete_role(ctx, role=role)
            else:
                await self._clone_role(ctx, role)
        else:
            await self._role_list(ctx)

    @mod.command(name="channel")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @discord.app_commands.describe(
        action="What to do with channels",
        name="Name for create",
        channel="Channel for delete/topic (defaults to current for topic)",
        text="New topic for topic",
    )
    async def channel(
        self,
        ctx: Context,
        action: Literal["create", "delete", "list", "topic"],
        name: str | None = None,
        channel: discord.TextChannel | None = None,
        text: str | None = None,
    ) -> Any:
        """Manage channels with a single command."""
        missing = f"{self.bot.no} Provide the arguments needed for `{action}`."
        if action == "create":
            if not name:
                return await ctx.send(embed=red_embed(description=missing))
            await self._create_channel(ctx, name)
        elif action == "delete":
            if channel is None:
                return await ctx.send(embed=red_embed(description=missing))
            await self._delete_channel(ctx, channel)
        elif action == "topic":
            if text is None:
                return await ctx.send(embed=red_embed(description=missing))
            await self._channel_topic(ctx, str(channel.id) if channel else None, text=text)
        else:
            await self._channel_list(ctx)

    @mod.command(name="logs")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.cooldown(2, 60, commands.BucketType.user)
    @discord.app_commands.describe(
        channel="Log channel to use",
        modules="Space-separated modules to enable (all, mod, messages,...)",
    )
    async def logs(
        self,
        ctx: Context,
        channel: discord.TextChannel | None = None,
        modules: str = "",
    ) -> Any:
        """Set the log channel and/or the events that are logged."""
        if channel is None and not modules:
            return await ctx.send(
                embed=green_embed(
                    description="Use `channel:` to set the log channel and/or `modules:` to configure logging."
                )
            )
        if channel is not None:
            await self._set_logs(ctx, channel)
        if modules:
            await self._set_logconfig(ctx, modules)

    @logs.autocomplete("modules")
    async def logs_module_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[discord.app_commands.Choice[str]]:
        """Suggest valid logging modules."""
        query = current.casefold()
        return [
            discord.app_commands.Choice(name=module, value=module)
            for module in _LOG_MODULES
            if not query or query in module
        ]

    @mod.command(name="insights")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def insights(self, ctx: Context) -> Any:
        """Detailed server insights (Pro)."""
        try:
            await premium(Tier.PRO).predicate(ctx)
        except commands.CheckFailure as exc:
            return await ctx.send(str(exc))
        await self._insights(ctx)


# ── right-click quick actions ──────────────────────────────────────────────────


def _mod_cog(interaction: discord.Interaction) -> Mod:
    cog = cast(Zync, interaction.client).get_cog("Mod")
    if cog is None:
        raise discord.app_commands.CheckFailure("The moderation cog is not loaded.")
    return cast(Mod, cog)


def _context_cooldown_key(interaction: discord.Interaction) -> tuple[int | None, int]:
    """Mirror the slash commands' per-user cooldown bucket."""
    return interaction.guild_id, interaction.user.id


async def _reject_target(
    interaction: discord.Interaction, cog: Mod, member: discord.Member
) -> bool:
    """Reject hierarchy-invalid targets with a private, actionable message."""
    ctx = cast(Context, _InteractionContext(interaction))
    error = cog._hierarchy_error(ctx, member)
    if error is None:
        return False
    bot = cast(Zync, interaction.client)
    await interaction.response.send_message(
        embed=red_embed(description=f"{bot.no} {error}"), ephemeral=True
    )
    return True


@discord.app_commands.context_menu(name="Ban")
@discord.app_commands.guild_only()
@discord.app_commands.checks.has_permissions(ban_members=True)
@discord.app_commands.checks.bot_has_permissions(ban_members=True)
@discord.app_commands.checks.cooldown(1, 10, key=_context_cooldown_key)
async def ban_context(interaction: discord.Interaction, member: discord.Member) -> None:
    """Ban a member from the right-click menu (asks for a reason)."""
    cog = _mod_cog(interaction)
    if await _reject_target(interaction, cog, member):
        return
    await interaction.response.send_modal(_ReasonModal(cog, member, "ban"))


@discord.app_commands.context_menu(name="Kick")
@discord.app_commands.guild_only()
@discord.app_commands.checks.has_permissions(kick_members=True)
@discord.app_commands.checks.bot_has_permissions(kick_members=True)
@discord.app_commands.checks.cooldown(1, 10, key=_context_cooldown_key)
async def kick_context(interaction: discord.Interaction, member: discord.Member) -> None:
    """Kick a member from the right-click menu (asks for a reason)."""
    cog = _mod_cog(interaction)
    if await _reject_target(interaction, cog, member):
        return
    await interaction.response.send_modal(_ReasonModal(cog, member, "kick"))


@discord.app_commands.context_menu(name="Warn")
@discord.app_commands.guild_only()
@discord.app_commands.checks.has_permissions(manage_messages=True)
@discord.app_commands.checks.cooldown(1, 5, key=_context_cooldown_key)
async def warn_context(interaction: discord.Interaction, member: discord.Member) -> None:
    """Warn a member from the right-click menu (asks for a reason)."""
    cog = _mod_cog(interaction)
    if await _reject_target(interaction, cog, member):
        return
    await interaction.response.send_modal(_ReasonModal(cog, member, "warn"))


@discord.app_commands.context_menu(name="Timeout")
@discord.app_commands.guild_only()
@discord.app_commands.checks.has_permissions(moderate_members=True)
@discord.app_commands.checks.bot_has_permissions(moderate_members=True)
@discord.app_commands.checks.cooldown(1, 5, key=_context_cooldown_key)
async def timeout_context(interaction: discord.Interaction, member: discord.Member) -> None:
    """Timeout a member from the right-click menu (asks for duration and reason)."""
    cog = _mod_cog(interaction)
    if await _reject_target(interaction, cog, member):
        return
    await interaction.response.send_modal(_TimeoutModal(cog, member))


_CONTEXT_MENUS = (ban_context, kick_context, warn_context, timeout_context)


async def setup(bot: Zync) -> None:
    await bot.add_cog(Mod(bot))
    for command in _CONTEXT_MENUS:
        existing = bot.tree.get_command(
            command.name, type=discord.AppCommandType.user
        )
        if existing is not None:
            bot.tree.remove_command(
                command.name, type=discord.AppCommandType.user
            )
        bot.tree.add_command(command)
