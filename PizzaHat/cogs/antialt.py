from __future__ import annotations

import discord
from async_lru import alru_cache
from discord.ext import commands
from discord.ext.commands import Context

from core.bot import PizzaHat
from core.cog import Cog
from utils.embed import ctx_embed, green_embed, normal_embed, orange_embed, red_embed

LEVELS = {
    1: (
        "🚫",
        "Restrict",
        "Add the restricted role — user can't send messages or react.",
    ),
    2: ("👞", "Kick", "Kick the suspect. If they rejoin, they're kicked again."),
    3: ("🔨", "Ban", "Permanently ban the suspect."),
}


class LevelSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=f"Level {lvl}  —  {name}",
                description=desc,
                value=str(lvl),
                emoji=emoji,
            )
            for lvl, (emoji, name, desc) in LEVELS.items()
        ]
        super().__init__(placeholder="Select a protection level…", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.level = int(self.values[0])  # type: ignore
        await interaction.response.defer()


class SetupModal(discord.ui.Modal, title="Anti-Alt Setup"):
    min_age = discord.ui.TextInput(
        label="Minimum account age (days)",
        placeholder="e.g. 7  — accounts newer than this are flagged",
        default="7",
        min_length=1,
        max_length=4,
    )

    def __init__(self, view: "SetupWizardView"):
        super().__init__()
        self._view = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            try:
                days = int(self.min_age.value)
                if days <= 0:
                    raise ValueError
            except ValueError:
                await interaction.response.send_message(
                    "Account age must be a positive integer.", ephemeral=True
                )
                return

            self._view.min_age = days
            await interaction.response.defer()
        except Exception:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "An unexpected error occurred while setting the minimum account age.",
                    ephemeral=True,
                )


class RoleChoiceView(discord.ui.View):
    """Step 3: let the admin pick an existing role or create one."""

    def __init__(self, ctx: Context):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.role: discord.Role | None = None
        self.create_new = False
        self.cancelled = False
        self.add_item(RoleSelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Not your menu.", ephemeral=True)
            return False
        return True

    @discord.ui.button(
        label="➕ Create 'Restricted' role", style=discord.ButtonStyle.primary, row=1
    )
    async def auto_create(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.create_new = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=1)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.cancelled = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(
        label="✅ Confirm selected role", style=discord.ButtonStyle.success, row=1
    )
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not self.role:
            return await interaction.response.send_message(
                "Please select a role first.", ephemeral=True
            )
        self.stop()
        await interaction.response.defer()


class RoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="Select an existing restricted role…")

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.role = self.values[0]  # type: ignore
        await interaction.response.defer()


class SetupWizardView(discord.ui.View):
    """Step 1+2: level + min age."""

    def __init__(self, ctx: Context):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.level = 0
        self.min_age = 7
        self.add_item(LevelSelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Not your menu.", ephemeral=True)
            return False
        return True

    @discord.ui.button(
        label="Set min account age →", style=discord.ButtonStyle.primary, row=1
    )
    async def set_age(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.level == 0:
            return await interaction.response.send_message(
                "Pick a protection level first.", ephemeral=True
            )
        await interaction.response.send_modal(SetupModal(self))

    @discord.ui.button(label="✅ Continue", style=discord.ButtonStyle.success, row=1)
    async def proceed(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.level == 0:
            return await interaction.response.send_message(
                "Pick a protection level first.", ephemeral=True
            )
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=1)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.level = -1
        self.stop()
        await interaction.response.defer()


def _build_status_embed(
    guild: discord.Guild,
    data: dict | None,
    bot_yes: str,
    bot_no: str,
) -> discord.Embed:
    enabled = data["enabled"] if data else False
    icon = "🟢" if enabled else "🔴"

    em = normal_embed(
        title="<:raidreport:1268857575919714376>  Anti-Alt Configuration",
        description=(
            f"**Status:** {icon} {'Enabled' if enabled else 'Disabled'}\n"
            f"**Server:** {guild.name}"
        ),
        timestamp=True,
    )

    if data:
        lvl_num = data.get("level", 0) or 0
        lvl_info = LEVELS.get(lvl_num, (None, "Not set", ""))
        role_id = data.get("restricted_role")
        role_str = f"<@&{role_id}>" if role_id else "`Not set`"

        em.add_field(
            name="Protection Level",
            value=f"{lvl_info[0] or '❓'} Level {lvl_num} — {lvl_info[1]}",
            inline=True,
        )
        em.add_field(
            name="Min Account Age",
            value=f"`{data.get('min_age') or 7}` days",
            inline=True,
        )
        em.add_field(name="Restricted Role", value=role_str, inline=True)
    else:
        em.add_field(
            name="Not configured",
            value="Run `p!antialt enable` to set up.",
            inline=False,
        )

    em.add_field(
        name="Levels",
        value="\n".join(
            f"{emoji} **Level {n}** — {name}: {desc}"
            for n, (emoji, name, desc) in LEVELS.items()
        ),
        inline=False,
    )
    em.set_thumbnail(url=guild.icon.url if guild.icon else None)
    return em


class AntiAlts(Cog, emoji=1268851128548724756):
    """Configure the Anti-Alt / Anti-Raid system."""

    def __init__(self, bot: PizzaHat):
        self.bot = bot

    def _clear_cache(self, guild_id: int) -> None:
        for cog_name in ("AntiAltsConfig", "AutoModConfig"):
            cog = self.bot.get_cog(cog_name)
            if cog and hasattr(cog, "clear_config_cache"):
                cog.clear_config_cache(guild_id)  # type: ignore

    @alru_cache()
    async def _get_data(self, guild_id: int) -> dict | None:
        if not self.bot.db:
            return None
        row = await self.bot.db.fetchrow(
            "SELECT enabled, min_age, restricted_role, level FROM antialt WHERE guild_id=$1",
            guild_id,
        )
        return dict(row) if row else None

    async def _refresh_data(self, guild_id: int) -> dict | None:
        """Clear cache then re-fetch."""
        self._get_data.cache_clear()
        return await self._get_data(guild_id)

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def antialt(self, ctx: Context):
        """Anti-Alt configuration hub."""

        if not ctx.guild:
            return

        data = await self._get_data(ctx.guild.id)
        await ctx.send(
            embed=_build_status_embed(ctx.guild, data, self.bot.yes, self.bot.no)
        )

    @antialt.command(name="enable")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def antialt_enable(self, ctx: Context):
        """Interactively enable and configure the Anti-Alt system."""

        if not ctx.guild or not self.bot.db:
            return

        data = await self._get_data(ctx.guild.id)
        enabled = data["enabled"] if data else False

        if enabled:
            return await ctx.send(
                embed=orange_embed(
                    description=f"{self.bot.no} Anti-Alt is already enabled. Use `{ctx.prefix}antialt disable` first."
                )
            )

        wizard = SetupWizardView(ctx)
        msg = await ctx.send(
            embed=await ctx_embed(
                ctx,
                title="Anti-Alt Setup (1/2)",
                description=(
                    "**Select a protection level** and optionally set the minimum account age.\n\n"
                    + "\n".join(
                        f"{emoji} **Level {n} — {name}:** {desc}"
                        for n, (emoji, name, desc) in LEVELS.items()
                    )
                ),
            ),
            view=wizard,
        )
        await wizard.wait()

        if wizard.level == -1:
            return await msg.edit(
                embed=red_embed(description="Setup cancelled."), view=None
            )

        role_view = RoleChoiceView(ctx)
        await msg.edit(
            embed=await ctx_embed(
                ctx,
                title="Anti-Alt Setup (2/2)",
                description=(
                    f"**Level:** {LEVELS[wizard.level][0]} Level {wizard.level} — {LEVELS[wizard.level][1]}\n"
                    f"**Min Age:** {wizard.min_age} days\n\n"
                    "Now select the **restricted role** (used for Level 1 restrict action), "
                    "or let the bot create one automatically."
                ),
            ),
            view=role_view,
        )
        await role_view.wait()

        if role_view.cancelled:
            return await msg.edit(
                embed=red_embed(description="Setup cancelled."), view=None
            )

        restricted_role: discord.Role | None = role_view.role

        if role_view.create_new:
            await msg.edit(
                embed=orange_embed(description="Creating the Restricted role…"),
                view=None,
            )
            try:
                restricted_role = await ctx.guild.create_role(
                    name="Restricted",
                    color=discord.Color.from_str("#818386"),
                    reason="PizzaHat Anti-Alt setup",
                )
                # Deny send/react/speak in every channel
                for channel in ctx.guild.channels:
                    try:
                        await channel.set_permissions(
                            restricted_role,
                            send_messages=False,
                            add_reactions=False,
                            speak=False,
                            reason="PizzaHat Anti-Alt: Restricted role setup",
                        )
                    except discord.HTTPException:
                        pass
            except discord.HTTPException:
                return await msg.edit(
                    embed=red_embed(
                        description=f"{self.bot.no} Failed to create the Restricted role. Please create one manually and run setup again."
                    ),
                    view=None,
                )

        await self.bot.db.execute(
            "INSERT INTO antialt (guild_id, enabled, min_age, restricted_role, level) "
            "VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT (guild_id) DO UPDATE SET enabled=$2, min_age=$3, restricted_role=$4, level=$5",
            ctx.guild.id,
            True,
            wizard.min_age,
            restricted_role.id if restricted_role else None,
            wizard.level,
        )
        self._clear_cache(ctx.guild.id)

        em = green_embed(
            title=f"{self.bot.yes}  Anti-Alt Enabled",
            description="Your configuration:",
            timestamp=True,
        )
        em.add_field(
            name="Level",
            value=f"{LEVELS[wizard.level][0]} Level {wizard.level} — {LEVELS[wizard.level][1]}",
            inline=True,
        )
        em.add_field(name="Min Age", value=f"`{wizard.min_age}` days", inline=True)
        em.add_field(
            name="Role",
            value=restricted_role.mention if restricted_role else "`None`",
            inline=True,
        )
        await msg.edit(embed=em, view=None)

    @antialt.command(name="disable")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def antialt_disable(self, ctx: Context):
        """Disable the Anti-Alt system."""

        if not ctx.guild or not self.bot.db:
            return

        data = await self._get_data(ctx.guild.id)
        if not data or not data["enabled"]:
            return await ctx.send(
                embed=orange_embed(
                    description=f"{self.bot.no} Anti-Alt is already disabled."
                )
            )

        await self.bot.db.execute(
            "UPDATE antialt SET enabled=$1 WHERE guild_id=$2", False, ctx.guild.id
        )
        self._clear_cache(ctx.guild.id)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Anti-Alt has been **disabled**."
            )
        )

    @antialt.command(name="minage")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def antialt_minage(self, ctx: Context, days: int):
        """Change the minimum account age threshold (in days)."""

        if not ctx.guild or not self.bot.db:
            return

        data = await self._get_data(ctx.guild.id)
        if not data or not data["enabled"]:
            return await ctx.send(
                embed=red_embed(description=f"{self.bot.no} Anti-Alt is not enabled.")
            )

        if days <= 0:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Days must be a positive integer."
                )
            )

        await self.bot.db.execute(
            "UPDATE antialt SET min_age=$1 WHERE guild_id=$2", days, ctx.guild.id
        )
        self._clear_cache(ctx.guild.id)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Minimum account age updated to **{days}** day(s)."
            )
        )

    @antialt.command(name="level")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def antialt_level(self, ctx: Context, level: int):
        """Change the protection level (1, 2, or 3)."""

        if not ctx.guild or not self.bot.db:
            return

        data = await self._get_data(ctx.guild.id)
        if not data or not data["enabled"]:
            return await ctx.send(
                embed=red_embed(description=f"{self.bot.no} Anti-Alt is not enabled.")
            )

        if level not in LEVELS:
            return await ctx.send(
                embed=red_embed(description=f"{self.bot.no} Level must be 1, 2, or 3.")
            )

        await self.bot.db.execute(
            "UPDATE antialt SET level=$1 WHERE guild_id=$2", level, ctx.guild.id
        )
        self._clear_cache(ctx.guild.id)
        emoji, name, desc = LEVELS[level]
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Protection level updated to **{emoji} Level {level} — {name}**."
            )
        )

    @antialt.command(name="role")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def antialt_role(self, ctx: Context, role: discord.Role):
        """Change the restricted role."""

        if not ctx.guild or not self.bot.db:
            return

        data = await self._get_data(ctx.guild.id)
        if not data or not data["enabled"]:
            return await ctx.send(
                embed=red_embed(description=f"{self.bot.no} Anti-Alt is not enabled.")
            )

        await self.bot.db.execute(
            "UPDATE antialt SET restricted_role=$1 WHERE guild_id=$2",
            role.id,
            ctx.guild.id,
        )
        self._clear_cache(ctx.guild.id)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Restricted role updated to {role.mention}."
            )
        )

    @antialt.command(name="status")
    @commands.guild_only()
    async def antialt_status(self, ctx: Context):
        """Show the current Anti-Alt configuration."""

        if not ctx.guild:
            return

        data = await self._get_data(ctx.guild.id)
        em = _build_status_embed(ctx.guild, data, self.bot.yes, self.bot.no)
        em.color = (await ctx_embed(ctx, color=em.color)).color
        await ctx.send(embed=em)


async def setup(bot: PizzaHat) -> None:
    await bot.add_cog(AntiAlts(bot))
