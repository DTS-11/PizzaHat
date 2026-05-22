import datetime
from typing import Any, Optional

from discord import Color, Embed

theme_cache: dict[int, int] = {}


async def get_guild_theme(pool, guild_id: int) -> int:
    if guild_id in theme_cache:
        return theme_cache[guild_id]

    accent_color = await pool.fetchval(
        "SELECT accent_color FROM guild_themes WHERE guild_id = $1", guild_id
    )

    color = accent_color if accent_color else 0x456DD4

    theme_cache[guild_id] = color
    return color


def invalidate_theme_cache(guild_id: int | None = None):
    """Invalidate the theme cache for a guild or all guilds."""

    if guild_id:
        theme_cache.pop(guild_id, None)
    else:
        theme_cache.clear()


def green_embed(
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    timestamp: Optional[bool] = None,
) -> Embed:
    """Creates embed with green color."""

    return Embed(
        title=title,
        description=description,
        color=0x57F287,
        timestamp=datetime.datetime.now() if timestamp else None,
    )


def red_embed(
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    timestamp: Optional[bool] = None,
) -> Embed:
    """Creates embed with red color."""

    return Embed(
        title=title,
        description=description,
        color=0xED4245,
        timestamp=datetime.datetime.now() if timestamp else None,
    )


def orange_embed(
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    timestamp: Optional[bool] = None,
) -> Embed:
    """Creates embed with orange color."""

    return Embed(
        title=title,
        description=description,
        color=0xFAA61A,
        timestamp=datetime.datetime.now() if timestamp else None,
    )


def golden_embed(
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    timestamp: Optional[bool] = None,
) -> Embed:
    """Creates embed with golden color."""

    return Embed(
        title=title,
        description=description,
        color=0xFFD700,
        timestamp=datetime.datetime.now() if timestamp else None,
    )


def normal_embed(
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    color: Optional[int] = None,
    timestamp: Optional[bool] = None,
) -> Embed:
    """Creates embed with bot's default color."""

    return Embed(
        title=title,
        description=description,
        color=color or 0x456DD4,
        timestamp=datetime.datetime.now() if timestamp else None,
    )


async def get_themed_embed(
    pool: Any,
    guild_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    timestamp: Optional[bool] = None,
) -> Embed:
    """Get a normal_embed with guild theme (premium) support."""

    from utils.custom_checks import is_premium_guild

    if await is_premium_guild(pool, guild_id):
        color = await get_guild_theme(pool, guild_id)
    else:
        color = 0x456DD4

    return normal_embed(title, description, color=color, timestamp=timestamp)


async def ctx_embed(
    ctx: Any,
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    color: Optional[int] = None,
    timestamp: Optional[bool] = None,
) -> Embed:
    """Get a themed embed using context (auto-detects guild/premium)."""

    if ctx.guild and ctx.bot.db:
        return await get_themed_embed(
            ctx.bot.db, ctx.guild.id, title, description, timestamp=timestamp
        )
    return normal_embed(title, description, timestamp=timestamp)


async def guild_embed(
    pool: Any,
    guild_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    timestamp: Optional[bool] = None,
) -> Embed:
    """Get a themed embed using pool and guild_id (for use in events/listeners)."""

    return await get_themed_embed(
        pool, guild_id, title, description, timestamp=timestamp
    )


def embed_from_data(data: dict) -> Embed:
    """Build a discord.Embed from stored template JSONB data.

    Supported keys: title, description, color (int or #hex), url,
    footer {text, icon_url}, author {name, url, icon_url},
    image {url} or "url", thumbnail {url} or "url",
    fields [{name, value, inline}].
    """

    raw_color = data.get("color")
    if isinstance(raw_color, str) and raw_color.startswith("#"):
        color = int(raw_color.lstrip("#"), 16)
    elif isinstance(raw_color, (int, float)):
        color = int(raw_color)
    else:
        color = 0x456DD4

    em = Embed(
        title=data.get("title"),
        description=data.get("description"),
        color=color,
        url=data.get("url"),
    )

    if footer := data.get("footer"):
        em.set_footer(
            text=footer.get("text") if isinstance(footer, dict) else str(footer),
            icon_url=footer.get("icon_url") if isinstance(footer, dict) else None,
        )
    if author := data.get("author"):
        em.set_author(
            name=author.get("name", "") if isinstance(author, dict) else str(author),
            url=author.get("url") if isinstance(author, dict) else None,
            icon_url=author.get("icon_url") if isinstance(author, dict) else None,
        )
    if image := data.get("image"):
        url = image.get("url") if isinstance(image, dict) else image
        if url:
            em.set_image(url=url)
    if thumbnail := data.get("thumbnail"):
        url = thumbnail.get("url") if isinstance(thumbnail, dict) else thumbnail
        if url:
            em.set_thumbnail(url=url)
    for field in data.get("fields", []):
        em.add_field(
            name=field.get("name", ""),
            value=field.get("value", ""),
            inline=bool(field.get("inline", False)),
        )
    return em


def render_template_vars(em: Embed, **kwargs: str) -> Embed:
    """Substitute {key} placeholders in an embed's text fields (modifies in-place)."""

    def sub(text: Optional[str]) -> Optional[str]:
        if not text:
            return text
        for k, v in kwargs.items():
            text = text.replace(f"{{{k}}}", v)
        return text

    em.title = sub(em.title)
    em.description = sub(em.description)
    if em.footer.text:
        em.set_footer(text=sub(em.footer.text), icon_url=em.footer.icon_url)
    old_fields = [(f.name, f.value, f.inline) for f in em.fields]
    em.clear_fields()
    for name, value, inline in old_fields:
        em.add_field(name=sub(name) or "", value=sub(value) or "", inline=inline)
    return em


async def resolve_template(
    pool: Any,
    template_id: Optional[int],
    fallback: Embed,
    **render_vars: str,
) -> Embed:
    """Return a built Embed from an embed_templates row, or *fallback* if unavailable.

    Template vars (e.g. user, user.mention, guild) are substituted when provided.
    ON DELETE SET NULL on the FK means a deleted template silently returns the fallback.
    """

    if not pool or not template_id:
        return fallback
    row = await pool.fetchrow(
        "SELECT data FROM embed_templates WHERE id=$1", template_id
    )
    if not row or not row["data"]:
        return fallback
    em = embed_from_data(dict(row["data"]))
    if render_vars:
        render_template_vars(em, **render_vars)
    return em


async def resolve_template_or_none(
    pool: Any,
    template_id: Optional[int],
    **render_vars: str,
) -> Optional[Embed]:
    """Return a built Embed from an embed_templates row, or None if unavailable."""

    if not pool or not template_id:
        return None
    row = await pool.fetchrow(
        "SELECT data FROM embed_templates WHERE id=$1", template_id
    )
    if not row or not row["data"]:
        return None
    em = embed_from_data(dict(row["data"]))
    if render_vars:
        render_template_vars(em, **render_vars)
    return em
