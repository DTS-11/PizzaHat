from __future__ import annotations

import datetime
import time
from typing import Optional

import discord
from async_lru import alru_cache
from asyncpg import Record
from core.bot import PizzaHat
from core.cog import Cog
from utils.embed import orange_embed, red_embed


def _datetime_to_unix(t: datetime.datetime) -> int:
    current_time = datetime.datetime.fromtimestamp(time.time())
    return round(
        round(time.time()) + (current_time - t.replace(tzinfo=None)).total_seconds()
    )


class AntiAltsConfig(Cog):
    """Anti-Alt enforcement listener."""

    def __init__(self, bot: PizzaHat):
        self.bot = bot

    def clear_config_cache(self, guild_id: int | None = None) -> None:
        self._get_logs_channel.cache_clear()
        self._is_enabled.cache_clear()

    @alru_cache()
    async def _get_logs_channel(self, guild_id: int) -> discord.TextChannel | None:
        if not self.bot.db:
            return None

        channel_id = await self.bot.db.fetchval(
            "SELECT channel_id FROM guild_logs WHERE guild_id=$1", guild_id
        )
        if not channel_id:
            return None

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return None

        ch = guild.get_channel(channel_id) or await guild.fetch_channel(channel_id)
        return ch if isinstance(ch, discord.TextChannel) else None

    @alru_cache()
    async def _is_enabled(self, guild_id: int) -> bool:
        if not self.bot.db:
            return False
        return bool(
            await self.bot.db.fetchval(
                "SELECT enabled FROM antialt WHERE guild_id=$1", guild_id
            )
        )

    @Cog.listener(name="on_member_join")
    async def antialt_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        if not await self._is_enabled(member.guild.id):
            return
        if not self.bot.db:
            return

        data: Optional[Record] = await self.bot.db.fetchrow(
            "SELECT min_age, restricted_role, level FROM antialt WHERE guild_id=$1",
            member.guild.id,
        )
        if not data:
            return

        age_days = (
            datetime.datetime.now(datetime.timezone.utc) - member.created_at
        ).total_seconds() / 86400

        min_age: int = data["min_age"] or 7
        if age_days >= min_age:
            return

        level = data["level"] or 1
        role_id = data["restricted_role"]
        logs_channel = await self._get_logs_channel(member.guild.id)

        restricted_role = member.guild.get_role(role_id) if role_id else None

        account_created_unix = _datetime_to_unix(member.created_at)
        em = (
            orange_embed(
                title="<:raidreport:1268857575919714376>  Alt Account Detected",
                description=(
                    f"{member.mention} — {discord.utils.escape_markdown(str(member))}\n\n"
                    f"**Account Created:** <t:{account_created_unix}:F> "
                    f"(<t:{account_created_unix}:R>)\n"
                    f"**Account Age:** `{age_days:.1f}` days  (minimum: `{min_age}` days)\n"
                    f"**Protection Level:** `{level}`"
                ),
                timestamp=True,
            )
            .set_author(name=str(member), icon_url=member.display_avatar.url)
            .set_footer(text=f"User ID: {member.id}")
        )

        action_label = "Unknown"

        try:
            if level == 1:
                if restricted_role:
                    await member.add_roles(
                        restricted_role, reason="PizzaHat Anti-Alt: Account too new"
                    )
                    action_label = f"RESTRICTED (role: {restricted_role.name})"
                else:
                    until = discord.utils.utcnow() + datetime.timedelta(hours=24)
                    await member.timeout(
                        until,
                        reason="PizzaHat Anti-Alt: Account too new — no restricted role set",
                    )
                    action_label = "TIMED OUT 24h (no restricted role configured)"

            elif level == 2:
                if member.guild.me.guild_permissions.kick_members:
                    await member.kick(reason="PizzaHat Anti-Alt: Account too new")
                    action_label = "KICKED"

                    await self.bot.db.execute(
                        "INSERT INTO warnlogs (guild_id, user_id, mod_id, reason) "
                        "VALUES ($1, $2, $3, $4)",
                        member.guild.id,
                        member.id,
                        self.bot.user.id,  # type: ignore
                        "Anti-Alt: Kicked for new account (ban on rejoin active for 24h)",
                    )

            elif level >= 3:
                if member.guild.me.guild_permissions.ban_members:
                    await member.ban(
                        reason="PizzaHat Anti-Alt: Account too new",
                        delete_message_days=0,
                    )
                    action_label = "BANNED"

        except discord.HTTPException as e:
            action_label = f"FAILED ({e})"

        em.add_field(name="Action Taken", value=f"`{action_label}`", inline=False)

        if logs_channel:
            await self.bot.send_log(logs_channel, embed=em)

        if level != 2:
            try:
                await self.bot.db.execute(
                    "INSERT INTO warnlogs (guild_id, user_id, mod_id, reason) "
                    "VALUES ($1, $2, $3, $4)",
                    member.guild.id,
                    member.id,
                    self.bot.user.id,  # type: ignore
                    f"Anti-Alt: Account age {age_days:.1f}d < minimum {min_age}d → {action_label}",
                )
            except Exception:
                pass

    @Cog.listener(name="on_member_join")
    async def antialt_ban_on_rejoin(self, member: discord.Member) -> None:
        """
        Secondary listener: if a member was previously Anti-Alt kicked (level 2)
        and rejoins within 24 hours, escalate to ban.
        """

        if member.bot or not self.bot.db:
            return
        if not await self._is_enabled(member.guild.id):
            return

        data: Optional[Record] = await self.bot.db.fetchrow(
            "SELECT level FROM antialt WHERE guild_id=$1", member.guild.id
        )
        if not data or data["level"] != 2:
            return

        recent_kick = await self.bot.db.fetchrow(
            "SELECT id FROM warnlogs WHERE guild_id=$1 AND user_id=$2 "
            "AND reason LIKE 'Anti-Alt: Kicked%' "
            "AND (NOW() - INTERVAL '24 hours') < NOW()",
            member.guild.id,
            member.id,
        )

        if not recent_kick:
            return

        try:
            await member.ban(
                reason="PizzaHat Anti-Alt: Rejoined after Level 2 kick",
                delete_message_days=0,
            )
        except discord.HTTPException:
            return

        logs_channel = await self._get_logs_channel(member.guild.id)
        if logs_channel:
            em = red_embed(
                title="<:ban:1268874381648465920>  Rejoin Ban — Anti-Alt",
                description=(
                    f"{member.mention} was previously **kicked** by Anti-Alt and attempted to rejoin.\n"
                    f"They have been **permanently banned**."
                ),
                timestamp=True,
            )
            em.set_author(name=str(member), icon_url=member.display_avatar.url)
            em.set_footer(text=f"User ID: {member.id}")
            await self.bot.send_log(logs_channel, embed=em)


async def setup(bot: PizzaHat) -> None:
    await bot.add_cog(AntiAltsConfig(bot))
