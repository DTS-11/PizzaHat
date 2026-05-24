import discord

from core.bot import PizzaHat
from core.cog import Cog
from core.database import get_prefix
from utils.config import LOGS_CHANNEL
from utils.embed import (
    green_embed,
    guild_embed,
    invalidate_theme_cache,
    red_embed,
)


class Events(Cog):
    """Events cog"""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot
        self._auto_left: dict[int, str] = {}  # guild_id -> leave reason
        # bot.loop.create_task(self.update_stats())

    async def _get_bot_logs_channel(self) -> discord.TextChannel | None:
        channel = self.bot.get_channel(LOGS_CHANNEL)

        if channel is None:
            try:
                channel = await self.bot.fetch_channel(LOGS_CHANNEL)
            except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                return None

        return channel if isinstance(channel, discord.TextChannel) else None

    async def _send_bot_logs_embed(self, embed: discord.Embed) -> None:
        channel = await self._get_bot_logs_channel()
        if channel is None:
            return

        await self.bot.send_log(channel, embed=embed)

    async def _get_leave_reason(self, guild: discord.Guild) -> tuple[str, bool]:
        auto_reason = self._auto_left.pop(guild.id, None)
        if auto_reason:
            return f"Auto-left: {auto_reason}", True

        if self.bot.user is None:
            return "Removed or left. Audit details unavailable.", False

        actions_to_try: list[discord.AuditLogAction] = []
        for name in ("bot_remove", "kick"):
            action = getattr(discord.AuditLogAction, name, None)
            if action is not None:
                actions_to_try.append(action)

        if not actions_to_try:
            return "Left voluntarily", False

        try:
            for action in actions_to_try:
                async for entry in guild.audit_logs(limit=5, action=action):
                    if not entry.target or entry.target.id != self.bot.user.id:
                        continue
                    if (
                        discord.utils.utcnow() - entry.created_at
                    ).total_seconds() >= 30:
                        continue

                    # Bot kicked itself = voluntary leave (e.g. guild.leave())
                    if entry.user and entry.user.id == self.bot.user.id:
                        return "Left voluntarily", False

                    moderator = (
                        str(entry.user) if entry.user else "Unknown moderator"
                    )
                    if entry.reason:
                        return f"Kicked by {moderator}: {entry.reason}", False
                    return f"Kicked by {moderator}", False
        except discord.Forbidden:
            return "Removed from guild. Missing audit log access.", False
        except discord.HTTPException:
            return "Removed from guild. Audit details unavailable.", False

        return "Left voluntarily", False

    # @tasks.loop(hours=24)
    # async def update_stats(self):
    #     try:
    #         # Top.gg
    #         await self.bot.wait_until_ready()
    #         self.topggpy = topgg.DBLClient(self, TOPGG_TOKEN, autopost=True)  # type: ignore
    #         await self.topggpy.post_guild_count()
    #         print(f"Posted server count: {self.topggpy.guild_count}")

    #     except Exception as e:
    #         print(e)

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
        return

    # ====== BOT PING MSG ======

    @Cog.listener()
    async def on_message(self, msg: discord.Message):
        if self.bot and self.bot.user is not None:
            bot_id = self.bot.user.id

            if msg.author.bot:
                return

            if self.bot.user == msg.author:
                return

            if msg.content in {f"<@{bot_id}>", f"<@!{bot_id}>"}:
                prefix = (
                    await get_prefix(self.bot.db, msg.guild.id if msg.guild else 0)
                    or "p!"
                )
                em = await guild_embed(
                    self.bot.db,
                    msg.guild.id if msg.guild else 0,
                    "Hello! <a:wave_animated:783393435242463324>",
                    f"I'm {self.bot.user.name} — Your Ultimate Discord Companion!\nTo get started, my prefix is `{prefix}` or <@{bot_id}>",
                )

                await msg.channel.send(embed=em)

    # ====== BOT GUILD JOIN/LEAVE ======

    @Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        chunked = False
        try:
            await guild.chunk()
            chunked = True
        except Exception:
            pass

        em = green_embed(
            title="Guild Joined",
            timestamp=True,
        )
        em.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)

        em.add_field(name="Guild Name", value=guild.name, inline=False)
        em.add_field(
            name="Members",
            value=len([m for m in guild.members if not m.bot]),
            inline=False,
        )
        em.add_field(
            name="Bots", value=sum(member.bot for member in guild.members), inline=False
        )
        if guild.owner:
            em.add_field(
                name="Owner", value=f"{guild.owner} ({guild.owner.id})", inline=False
            )

        await self._send_bot_logs_embed(em)

        # Auto-leave detection requires a full member view. If chunking failed or
        # cached members don't cover the whole guild, skip — otherwise we'd
        # auto-leave every guild we join (only the bot itself would be cached).
        if not chunked:
            return
        if guild.member_count is not None and len(guild.members) < guild.member_count:
            return

        bots = sum(1 for m in guild.members if m.bot)
        humans = sum(1 for m in guild.members if not m.bot)

        total = bots + humans
        bot_ratio = bots / total if total > 0 else 0

        reason = None
        if bot_ratio >= 0.70:
            reason = (
                f"it has a high bot-to-member ratio ({round(bot_ratio * 100)}% bots)"
            )
        elif humans <= 3:
            reason = f"it has too few real members ({humans} human{'s' if humans != 1 else ''})"

        if reason:
            self._auto_left[guild.id] = reason
            try:
                ch = guild.system_channel or next(
                    (
                        c
                        for c in guild.text_channels
                        if c.permissions_for(guild.me).send_messages
                    ),
                    None,
                )
                if ch:
                    await ch.send(
                        f"👋 I've automatically left this server because {reason}. Bye!"
                    )
                await guild.leave()
            except Exception:
                # If leaving failed, drop the stale auto-left marker so a later
                # legitimate kick doesn't get mislabeled as an auto-leave.
                self._auto_left.pop(guild.id, None)
            return

    @Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        for cog_name in (
            "AntiAlts",
            "AntiAltsConfig",
            "AutomationEvents",
            "AutoModeration",
            "AutoModConfig",
            "GuildLogs",
            "StarboardEvents",
        ):
            cog = self.bot.get_cog(cog_name)
            clear_cache = getattr(cog, "clear_config_cache", None) or getattr(
                cog, "clear_cache", None
            )
            if callable(clear_cache):
                clear_cache(guild.id)

        invalidate_theme_cache(guild.id)
        leave_reason, was_auto_left = await self._get_leave_reason(guild)

        em = red_embed(
            title="Guild Left",
            timestamp=True,
        )
        em.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)

        em.add_field(name="Guild Name", value=guild.name, inline=False)
        em.add_field(
            name="Members",
            value=guild.member_count or len(guild.members),
            inline=False,
        )
        if guild.owner:
            em.add_field(
                name="Owner", value=f"{guild.owner} ({guild.owner.id})", inline=False
            )
        em.add_field(
            name="Leave Type",
            value="Auto-left" if was_auto_left else "Removed / left",
            inline=False,
        )
        em.add_field(name="Reason", value=leave_reason, inline=False)

        await self._send_bot_logs_embed(em)

    # ====== MEMBER PING - AFK EVENT ======

    @Cog.listener(name="on_message")
    async def member_ping_in_afk(self, msg: discord.Message):
        if msg.author.bot or not msg.guild:
            return

        data = (
            await self.bot.db.fetchrow(
                "SELECT reason FROM afk WHERE guild_id=$1 AND user_id=$2",
                msg.guild.id,
                msg.author.id,
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
                    await self.bot.db.fetchrow(
                        "SELECT reason FROM afk WHERE guild_id=$1 AND user_id=$2",
                        msg.guild.id,
                        mention.id,
                    )
                    if self.bot.db
                    else None
                )

                if d2 and mention.id != msg.author.id:
                    em = discord.Embed(
                        title="💤 Member is AFK",
                        description=f"{mention.mention} is currently away.\n**Reason:** {d2['reason']}",
                        color=0x456DD4,
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


async def setup(bot: PizzaHat) -> None:
    await bot.add_cog(Events(bot))
