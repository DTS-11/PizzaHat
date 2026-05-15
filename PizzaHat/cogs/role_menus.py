from __future__ import annotations

from typing import Optional

import discord
from discord.ext import commands
from discord.ext.commands import Context

from cogs_hidden.role_menus import (
    DISCORD_MAX_ITEMS,
    _fetch_items,
    _fetch_menu,
    publish_menu,
    refresh_menu,
)
from core.bot import PizzaHat, Tier
from core.cog import Cog
from utils.custom_checks import _tier_cache, premium
from utils.embed import ctx_embed, green_embed, orange_embed, red_embed

TIER_LIMITS: dict[Tier, int] = {
    Tier.FREE: 3,
    Tier.BASIC: 15,
    Tier.PRO: 100,
}

VALID_TYPES = {"button", "dropdown"}
VALID_MODES = {"single", "multi"}


async def _guild_tier(bot: PizzaHat, guild_id: int) -> Tier:
    cached = _tier_cache.get(guild_id)
    if cached is not None:
        return cached
    if bot.db is None:
        return Tier.FREE
    row = await bot.db.fetchrow("SELECT tier FROM premium WHERE guild_id=$1", guild_id)
    tier = Tier(row["tier"]) if row else Tier.FREE
    _tier_cache[guild_id] = tier
    return tier


async def _resolve_menu(ctx: Context, menu_id: int) -> Optional[dict]:
    if not ctx.guild or not ctx.bot.db:
        return None
    menu = await _fetch_menu(ctx.bot, menu_id)
    if not menu or menu["guild_id"] != ctx.guild.id:
        await ctx.send(
            embed=red_embed(
                description=f"{ctx.bot.no} Role menu `#{menu_id}` not found."
            )
        )
        return None
    return menu


class RoleMenus(Cog, emoji="🎭"):
    """🎭 Self-assignable role menus — buttons and dropdowns."""

    def __init__(self, bot: PizzaHat):
        self.bot = bot

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HUB / LIST
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @commands.group(
        name="rolemenu", aliases=["rm", "rolemenus"], invoke_without_command=True
    )
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def rolemenu(self, ctx: Context):
        """🎭 Role menu management."""
        if not ctx.guild or not self.bot.db:
            return

        rows = await self.bot.db.fetch(
            "SELECT id, name, type, mode, enabled, message_id, "
            "(SELECT COUNT(*) FROM role_menu_items WHERE menu_id=role_menus.id) AS item_count "
            "FROM role_menus WHERE guild_id=$1 ORDER BY id",
            ctx.guild.id,
        )
        tier = await _guild_tier(self.bot, ctx.guild.id)
        limit = TIER_LIMITS[tier]
        p = ctx.prefix

        if not rows:
            return await ctx.send(
                embed=orange_embed(
                    description=(
                        f"No role menus yet.\n\n"
                        f"**Create one:** `{p}rolemenu create <name> [button|dropdown]`\n"
                        f'Example: `{p}rolemenu create "Game Roles" button`'
                    )
                )
            )

        lines: list[str] = []
        for r in rows:
            status = "✅" if r["enabled"] else "❌"
            posted = "📤" if r["message_id"] else "📝"
            lines.append(
                f"{status} {posted} `#{r['id']}` **{r['name']}** · "
                f"`{r['type']}` / `{r['mode']}` · {r['item_count']} role(s)"
            )

        em = await ctx_embed(
            ctx,
            title="🎭  Role Menus",
            description=(
                f"**{len(rows)}** / **{limit}** · {tier.name} tier\n"
                f"📤 posted · 📝 draft\n\n" + "\n".join(lines)
            ),
        )
        await ctx.send(embed=em)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CREATE / DELETE / TOGGLE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @rolemenu.command(name="create", aliases=["new"])
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def rm_create(
        self, ctx: Context, name: str, type_: str = "button", mode: str = "multi"
    ):
        """Create a new role menu. Type: `button` or `dropdown`. Mode: `single` or `multi`."""
        if not ctx.guild or not self.bot.db:
            return

        type_ = type_.lower()
        mode = mode.lower()
        if type_ not in VALID_TYPES:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Type must be `button` or `dropdown`."
                )
            )
        if mode not in VALID_MODES:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Mode must be `single` or `multi`."
                )
            )

        tier = await _guild_tier(self.bot, ctx.guild.id)
        limit = TIER_LIMITS[tier]
        count = (
            await self.bot.db.fetchval(
                "SELECT COUNT(*) FROM role_menus WHERE guild_id=$1", ctx.guild.id
            )
            or 0
        )
        if count >= limit:
            return await ctx.send(
                embed=red_embed(
                    description=(
                        f"{self.bot.no} **{tier.name}** tier limit reached "
                        f"(**{limit}** menus).\n"
                        f"[Upgrade to unlock more](https://pizzahat.vercel.app/premium)"
                    )
                )
            )

        row = await self.bot.db.fetchrow(
            "INSERT INTO role_menus (guild_id, name, type, mode, created_by) "
            "VALUES ($1,$2,$3,$4,$5) RETURNING id",
            ctx.guild.id,
            name,
            type_,
            mode,
            ctx.author.id,
        )
        p = ctx.prefix
        await ctx.send(
            embed=green_embed(
                description=(
                    f"{self.bot.yes} Created role menu `#{row['id']}` — **{name}**\n"
                    f"Type: `{type_}` · Mode: `{mode}`\n\n"
                    f"Next:\n"
                    f"• `{p}rolemenu add {row['id']} @role` — add roles\n"
                    f"• `{p}rolemenu post {row['id']} #channel` — post it"
                )
            )
        )

    @rolemenu.command(name="delete", aliases=["remove", "del"])
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def rm_delete(self, ctx: Context, menu_id: int):
        """Delete a role menu and unposts its message."""
        if not ctx.guild or not self.bot.db:
            return

        menu = await _resolve_menu(ctx, menu_id)
        if not menu:
            return

        if menu["channel_id"] and menu["message_id"]:
            ch = ctx.guild.get_channel(menu["channel_id"])
            if isinstance(ch, (discord.TextChannel, discord.Thread)):
                try:
                    msg = await ch.fetch_message(menu["message_id"])
                    await msg.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass

        await self.bot.db.execute("DELETE FROM role_menus WHERE id=$1", menu_id)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Role menu `#{menu_id}` (`{menu['name']}`) deleted."
            )
        )

    @rolemenu.command(name="toggle", aliases=["enable", "disable"])
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def rm_toggle(self, ctx: Context, menu_id: int):
        """Toggle a role menu on or off."""
        if not ctx.guild or not self.bot.db:
            return

        menu = await _resolve_menu(ctx, menu_id)
        if not menu:
            return

        row = await self.bot.db.fetchrow(
            "UPDATE role_menus SET enabled = NOT enabled WHERE id=$1 RETURNING enabled",
            menu_id,
        )
        await refresh_menu(self.bot, menu_id)
        status = "✅ enabled" if row["enabled"] else "❌ disabled"
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Role menu `#{menu_id}` {status}."
            )
        )

    @rolemenu.command(name="show", aliases=["info"])
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def rm_show(self, ctx: Context, menu_id: int):
        """Show full details of a role menu."""
        if not ctx.guild or not self.bot.db:
            return

        menu = await _resolve_menu(ctx, menu_id)
        if not menu:
            return

        items = await _fetch_items(self.bot, menu_id)

        em = await ctx_embed(ctx, title=f"🎭  Role Menu: {menu['name']}")
        em.add_field(
            name="Status",
            value="✅ Enabled" if menu["enabled"] else "❌ Disabled",
            inline=True,
        )
        em.add_field(name="Type", value=f"`{menu['type']}`", inline=True)
        em.add_field(name="Mode", value=f"`{menu['mode']}`", inline=True)

        if menu["message_id"] and menu["channel_id"]:
            em.add_field(
                name="Posted in",
                value=f"<#{menu['channel_id']}> ([jump](https://discord.com/channels/"
                f"{ctx.guild.id}/{menu['channel_id']}/{menu['message_id']}))",
                inline=False,
            )
        else:
            em.add_field(name="Posted in", value="Not posted yet", inline=False)

        if menu.get("title"):
            em.add_field(name="Embed title", value=menu["title"], inline=False)
        if menu.get("description"):
            em.add_field(
                name="Embed description",
                value=menu["description"][:200],
                inline=False,
            )
        if menu.get("max_selections"):
            em.add_field(
                name="Max selections", value=str(menu["max_selections"]), inline=True
            )
        if menu.get("required_role_id"):
            em.add_field(
                name="Required role",
                value=f"<@&{menu['required_role_id']}>",
                inline=True,
            )

        if items:
            item_lines = [
                f"• {(it.get('emoji') or '')} <@&{it['role_id']}> "
                f"— `{it.get('label') or '(default)'}`"
                for it in items
            ]
            em.add_field(
                name=f"Roles ({len(items)})",
                value="\n".join(item_lines)[:1024],
                inline=False,
            )
        else:
            em.add_field(name="Roles", value="None yet", inline=False)

        await ctx.send(embed=em)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ITEMS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @rolemenu.command(name="add")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def rm_add(
        self, ctx: Context, menu_id: int, role: discord.Role, *, label: str = ""
    ):
        """Add a role to a menu. Optional label overrides the role name."""
        if not ctx.guild or not self.bot.db:
            return

        menu = await _resolve_menu(ctx, menu_id)
        if not menu:
            return

        if role >= ctx.guild.me.top_role:
            return await ctx.send(
                embed=red_embed(
                    description=(
                        f"{self.bot.no} {role.mention} is at or above my top role — "
                        f"I won't be able to assign it. Move my role above it first."
                    )
                )
            )

        count = (
            await self.bot.db.fetchval(
                "SELECT COUNT(*) FROM role_menu_items WHERE menu_id=$1", menu_id
            )
            or 0
        )
        if count >= DISCORD_MAX_ITEMS:
            return await ctx.send(
                embed=red_embed(
                    description=(
                        f"{self.bot.no} Discord limits role menus to **{DISCORD_MAX_ITEMS}** roles."
                    )
                )
            )

        result = await self.bot.db.execute(
            "INSERT INTO role_menu_items (menu_id, role_id, label, position) "
            "VALUES ($1,$2,$3,$4) ON CONFLICT (menu_id, role_id) DO NOTHING",
            menu_id,
            role.id,
            (label.strip() or None),
            count,
        )
        if result == "INSERT 0 0":
            return await ctx.send(
                embed=orange_embed(
                    description=f"{role.mention} is already in menu `#{menu_id}`."
                )
            )

        await refresh_menu(self.bot, menu_id)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Added {role.mention} to `#{menu_id}`."
            )
        )

    @rolemenu.command(name="rmrole", aliases=["delrole"])
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def rm_rmrole(self, ctx: Context, menu_id: int, role: discord.Role):
        """Remove a role from a menu."""
        if not ctx.guild or not self.bot.db:
            return

        menu = await _resolve_menu(ctx, menu_id)
        if not menu:
            return

        result = await self.bot.db.execute(
            "DELETE FROM role_menu_items WHERE menu_id=$1 AND role_id=$2",
            menu_id,
            role.id,
        )
        if result == "DELETE 0":
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} {role.mention} isn't in `#{menu_id}`."
                )
            )

        await refresh_menu(self.bot, menu_id)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Removed {role.mention} from `#{menu_id}`."
            )
        )

    @rolemenu.command(name="emoji")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @premium(tier=Tier.BASIC)
    async def rm_emoji(
        self, ctx: Context, menu_id: int, role: discord.Role, emoji: str
    ):
        """Set the emoji for a role in a menu. (Basic+)"""
        if not ctx.guild or not self.bot.db:
            return

        menu = await _resolve_menu(ctx, menu_id)
        if not menu:
            return

        result = await self.bot.db.execute(
            "UPDATE role_menu_items SET emoji=$1 WHERE menu_id=$2 AND role_id=$3",
            emoji,
            menu_id,
            role.id,
        )
        if result == "UPDATE 0":
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} {role.mention} isn't in `#{menu_id}`."
                )
            )

        await refresh_menu(self.bot, menu_id)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Emoji for {role.mention} set to {emoji}."
            )
        )

    @rolemenu.command(name="label")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @premium(tier=Tier.BASIC)
    async def rm_label(
        self, ctx: Context, menu_id: int, role: discord.Role, *, label: str
    ):
        """Set a custom label for a role in the menu. (Basic+)"""
        if not ctx.guild or not self.bot.db:
            return

        menu = await _resolve_menu(ctx, menu_id)
        if not menu:
            return

        result = await self.bot.db.execute(
            "UPDATE role_menu_items SET label=$1 WHERE menu_id=$2 AND role_id=$3",
            label[:80],
            menu_id,
            role.id,
        )
        if result == "UPDATE 0":
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} {role.mention} isn't in `#{menu_id}`."
                )
            )

        await refresh_menu(self.bot, menu_id)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Label for {role.mention} set to `{label[:80]}`."
            )
        )

    @rolemenu.command(name="desc")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @premium(tier=Tier.BASIC)
    async def rm_desc(
        self, ctx: Context, menu_id: int, role: discord.Role, *, description: str
    ):
        """Set a per-role description (shown in dropdowns). (Basic+)"""
        if not ctx.guild or not self.bot.db:
            return

        menu = await _resolve_menu(ctx, menu_id)
        if not menu:
            return

        result = await self.bot.db.execute(
            "UPDATE role_menu_items SET description=$1 WHERE menu_id=$2 AND role_id=$3",
            description[:100],
            menu_id,
            role.id,
        )
        if result == "UPDATE 0":
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} {role.mention} isn't in `#{menu_id}`."
                )
            )

        await refresh_menu(self.bot, menu_id)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Description set for {role.mention}."
            )
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # MENU-LEVEL CONFIG
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @rolemenu.command(name="mode")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def rm_mode(self, ctx: Context, menu_id: int, mode: str):
        """Set selection mode: `single` (one role only) or `multi`."""
        if not ctx.guild or not self.bot.db:
            return

        mode = mode.lower()
        if mode not in VALID_MODES:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} Mode must be `single` or `multi`."
                )
            )

        menu = await _resolve_menu(ctx, menu_id)
        if not menu:
            return

        await self.bot.db.execute(
            "UPDATE role_menus SET mode=$1 WHERE id=$2", mode, menu_id
        )
        await refresh_menu(self.bot, menu_id)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Menu `#{menu_id}` mode set to `{mode}`."
            )
        )

    @rolemenu.command(name="title")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @premium(tier=Tier.BASIC)
    async def rm_title(self, ctx: Context, menu_id: int, *, title: str):
        """Set the embed title for a menu. (Basic+)"""
        if not ctx.guild or not self.bot.db:
            return

        menu = await _resolve_menu(ctx, menu_id)
        if not menu:
            return

        await self.bot.db.execute(
            "UPDATE role_menus SET title=$1 WHERE id=$2", title[:256], menu_id
        )
        await refresh_menu(self.bot, menu_id)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Title updated for `#{menu_id}`."
            )
        )

    @rolemenu.command(name="description", aliases=["text"])
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @premium(tier=Tier.BASIC)
    async def rm_description(self, ctx: Context, menu_id: int, *, description: str):
        """Set the embed description body for a menu. (Basic+)"""
        if not ctx.guild or not self.bot.db:
            return

        menu = await _resolve_menu(ctx, menu_id)
        if not menu:
            return

        await self.bot.db.execute(
            "UPDATE role_menus SET description=$1 WHERE id=$2",
            description[:4000],
            menu_id,
        )
        await refresh_menu(self.bot, menu_id)
        await ctx.send(
            embed=green_embed(
                description=f"{self.bot.yes} Description updated for `#{menu_id}`."
            )
        )

    @rolemenu.command(name="max")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @premium(tier=Tier.PRO)
    async def rm_max(self, ctx: Context, menu_id: int, limit: int):
        """Set the max number of roles a user can pick from this menu. `0` to clear. (Pro)"""
        if not ctx.guild or not self.bot.db:
            return

        if limit < 0 or limit > DISCORD_MAX_ITEMS:
            return await ctx.send(
                embed=red_embed(
                    description=(
                        f"{self.bot.no} Limit must be between `0` and `{DISCORD_MAX_ITEMS}`."
                    )
                )
            )

        menu = await _resolve_menu(ctx, menu_id)
        if not menu:
            return

        await self.bot.db.execute(
            "UPDATE role_menus SET max_selections=$1 WHERE id=$2",
            (limit or None),
            menu_id,
        )
        await refresh_menu(self.bot, menu_id)
        msg = (
            f"Max selections for `#{menu_id}` set to `{limit}`."
            if limit
            else f"Cleared selection limit on `#{menu_id}`."
        )
        await ctx.send(embed=green_embed(description=f"{self.bot.yes} {msg}"))

    @rolemenu.command(name="required")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @premium(tier=Tier.PRO)
    async def rm_required(
        self, ctx: Context, menu_id: int, role: Optional[discord.Role] = None
    ):
        """Require members to already have a role before using a menu. Pass no role to clear. (Pro)"""
        if not ctx.guild or not self.bot.db:
            return

        menu = await _resolve_menu(ctx, menu_id)
        if not menu:
            return

        await self.bot.db.execute(
            "UPDATE role_menus SET required_role_id=$1 WHERE id=$2",
            role.id if role else None,
            menu_id,
        )
        if role:
            msg = f"Members now need {role.mention} to use `#{menu_id}`."
        else:
            msg = f"Cleared required role on `#{menu_id}`."
        await ctx.send(embed=green_embed(description=f"{self.bot.yes} {msg}"))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # POST / REFRESH
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @rolemenu.command(name="post", aliases=["publish"])
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(
        send_messages=True, embed_links=True, manage_roles=True
    )
    async def rm_post(self, ctx: Context, menu_id: int, channel: discord.TextChannel):
        """Post (or repost) a role menu into a channel."""
        if not ctx.guild or not self.bot.db:
            return

        menu = await _resolve_menu(ctx, menu_id)
        if not menu:
            return

        items = await _fetch_items(self.bot, menu_id)
        if not items:
            return await ctx.send(
                embed=red_embed(
                    description=(
                        f"{self.bot.no} Add at least one role first: "
                        f"`{ctx.prefix}rolemenu add {menu_id} @role`"
                    )
                )
            )

        # If already posted, try to delete the old message
        if menu["channel_id"] and menu["message_id"]:
            old_ch = ctx.guild.get_channel(menu["channel_id"])
            if isinstance(old_ch, (discord.TextChannel, discord.Thread)):
                try:
                    old_msg = await old_ch.fetch_message(menu["message_id"])
                    await old_msg.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass

        try:
            message = await publish_menu(self.bot, menu, items, channel)
        except discord.Forbidden:
            return await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} I can't post in {channel.mention}."
                )
            )

        await ctx.send(
            embed=green_embed(
                description=(
                    f"{self.bot.yes} Posted `#{menu_id}` in {channel.mention} "
                    f"([jump]({message.jump_url}))."
                )
            )
        )

    @rolemenu.command(name="refresh", aliases=["sync"])
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def rm_refresh(self, ctx: Context, menu_id: int):
        """Re-render the posted message (after manual edits to roles/labels)."""
        if not ctx.guild or not self.bot.db:
            return

        menu = await _resolve_menu(ctx, menu_id)
        if not menu:
            return

        ok = await refresh_menu(self.bot, menu_id)
        if not ok:
            return await ctx.send(
                embed=orange_embed(
                    description=(
                        f"Couldn't refresh `#{menu_id}` — has it been posted yet? "
                        f"Use `{ctx.prefix}rolemenu post {menu_id} #channel`."
                    )
                )
            )
        await ctx.send(
            embed=green_embed(description=f"{self.bot.yes} Refreshed `#{menu_id}`.")
        )


async def setup(bot: PizzaHat) -> None:
    await bot.add_cog(RoleMenus(bot))
