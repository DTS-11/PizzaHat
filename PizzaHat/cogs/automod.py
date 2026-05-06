from __future__ import annotations

import ast
import json

import discord
from discord.ext import commands
from discord.ext.commands import Context

from core.bot import PizzaHat, Tier
from core.cog import Cog
from utils.custom_checks import premium
from utils.embed import ctx_embed, green_embed, orange_embed, red_embed

FREE_MODULES = [
    "banned_words",
    "all_caps",
    "message_spam",
    "invites",
    "mass_mentions",
    "emoji_spam",
    "zalgo_text",
]

BASIC_MODULES = [
    "newline_spam",
    "repeated_chars",
    "scam_links",
    "username_filter",
    "default_avatar",
    "join_rate",
]

ALL_MODULES = FREE_MODULES + BASIC_MODULES

PRO_ACTIONS = {"tempban", "role_add", "role_remove"}

MODULE_DESCRIPTIONS = {
    "banned_words": "Delete messages containing blacklisted words",
    "all_caps": "Delete messages exceeding the caps % threshold",
    "message_spam": "Purge rapid repeated messages from one user",
    "invites": "Delete external Discord invite links",
    "mass_mentions": "Delete messages with excessive @mentions",
    "emoji_spam": "Delete messages with too many emojis",
    "zalgo_text": "Delete zalgo / corrupted unicode text",
    "newline_spam": "Delete messages with excessive line breaks  [Basic]",
    "repeated_chars": "Delete messages with repeated character runs  [Basic]",
    "scam_links": "Delete known phishing/scam domains  [Basic]",
    "username_filter": "Kick members with banned words or staff impersonation  [Basic]",
    "default_avatar": "Act on members who join with no avatar  [Basic]",
    "join_rate": "Detect mass joins and trigger auto-lockdown  [Basic]",
}


class ModuleToggleSelect(discord.ui.Select):
    def __init__(self, cfg: dict, mode: str, available: list[str]):
        options = [
            discord.SelectOption(
                label=m.replace("_", " ").title(),
                description=MODULE_DESCRIPTIONS.get(m, "")[:100],
                value=m,
                default=_mod_active(cfg, m),
            )
            for m in available
        ]
        super().__init__(
            placeholder=f"Select modules to {mode}…",
            min_values=1,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.selected_modules = self.values  # type: ignore
        await interaction.response.defer()


class ModuleToggleView(discord.ui.View):
    def __init__(self, ctx: Context, cfg: dict, mode: str, available: list[str]):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.mode = mode
        self.selected_modules: list[str] = [
            module for module in available if _mod_active(cfg, module)
        ]
        self.cancelled = False
        self.selector = ModuleToggleSelect(cfg, mode, available)
        self.add_item(self.selector)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Not your menu.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success, row=1)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.selected_modules = list(self.selector.values or self.selected_modules)
        if not self.selected_modules:
            return await interaction.response.send_message(
                "Select at least one module first.", ephemeral=True
            )
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=1)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.cancelled = True
        self.selected_modules = []
        self.stop()
        await interaction.response.defer()


class ThresholdActionSelect(discord.ui.Select):
    def __init__(self, is_pro: bool):
        options = [
            discord.SelectOption(
                label="Timeout",
                value="timeout",
                description="Temporarily mute the user",
            ),
            discord.SelectOption(
                label="Kick", value="kick", description="Kick the user"
            ),
            discord.SelectOption(
                label="Ban", value="ban", description="Permanently ban the user"
            ),
        ]
        if is_pro:
            options += [
                discord.SelectOption(
                    label="Temp Ban",
                    value="tempban",
                    description="Ban for N days then unban  [Pro]",
                ),
                discord.SelectOption(
                    label="Add Role",
                    value="role_add",
                    description="Assign a role to the user  [Pro]",
                ),
                discord.SelectOption(
                    label="Remove Role",
                    value="role_remove",
                    description="Remove a role from the user  [Pro]",
                ),
            ]
        super().__init__(placeholder="Select an action…", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.action = self.values[0]  # type: ignore
        await interaction.response.defer()


class ThresholdModal(discord.ui.Modal, title="Add Warn Threshold"):
    warn_count = discord.ui.TextInput(
        label="Warn count that triggers this action",
        placeholder="e.g. 3",
        min_length=1,
        max_length=3,
    )
    duration = discord.ui.TextInput(
        label="Duration in seconds (timeout / tempban only)",
        placeholder="e.g. 3600  —  leave blank for kick / ban",
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

    async def on_submit(self, i: discord.Interaction) -> None:
        try:
            warns = int(self.warn_count.value)
            if warns <= 0:
                raise ValueError
        except ValueError:
            await i.response.send_message(
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

        # Overwrite existing entry with same warn count
        self._view.thresholds = [
            t for t in self._view.thresholds if t["warns"] != warns
        ]
        self._view.thresholds.append(entry)
        self._view.action = None
        await i.response.send_message(
            f"Added: **{warns} warns → {entry['action'].replace('_', ' ').title()}**",
            ephemeral=True,
        )


class ThresholdBuilderView(discord.ui.View):
    def __init__(self, ctx: Context, existing: list[dict], is_pro: bool):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.thresholds: list[dict] = list(existing)
        self.action: str | None = None
        self.add_item(ThresholdActionSelect(is_pro))

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


def _mod_active(cfg: dict, module: str) -> bool:
    val = cfg.get(module, {})
    if isinstance(val, bool):
        return val
    if isinstance(val, dict):
        return bool(val.get("enabled", False))
    return False


def _default_module_config(modules: list[str]) -> dict:
    return {module: {"enabled": True} for module in modules}


def _threshold_summary(thresholds: list[dict]) -> str:
    if not thresholds:
        return "None configured."

    lines = []

    for t in sorted(thresholds, key=lambda x: x["warns"]):
        action = t["action"].replace("_", " ").title()
        extras = []

        if "duration" in t:
            extras.append(f"{t['duration']}s")

        if "unban_days" in t:
            extras.append(f"unban {t['unban_days']}d")
        extra = f" ({', '.join(extras)})" if extras else ""
        lines.append(f"**{t['warns']} warns** → {action}{extra}")

    return "\n".join(lines)


async def _guild_tier(bot: PizzaHat, guild_id: int) -> Tier:
    if not bot.db:
        return Tier.FREE

    row = await bot.db.fetchrow(
        "SELECT tier, status FROM premium WHERE guild_id=$1", guild_id
    )

    if not row or row["status"] != "active":
        return Tier.FREE

    try:
        return Tier(row["tier"])
    except ValueError:
        return Tier.FREE


def _build_status_embed(
    em: discord.Embed,
    guild: discord.Guild,
    enabled: bool,
    module_config: dict,
    tier: Tier,
    bot_yes: str,
    bot_no: str,
) -> discord.Embed:
    tier_label = {Tier.FREE: "Free", Tier.BASIC: "Basic ⭐", Tier.PRO: "Pro 💎"}.get(
        tier, "Free"
    )

    em.title = "<:wrench:1268855253768339476>  AutoMod Configuration"
    em.description = (
        f"**Status:** {f'{bot_yes} Enabled' if enabled else f'{bot_no} Disabled'}\n"
        f"**Plan:** {tier_label}\n"
        f"**Server:** {guild.name}"
    )

    free_lines = [
        f"{bot_yes if _mod_active(module_config, m) else bot_no} `{m.replace('_', ' ').title()}`"
        for m in FREE_MODULES
    ]
    basic_lines = [
        f"{'🔒' if tier < Tier.BASIC else (bot_yes if _mod_active(module_config, m) else bot_no)} `{m.replace('_', ' ').title()}`"
        for m in BASIC_MODULES
    ]

    em.add_field(name="Free Modules", value="\n".join(free_lines), inline=True)
    em.add_field(name="Basic Modules", value="\n".join(basic_lines), inline=True)

    thresholds: list[dict] = sorted(
        module_config.get("thresholds", []), key=lambda t: t["warns"]
    )
    shown = thresholds[:1] if tier == Tier.FREE else thresholds
    t_text = _threshold_summary(shown)

    if tier == Tier.FREE and len(thresholds) > 1:
        t_text += "\n🔒 Additional thresholds require **Basic**"

    em.add_field(name="Warn Thresholds", value=t_text, inline=False)

    overrides: dict = module_config.get("overrides", {})
    if tier >= Tier.BASIC and overrides:
        lines = [
            f"<#{cid}>: {len(mods)} override(s)"
            for cid, mods in list(overrides.items())[:5]
        ]
        em.add_field(name="Channel Overrides", value="\n".join(lines), inline=False)

    elif tier < Tier.BASIC:
        em.add_field(
            name="Channel Overrides", value="🔒 Requires **Basic**", inline=False
        )

    decay = module_config.get("warn_decay_days")

    if tier >= Tier.PRO:
        em.add_field(
            name="Warn Decay",
            value=f"Warns older than `{decay}` days don't count"
            if decay
            else "Disabled",
            inline=False,
        )
    else:
        em.add_field(name="Warn Decay", value="🔒 Requires **Pro**", inline=False)

    em.set_thumbnail(url=guild.icon.url if guild.icon else None)
    return em


class AutoModeration(Cog, emoji=1268880500248936491):
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
            "SELECT enabled, config, modules FROM automod WHERE guild_id=$1", guild_id
        )
        if not row:
            return {}

        data = dict(row)
        config = data.get("config")
        if isinstance(config, str):
            try:
                data["config"] = json.loads(config)
            except json.JSONDecodeError:
                try:
                    data["config"] = ast.literal_eval(config)
                except (ValueError, SyntaxError):
                    data["config"] = {}
        elif config is None:
            data["config"] = {}

        if not data["config"] and data.get("modules"):
            data["config"] = _default_module_config(list(data["modules"]))

        return data

    async def _upsert_config(self, guild_id: int, cfg: dict) -> None:
        if not self.bot.db:
            return
        await self.bot.db.execute(
            "INSERT INTO automod (guild_id, config) VALUES ($1,$2) "
            "ON CONFLICT (guild_id) DO UPDATE SET config=$2",
            guild_id,
            cfg,
        )
        self._clear_cache(guild_id)

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod(self, ctx: Context):
        """AutoMod configuration hub."""

        if not ctx.guild:
            return

        row = await self._get_row(ctx.guild.id)
        enabled = row.get("enabled", False)
        module_config = row.get("config") or {}
        tier = await _guild_tier(self.bot, ctx.guild.id)

        em = await ctx_embed(ctx, timestamp=True)
        em = _build_status_embed(
            em, ctx.guild, enabled, module_config, tier, self.bot.yes, self.bot.no
        )
        em.add_field(
            name="Commands",
            value=(
                f"`{ctx.prefix}automod enable/disable` — toggle system\n"
                f"`{ctx.prefix}automod enable <module>` — enable a module\n"
                f"`{ctx.prefix}automod disable <module>` — disable a module\n"
                f"`{ctx.prefix}automod modules` — bulk module manager  **[Basic]**\n"
                f"`{ctx.prefix}automod thresholds` — warn thresholds  **[Basic: unlimited / Free: 1]**\n"
                f"`{ctx.prefix}automod override #ch module on/off` — per-channel override  **[Basic]**\n"
                f"`{ctx.prefix}automod settings module key value` — tweak settings  **[Basic]**\n"
                f"`{ctx.prefix}automod decay <days>` — warn decay  **[Pro]**"
            ),
            inline=False,
        )
        await ctx.send(embed=em)

    @automod.command(name="enable")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_enable(self, ctx: Context, module: str | None = None):
        """Enable the AutoMod system, or a specific module."""

        if not ctx.guild or not self.bot.db:
            return

        if module is None:
            row = await self._get_row(ctx.guild.id)
            config_data: dict = dict(row.get("config") or {})

            for mod, default_entry in _default_module_config(FREE_MODULES).items():
                entry = config_data.get(mod, {})
                if isinstance(entry, dict):
                    config_data[mod] = {**default_entry, **entry}
                else:
                    config_data[mod] = default_entry

            await self.bot.db.execute(
                "INSERT INTO automod (guild_id, enabled, config) VALUES ($1, true, $2) "
                "ON CONFLICT (guild_id) DO UPDATE SET enabled=true, config=$2",
                ctx.guild.id,
                config_data,
            )
            self._clear_cache(ctx.guild.id)
            return await ctx.send(
                embed=green_embed(description=f"{self.bot.yes} AutoMod **enabled**.")
            )

        module = module.lower()
        if module not in ALL_MODULES:
            return await ctx.send(
                embed=red_embed(
                    description=(
                        f"{self.bot.no} `{module}` is not a valid module.\n"
                        f"**Free:** {', '.join(f'`{m}`' for m in FREE_MODULES)}\n"
                        f"**Basic:** {', '.join(f'`{m}`' for m in BASIC_MODULES)}"
                    )
                )
            )

        tier = await _guild_tier(self.bot, ctx.guild.id)
        if module in BASIC_MODULES and tier < Tier.BASIC:
            return await ctx.send(
                embed=orange_embed(
                    description=f"⭐ `{module.replace('_', ' ').title()}` requires **Basic** or higher."
                )
            )

        row = await self._get_row(ctx.guild.id)
        cfg: dict = dict(row.get("config") or {})
        entry = cfg.get(module, {})
        cfg[module] = {**(entry if isinstance(entry, dict) else {}), "enabled": True}

        await self._upsert_config(ctx.guild.id, cfg)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} `{module.replace('_', ' ').title()}` **enabled**."
            )
        )

    @automod.command(name="disable")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_disable(self, ctx: Context, module: str | None = None):
        """Disable the AutoMod system, or a specific module."""

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
                embed=green_embed(description=f"{self.bot.yes} AutoMod **disabled**.")
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
        cfg[module] = {**(entry if isinstance(entry, dict) else {}), "enabled": False}
        await self._upsert_config(ctx.guild.id, cfg)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} `{module.replace('_', ' ').title()}` **disabled**."
            )
        )

    @automod.command(name="modules")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @premium(Tier.BASIC)
    async def automod_modules(self, ctx: Context, mode: str = "enable"):
        """Bulk interactive module manager.  [Basic]"""

        if not ctx.guild:
            return

        mode = mode.lower()
        if mode not in ("enable", "disable"):
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Mode must be `enable` or `disable`."
                )
            )

        tier = await _guild_tier(self.bot, ctx.guild.id)
        available = FREE_MODULES + (BASIC_MODULES if tier >= Tier.BASIC else [])
        row = await self._get_row(ctx.guild.id)
        cfg: dict = dict(row.get("config") or {})

        view = ModuleToggleView(ctx, cfg, mode, available)
        msg = await ctx.send(
            embed=await ctx_embed(
                ctx,
                title="Module Manager",
                description=f"Select modules to **{mode}**, then click **Confirm**.",
            ),
            view=view,
        )
        await view.wait()

        if not view.selected_modules:
            return await msg.edit(
                embed=red_embed(description="Cancelled — no changes made."), view=None
            )

        for mod in view.selected_modules:
            entry = cfg.get(mod, {})
            cfg[mod] = {
                **(entry if isinstance(entry, dict) else {}),
                "enabled": mode == "enable",
            }

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
        Manage warn → action thresholds.
        Free: 1 threshold · Basic: unlimited · Pro: adds Temp Ban, Add/Remove Role
        """

        if not ctx.guild:
            return

        tier = await _guild_tier(self.bot, ctx.guild.id)
        row = await self._get_row(ctx.guild.id)
        cfg: dict = dict(row.get("config") or {})
        existing = cfg.get("thresholds", [])
        is_pro = tier >= Tier.PRO
        is_basic = tier >= Tier.BASIC

        upsell = ""
        if not is_basic:
            upsell = "\n\n⭐ **Basic** unlocks unlimited stacked thresholds.\n💎 **Pro** unlocks Temp Ban, Add/Remove Role actions."
        elif not is_pro:
            upsell = "\n\n💎 **Pro** unlocks Temp Ban, Add Role, Remove Role actions."

        view = ThresholdBuilderView(ctx, existing, is_pro)
        msg = await ctx.send(
            embed=await ctx_embed(
                ctx,
                title="Warn Threshold Builder",
                description=(
                    "**Current thresholds:**\n" + _threshold_summary(existing) + "\n\n"
                    "1. Pick an **action** from the dropdown\n"
                    "2. Click **➕ Add threshold** and fill in the warn count\n"
                    "3. Repeat to stack multiple thresholds\n"
                    "4. Click **✅ Save** when done" + upsell
                ),
            ),
            view=view,
        )
        await view.wait()

        new_thresholds = view.thresholds

        if not is_basic and len(new_thresholds) > 1:
            new_thresholds = sorted(new_thresholds, key=lambda t: t["warns"])[:1]
            await ctx.send(
                embed=orange_embed(
                    description=(
                        "⭐ Free plan supports **1 warn threshold**. "
                        "Only the lowest was saved. Upgrade to **Basic** for unlimited."
                    )
                )
            )

        if not is_pro:
            for t in new_thresholds:
                if t.get("action") in PRO_ACTIONS:
                    t["action"] = "kick"
                    await ctx.send(
                        embed=orange_embed(
                            description=(
                                f"💎 `{t['action']}` requires **Pro** — replaced with `kick`. "
                                "Upgrade to use Temp Ban, Add Role, or Remove Role."
                            )
                        )
                    )

        cfg["thresholds"] = new_thresholds
        await self._upsert_config(ctx.guild.id, cfg)
        await msg.edit(
            embed=green_embed(
                title="Thresholds Saved",
                description=_threshold_summary(new_thresholds)
                or "All thresholds cleared.",
            ),
            view=None,
        )

    @automod.command(name="override")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @premium(Tier.BASIC)
    async def automod_override(
        self,
        ctx: Context,
        channel: discord.TextChannel,
        module: str,
        state: str,
    ):
        """
        Override a module for one channel.  [Basic]
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
        if state not in ("on", "off", "enable", "disable"):
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} State must be `on` or `off`."
                )
            )

        enabled = state in ("on", "enable")
        row = await self._get_row(ctx.guild.id)
        cfg: dict = dict(row.get("config") or {})
        overrides = cfg.get("overrides", {})
        ch_cfg = overrides.get(str(channel.id), {})
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
    @premium(Tier.BASIC)
    async def automod_settings(
        self, ctx: Context, module: str, setting: str, *, value: str
    ):
        """
        Tweak a setting for a specific module.  [Basic]

        Examples:
        `p!automod settings all_caps threshold 80`
        `p!automod settings message_spam window_seconds 8`
        `p!automod settings mass_mentions threshold 5`
        `p!automod settings emoji_spam threshold 15`
        `p!automod settings invites whitelist discord.gg/yourcode`
        `p!automod settings join_rate threshold 8`
        `p!automod settings join_rate window_seconds 20`
        `p!automod settings join_rate lockdown_minutes 10`  [Pro]
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

        if setting == "lockdown_minutes":
            tier = await _guild_tier(self.bot, ctx.guild.id)
            if tier < Tier.PRO:
                return await ctx.send(
                    embed=orange_embed(
                        description="💎 `lockdown_minutes` is a **Pro** setting. Upgrade to customise the raid lockdown duration."
                    )
                )

        row = await self._get_row(ctx.guild.id)
        cfg: dict = dict(row.get("config") or {})
        entry: dict = cfg.get(module, {})

        if not isinstance(entry, dict):
            entry = {"enabled": bool(entry)}

        if setting == "whitelist":
            wl: list = entry.get("whitelist", [])
            if value not in wl:
                wl.append(value)
            entry["whitelist"] = wl
        else:
            try:
                entry[setting] = int(value)
            except ValueError:
                entry[setting] = value

        cfg[module] = entry
        await self._upsert_config(ctx.guild.id, cfg)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} `{module.replace('_', ' ').title()}` → `{setting}` = `{value}`."
            )
        )

    @automod.command(name="decay")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @premium(Tier.PRO)
    async def automod_decay(self, ctx: Context, days: int):
        """
        Warns older than N days stop counting toward thresholds.  [Pro]
        Set to 0 to disable decay.
        """

        if not ctx.guild:
            return
        if days < 0:
            return await ctx.send(
                embed=red_embed(description=f"{self.bot.no} Days must be 0 or greater.")
            )

        row = await self._get_row(ctx.guild.id)
        cfg: dict = dict(row.get("config") or {})

        if days == 0:
            cfg.pop("warn_decay_days", None)
            await self._upsert_config(ctx.guild.id, cfg)
            return await ctx.send(
                embed=green_embed(
                    description=f"{self.bot.yes} Warn decay **disabled**."
                )
            )

        cfg["warn_decay_days"] = days
        await self._upsert_config(ctx.guild.id, cfg)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Warns older than **{days}** days will no longer count toward thresholds."
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
        module_config = row.get("config") or {}
        tier = await _guild_tier(self.bot, ctx.guild.id)
        em = await ctx_embed(ctx, timestamp=True)
        await ctx.send(
            embed=_build_status_embed(
                em, ctx.guild, enabled, module_config, tier, self.bot.yes, self.bot.no
            )
        )


async def setup(bot: PizzaHat) -> None:
    await bot.add_cog(AutoModeration(bot))
