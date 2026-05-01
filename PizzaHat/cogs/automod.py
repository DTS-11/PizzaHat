from __future__ import annotations

import discord
from discord.ext import commands
from discord.ext.commands import Context

from core.bot import PizzaHat
from core.cog import Cog
from utils.embed import ctx_embed, green_embed, normal_embed, red_embed

ALL_MODULES = [
    "banned_words",
    "scam_links",
    "all_caps",
    "message_spam",
    "invites",
    "mass_mentions",
    "emoji_spam",
    "zalgo_text",
    "newline_spam",
    "repeated_chars",
    "username_filter",
    "default_avatar",
    "join_rate",
]

MODULE_DESCRIPTIONS = {
    "banned_words": "Delete messages containing blacklisted words",
    "scam_links": "Delete known phishing/scam domains",
    "all_caps": "Delete messages exceeding the caps threshold",
    "message_spam": "Purge rapid repeated messages from one user",
    "invites": "Delete external Discord invite links",
    "mass_mentions": "Delete messages with excessive @mentions",
    "emoji_spam": "Delete messages with too many emojis",
    "zalgo_text": "Delete zalgo / corrupted unicode text",
    "newline_spam": "Delete messages with excessive line breaks",
    "repeated_chars": "Delete messages with repeated character runs",
    "username_filter": "Kick members with banned words or staff-impersonation names",
    "default_avatar": "Act on members who join with no avatar",
    "join_rate": "Detect mass joins and auto-lockdown (raid protection)",
}

VALID_ACTIONS = ["timeout", "kick", "tempban", "ban", "role_add", "role_remove", "none"]


class ModuleToggleSelect(discord.ui.Select):
    """Multi-select dropdown to toggle modules on/off."""

    def __init__(self, cfg: dict, mode: str):
        self.mode = mode  # "enable" | "disable"
        options = [
            discord.SelectOption(
                label=mod.replace("_", " ").title(),
                description=MODULE_DESCRIPTIONS[mod][:100],
                value=mod,
                default=self._is_active(cfg, mod),
            )
            for mod in ALL_MODULES
        ]
        super().__init__(
            placeholder=f"Select modules to {mode}…",
            min_values=1,
            max_values=len(ALL_MODULES),
            options=options,
        )

    @staticmethod
    def _is_active(cfg: dict, mod: str) -> bool:
        val = cfg.get(mod, {})
        if isinstance(val, bool):
            return val
        if isinstance(val, dict):
            return bool(val.get("enabled", False))
        return False

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.selected_modules = self.values  # type: ignore
        await interaction.response.defer()


class ModuleToggleView(discord.ui.View):
    def __init__(self, ctx: Context, cfg: dict, mode: str):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.mode = mode
        self.selected_modules: list[str] = []
        self.add_item(ModuleToggleSelect(cfg, mode))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Not your menu.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success, row=1)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=1)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.selected_modules = []
        self.stop()
        await interaction.response.defer()


class ThresholdActionSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Timeout",
                value="timeout",
                description="Temporarily mute the user",
            ),
            discord.SelectOption(
                label="Kick", value="kick", description="Kick the user from the server"
            ),
            discord.SelectOption(
                label="Temp Ban",
                value="tempban",
                description="Ban for a set number of days",
            ),
            discord.SelectOption(
                label="Ban", value="ban", description="Permanently ban the user"
            ),
            discord.SelectOption(
                label="Add Role",
                value="role_add",
                description="Assign a role to the user",
            ),
            discord.SelectOption(
                label="Remove Role",
                value="role_remove",
                description="Remove a role from the user",
            ),
        ]
        super().__init__(placeholder="Select action…", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.action = self.values[0]  # type: ignore
        await interaction.response.defer()


class ThresholdModal(discord.ui.Modal, title="Add Warn Threshold"):
    warn_count = discord.ui.TextInput(
        label="Warn count",
        placeholder="e.g. 3",
        min_length=1,
        max_length=3,
    )
    duration = discord.ui.TextInput(
        label="Duration (seconds, for timeout/tempban)",
        placeholder="e.g. 3600  — leave blank for kick/ban",
        required=False,
        max_length=10,
    )
    unban_days = discord.ui.TextInput(
        label="Unban after N days (tempban only)",
        placeholder="e.g. 7",
        required=False,
        max_length=3,
    )

    def __init__(self, view: "ThresholdBuilderView"):
        super().__init__()
        self._view = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            try:
                warns = int(self.warn_count.value)
                if warns <= 0:
                    raise ValueError
            except ValueError:
                await interaction.response.send_message(
                    "Warn count must be a positive integer.", ephemeral=True
                )
                return

            entry: dict = {"warns": warns, "action": self._view.action or "kick"}

            if self.duration.value.strip():
                try:
                    entry["duration"] = int(self.duration.value)
                except ValueError:
                    pass

            if self.unban_days.value.strip():
                try:
                    entry["unban_days"] = int(self.unban_days.value)
                except ValueError:
                    pass

            self._view.thresholds.append(entry)
            self._view.action = None
            await interaction.response.send_message(
                f"Threshold added: **{warns} warns → {entry['action'].replace('_', ' ').title()}**",
                ephemeral=True,
            )
        except Exception:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "An unexpected error occurred while adding the threshold.",
                    ephemeral=True,
                )


class ThresholdBuilderView(discord.ui.View):
    def __init__(self, ctx: Context, existing: list[dict]):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.thresholds: list[dict] = list(existing)
        self.action: str | None = None
        self.add_item(ThresholdActionSelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Not your menu.", ephemeral=True)
            return False
        return True

    @discord.ui.button(
        label="➕ Add threshold", style=discord.ButtonStyle.primary, row=1
    )
    async def add(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not self.action:
            return await interaction.response.send_message(
                "Select an action first.", ephemeral=True
            )
        await interaction.response.send_modal(ThresholdModal(self))

    @discord.ui.button(label="🗑 Clear all", style=discord.ButtonStyle.danger, row=1)
    async def clear(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.thresholds.clear()
        await interaction.response.send_message(
            "All thresholds cleared.", ephemeral=True
        )

    @discord.ui.button(label="✅ Save", style=discord.ButtonStyle.success, row=1)
    async def save(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.stop()
        await interaction.response.defer()


def _status_icon(enabled: bool) -> str:
    return "🟢" if enabled else "🔴"


def _build_status_embed(
    guild: discord.Guild, enabled: bool, cfg: dict, ctx: Optional[Context] = None
) -> discord.Embed:
    em = normal_embed(
        title="<:wrench:1268855253768339476>  AutoMod Configuration",
        description=(
            f"**Status:** {_status_icon(enabled)} {'Enabled' if enabled else 'Disabled'}\n"
            f"**Server:** {guild.name}"
        ),
        timestamp=True,
    )

    lines = []
    for mod in ALL_MODULES:
        val = cfg.get(mod, {})
        active = (
            val if isinstance(val, bool) else bool((val or {}).get("enabled", False))
        )
        lines.append(f"{_status_icon(active)} `{mod.replace('_', ' ').title()}`")

    half = len(lines) // 2
    em.add_field(name="Modules", value="\n".join(lines[:half]), inline=True)
    em.add_field(name="\u200b", value="\n".join(lines[half:]), inline=True)

    thresholds: list[dict] = sorted(cfg.get("thresholds", []), key=lambda t: t["warns"])
    if thresholds:
        t_lines = []
        for t in thresholds:
            action = t["action"].replace("_", " ").title()
            extras = []
            if "duration" in t:
                extras.append(f"{t['duration']}s")
            if "unban_days" in t:
                extras.append(f"unban in {t['unban_days']}d")
            extra_str = f" ({', '.join(extras)})" if extras else ""
            t_lines.append(f"**{t['warns']} warns** → {action}{extra_str}")
        em.add_field(name="Warn Thresholds", value="\n".join(t_lines), inline=False)

    else:
        em.add_field(name="Warn Thresholds", value="None configured", inline=False)

    overrides: dict = cfg.get("overrides", {})
    if overrides:
        o_lines = [
            f"<#{ch_id}>: {len(mods)} override(s)" for ch_id, mods in overrides.items()
        ]
        em.add_field(
            name="Channel Overrides", value="\n".join(o_lines[:5]), inline=False
        )

    em.set_thumbnail(url=guild.icon.url if guild.icon else None)
    return em


class AutoMod(Cog, emoji=1268855303768903733):
    """Configure the AutoMod system for your server."""

    def __init__(self, bot: PizzaHat):
        self.bot = bot

    def _clear_cache(self, guild_id: int) -> None:
        cog = self.bot.get_cog("AutoModConfig")
        if cog and hasattr(cog, "clear_config_cache"):
            cog.clear_config_cache(guild_id)  # type: ignore

    async def _get_row(self, guild_id: int) -> dict:
        if not self.bot.db:
            return {}
        row = await self.bot.db.fetchrow(
            "SELECT enabled, config FROM automod WHERE guild_id=$1", guild_id
        )
        return dict(row) if row else {}

    async def _upsert_config(self, guild_id: int, cfg: dict) -> None:
        if not self.bot.db:
            return
        await self.bot.db.execute(
            "INSERT INTO automod (guild_id, config) VALUES ($1, $2) "
            "ON CONFLICT (guild_id) DO UPDATE SET config=$2",
            guild_id,
            cfg,
        )
        self._clear_cache(guild_id)

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def automod(self, ctx: Context):
        """AutoMod configuration hub. Run sub-commands to configure."""

        if not ctx.guild:
            return

        row = await self._get_row(ctx.guild.id)
        enabled: bool = row.get("enabled", False)
        cfg: dict = row.get("config") or {}

        em = _build_status_embed(ctx.guild, enabled, cfg)
        # Apply theming
        em.color = (await ctx_embed(ctx, color=em.color)).color
        em.add_field(
            name="Sub-commands",
            value=(
                f"`{ctx.prefix}automod enable/disable` — toggle the system\n"
                f"`{ctx.prefix}automod enable <module>` — enable a specific module\n"
                f"`{ctx.prefix}automod disable <module>` — disable a specific module\n"
                f"`{ctx.prefix}automod modules` — interactive module manager\n"
                f"`{ctx.prefix}automod thresholds` — manage warn thresholds\n"
                f"`{ctx.prefix}automod override` — per-channel overrides\n"
                f"`{ctx.prefix}automod settings <module>` — tweak module settings"
            ),
            inline=False,
        )
        await ctx.send(embed=em)

    @automod.command(name="enable")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_enable(self, ctx: Context, module: str | None = None):
        """Enable the AutoMod system or a specific module."""

        if not ctx.guild or not self.bot.db:
            return

        if module is None:
            # Toggle whole system ON
            await self.bot.db.execute(
                "INSERT INTO automod (guild_id, enabled) VALUES ($1, true) "
                "ON CONFLICT (guild_id) DO UPDATE SET enabled=true",
                ctx.guild.id,
            )
            self._clear_cache(ctx.guild.id)
            return await ctx.send(
                embed=green_embed(
                    description=f"{self.bot.yes} AutoMod has been **enabled**."
                )
            )

        module = module.lower()
        if module not in ALL_MODULES:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} `{module}` is not a valid module.\n"
                    f"Valid: {', '.join(f'`{m}`' for m in ALL_MODULES)}"
                )
            )

        row = await self._get_row(ctx.guild.id)
        cfg: dict = dict(row.get("config") or {})
        entry = cfg.get(module, {})
        if isinstance(entry, bool):
            cfg[module] = True
        else:
            cfg[module] = {**(entry or {}), "enabled": True}

        await self._upsert_config(ctx.guild.id, cfg)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} `{module.replace('_', ' ').title()}` module **enabled**."
            )
        )

    @automod.command(name="disable")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_disable(self, ctx: Context, module: str | None = None):
        """Disable the AutoMod system or a specific module."""

        if not ctx.guild or not self.bot.db:
            return

        if module is None:
            await self.bot.db.execute(
                "INSERT INTO automod (guild_id, enabled) VALUES ($1, false) "
                "ON CONFLICT (guild_id) DO UPDATE SET enabled=false",
                ctx.guild.id,
            )
            self._clear_cache(ctx.guild.id)
            return await ctx.send(
                embed=green_embed(
                    description=f"{self.bot.yes} AutoMod has been **disabled**."
                )
            )

        module = module.lower()
        if module not in ALL_MODULES:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} `{module}` is not a valid module."
                )
            )

        row = await self._get_row(ctx.guild.id)
        cfg: dict = dict(row.get("config") or {})
        entry = cfg.get(module, {})
        if isinstance(entry, bool):
            cfg[module] = False
        else:
            cfg[module] = {**(entry or {}), "enabled": False}

        await self._upsert_config(ctx.guild.id, cfg)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} `{module.replace('_', ' ').title()}` module **disabled**."
            )
        )

    @automod.command(name="modules")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_modules(self, ctx: Context, mode: str = "enable"):
        """
        Interactive module manager.
        Usage: `p!automod modules enable` or `p!automod modules disable`
        """

        if not ctx.guild:
            return

        mode = mode.lower()
        if mode not in ("enable", "disable"):
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Mode must be `enable` or `disable`."
                )
            )

        row = await self._get_row(ctx.guild.id)
        cfg: dict = dict(row.get("config") or {})

        view = ModuleToggleView(ctx, cfg, mode)
        msg = await ctx.send(
            embed=await ctx_embed(
                ctx,
                title="Module Manager",
                description=f"Select the modules you want to **{mode}**, then click **Confirm**.",
            ),
            view=view,
        )
        await view.wait()

        if not view.selected_modules:
            return await msg.edit(
                embed=red_embed(description="Cancelled — no changes made."),
                view=None,
            )

        for mod in view.selected_modules:
            entry = cfg.get(mod, {})
            enabled_val = mode == "enable"
            if isinstance(entry, bool):
                cfg[mod] = enabled_val
            else:
                cfg[mod] = {**(entry or {}), "enabled": enabled_val}

        await self._upsert_config(ctx.guild.id, cfg)

        changed = ", ".join(
            f"`{m.replace('_', ' ').title()}`" for m in view.selected_modules
        )
        await msg.edit(
            embed=green_embed(description=f"{self.bot.yes} {mode.title()}d: {changed}"),
            view=None,
        )

    @automod.command(name="thresholds", aliases=["threshold"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_thresholds(self, ctx: Context):
        """
        Interactively manage warn → action thresholds.
        You can stack multiple thresholds (e.g. 3 warns = timeout, 5 = kick, 7 = ban).
        """

        if not ctx.guild:
            return

        row = await self._get_row(ctx.guild.id)
        cfg: dict = dict(row.get("config") or {})
        existing: list[dict] = cfg.get("thresholds", [])

        def _threshold_summary(thresholds: list[dict]) -> str:
            if not thresholds:
                return "No thresholds configured yet."
            lines = []
            for t in sorted(thresholds, key=lambda x: x["warns"]):
                action = t["action"].replace("_", " ").title()
                extras = []
                if "duration" in t:
                    extras.append(f"{t['duration']}s timeout")
                if "unban_days" in t:
                    extras.append(f"unban after {t['unban_days']}d")
                extra_str = f" ({', '.join(extras)})" if extras else ""
                lines.append(f"**{t['warns']} warns** → {action}{extra_str}")
            return "\n".join(lines)

        view = ThresholdBuilderView(ctx, existing)
        msg = await ctx.send(
            embed=await ctx_embed(
                ctx,
                title="Warn Threshold Builder",
                description=(
                    "**Current thresholds:**\n" + _threshold_summary(existing) + "\n\n"
                    "1. Pick an **action** from the dropdown.\n"
                    "2. Click **➕ Add threshold** to set the warn count.\n"
                    "3. Repeat for multiple thresholds.\n"
                    "4. Click **✅ Save** when done."
                ),
            ),
            view=view,
        )
        await view.wait()

        cfg["thresholds"] = view.thresholds
        await self._upsert_config(ctx.guild.id, cfg)

        await msg.edit(
            embed=green_embed(
                title="Thresholds Saved",
                description=_threshold_summary(view.thresholds)
                or "All thresholds cleared.",
            ),
            view=None,
        )

    @automod.command(name="override")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_override(
        self,
        ctx: Context,
        channel: discord.TextChannel,
        module: str,
        state: str,
    ):
        """
        Enable or disable a specific module for one channel.
        Example: `p!automod override #resources invites off`
        """

        if not ctx.guild:
            return

        module = module.lower()
        state = state.lower()

        if module not in ALL_MODULES:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} `{module}` is not a valid module."
                )
            )
        if state not in ("on", "off", "enable", "disable", "true", "false"):
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} State must be `on` or `off`."
                )
            )

        enabled = state in ("on", "enable", "true")

        row = await self._get_row(ctx.guild.id)
        cfg: dict = dict(row.get("config") or {})
        overrides: dict = cfg.get("overrides", {})
        ch_cfg: dict = overrides.get(str(channel.id), {})
        ch_cfg[module] = {"enabled": enabled}
        overrides[str(channel.id)] = ch_cfg
        cfg["overrides"] = overrides

        await self._upsert_config(ctx.guild.id, cfg)
        await ctx.send(
            embed=green_embed(
                description=(
                    f"{self.bot.yes} `{module.replace('_', ' ').title()}` "
                    f"{'enabled' if enabled else 'disabled'} in {channel.mention}."
                )
            )
        )

    @automod.command(name="settings")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_settings(
        self, ctx: Context, module: str, setting: str, value: str
    ):
        """
        Tweak a numeric/string setting for a module.

        **Examples**
        `p!automod settings all_caps threshold 80`
        `p!automod settings message_spam threshold 6`
        `p!automod settings message_spam window_seconds 8`
        `p!automod settings mass_mentions threshold 5`
        `p!automod settings emoji_spam threshold 15`
        `p!automod settings invites whitelist discord.gg/yourserver`
        `p!automod settings join_rate threshold 8`
        `p!automod settings join_rate window_seconds 20`
        `p!automod settings join_rate lockdown_minutes 10`
        `p!automod settings default_avatar action kick`
        """

        if not ctx.guild:
            return

        module = module.lower()
        if module not in ALL_MODULES:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} `{module}` is not a valid module."
                )
            )

        row = await self._get_row(ctx.guild.id)
        cfg: dict = dict(row.get("config") or {})
        mod_entry: dict = cfg.get(module, {})
        if not isinstance(mod_entry, dict):
            mod_entry = {"enabled": bool(mod_entry)}

        # Special handling for whitelist (append)
        if setting == "whitelist":
            wl: list = mod_entry.get("whitelist", [])
            if value not in wl:
                wl.append(value)
            mod_entry["whitelist"] = wl
        else:
            # Try to coerce to int, else store as string
            try:
                mod_entry[setting] = int(value)
            except ValueError:
                mod_entry[setting] = value

        cfg[module] = mod_entry
        await self._upsert_config(ctx.guild.id, cfg)
        await ctx.send(
            embed=green_embed(
                description=(
                    f"{self.bot.yes} `{module.replace('_', ' ').title()}` → "
                    f"`{setting}` set to `{value}`."
                )
            )
        )

    @automod.command(name="status")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_status(self, ctx: Context):
        """Show the full AutoMod configuration for this server."""

        if not ctx.guild:
            return

        row = await self._get_row(ctx.guild.id)
        enabled = row.get("enabled", False)
        cfg = row.get("config") or {}
        em = _build_status_embed(ctx.guild, enabled, cfg)
        em.color = (await ctx_embed(ctx, color=em.color)).color
        await ctx.send(embed=em)


async def setup(bot: PizzaHat) -> None:
    await bot.add_cog(AutoMod(bot))
