from __future__ import annotations

import datetime
import re

import discord
from async_lru import alru_cache

from core.bot import PizzaHat
from core.cog import Cog

INVITE_REGEX = re.compile(
    r"((http(s|):\/\/|)(discord)(\.(gg|io|me)\/|app\.com\/invite\/)([0-z]+))"
)


def _render(text: str, **kwargs: str) -> str:
    """Replace {key} placeholders with values."""
    for k, v in kwargs.items():
        text = text.replace(f"{{{k}}}", v)
    return text


def _template_vars(
    guild: discord.Guild,
    member: discord.Member | discord.User | None = None,
    message: discord.Message | None = None,
) -> dict[str, str]:
    tvars: dict[str, str] = {"guild": guild.name, "guild.id": str(guild.id)}
    if member:
        tvars.update(
            {
                "user": str(member),
                "user.mention": member.mention,
                "user.name": getattr(member, "name", str(member)),
                "user.id": str(member.id),
            }
        )
    if message and hasattr(message.channel, "mention"):
        tvars["channel"] = message.channel.mention  # type: ignore
        tvars["channel.name"] = getattr(message.channel, "name", "")
    return tvars


class WorkflowEvents(Cog):
    """Background event listeners for the workflow/automation system."""

    def __init__(self, bot: PizzaHat):
        self.bot = bot

    # ── cache ─────────────────────────────────────────────────────────────────

    def clear_cache(self, guild_id: int | None = None) -> None:
        self._get_workflows.cache_clear()

    @alru_cache()
    async def _get_workflows(self, guild_id: int) -> list[dict]:
        if not self.bot.db:
            return []
        rows = await self.bot.db.fetch(
            "SELECT id, trigger_type, trigger_config, actions "
            "FROM workflows WHERE guild_id=$1 AND enabled=true",
            guild_id,
        )
        return [dict(r) for r in rows]

    # ── action executor ───────────────────────────────────────────────────────

    async def _run_workflows(
        self,
        guild: discord.Guild,
        trigger_type: str,
        *,
        member: discord.Member | discord.User | None = None,
        message: discord.Message | None = None,
        trigger_config_check=None,
    ) -> None:
        workflows = await self._get_workflows(guild.id)
        for wf in workflows:
            if wf["trigger_type"] != trigger_type:
                continue
            if trigger_config_check and not trigger_config_check(
                dict(wf["trigger_config"]) if wf["trigger_config"] else {}
            ):
                continue
            for action in list(wf["actions"] or []):
                try:
                    await self._execute(
                        guild,
                        action["type"],
                        action.get("config", {}),
                        member=member,
                        message=message,
                    )
                except (discord.HTTPException, Exception):
                    pass

    async def _execute(
        self,
        guild: discord.Guild,
        action_type: str,
        config: dict,
        *,
        member: discord.Member | discord.User | None = None,
        message: discord.Message | None = None,
    ) -> None:
        tvars = _template_vars(guild, member, message)

        if action_type == "send_message":
            channel_id = config.get("channel_id")
            if not channel_id:
                return
            ch = guild.get_channel(channel_id)
            if isinstance(ch, discord.TextChannel):
                await ch.send(_render(config.get("message", ""), **tvars))

        elif action_type == "give_role":
            if not isinstance(member, discord.Member):
                return
            role = guild.get_role(config.get("role_id", 0))
            if role:
                await member.add_roles(role, reason="Workflow automation")

        elif action_type == "remove_role":
            if not isinstance(member, discord.Member):
                return
            role = guild.get_role(config.get("role_id", 0))
            if role:
                await member.remove_roles(role, reason="Workflow automation")

        elif action_type == "dm_user":
            if not member:
                return
            text = _render(config.get("message", ""), **tvars)
            try:
                await member.send(text)
            except discord.HTTPException:
                pass

        elif action_type == "delete_message":
            if message:
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass

        elif action_type == "warn":
            if not member or not self.bot.db:
                return
            reason = _render(config.get("reason", "Workflow automation"), **tvars)
            await self.bot.db.execute(
                "INSERT INTO warnlogs (guild_id, user_id, mod_id, reason) VALUES ($1,$2,$3,$4)",
                guild.id,
                member.id,
                self.bot.user.id,  # type: ignore
                reason,
            )
            automod_cog = self.bot.get_cog("AutoModConfig")
            if automod_cog and hasattr(automod_cog, "check_warn_threshold"):
                await automod_cog.check_warn_threshold(member.id, guild.id)  # type: ignore

        elif action_type == "timeout":
            if not isinstance(member, discord.Member):
                return
            until = discord.utils.utcnow() + datetime.timedelta(
                seconds=config.get("duration", 600)
            )
            await member.timeout(until, reason="Workflow automation")

        elif action_type == "kick":
            if not isinstance(member, discord.Member):
                return
            reason = _render(config.get("reason", "Workflow automation"), **tvars)
            await member.kick(reason=reason)

        elif action_type == "ban":
            if not isinstance(member, discord.Member):
                return
            reason = _render(config.get("reason", "Workflow automation"), **tvars)
            await member.ban(reason=reason, delete_message_days=0)

        elif action_type == "log":
            channel_id = config.get("channel_id")
            if not channel_id:
                return
            ch = guild.get_channel(channel_id)
            if not isinstance(ch, discord.TextChannel):
                return
            text = _render(config.get("message", "Workflow action triggered."), **tvars)
            em = discord.Embed(
                description=text,
                color=0x456DD4,
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
            if member:
                em.set_author(name=str(member), icon_url=member.display_avatar.url)
            await self.bot.send_log(ch, embed=em)

    # ── event listeners ───────────────────────────────────────────────────────

    @Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        await self._run_workflows(member.guild, "member_join", member=member)

    @Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if member.bot:
            return
        await self._run_workflows(member.guild, "member_leave", member=member)

    @Cog.listener()
    async def on_message(self, msg: discord.Message) -> None:
        if msg.author.bot or not msg.guild or not msg.content:
            return

        # message_contains trigger
        def _contains_check(tcfg: dict) -> bool:
            text = tcfg.get("text", "")
            if not text:
                return False
            content = msg.content.lower() if tcfg.get("ignore_case", True) else msg.content
            needle = text.lower() if tcfg.get("ignore_case", True) else text
            return needle in content

        await self._run_workflows(
            msg.guild,
            "message_contains",
            member=msg.author,
            message=msg,
            trigger_config_check=_contains_check,
        )

        # discord_invite trigger
        if INVITE_REGEX.search(msg.content):
            await self._run_workflows(
                msg.guild,
                "discord_invite",
                member=msg.author,
                message=msg,
            )


async def setup(bot: PizzaHat) -> None:
    await bot.add_cog(WorkflowEvents(bot))
