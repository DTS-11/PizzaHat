import ssl
from typing import Union

import asyncpg
from utils.config import DEFAULT_PREFIX, PG_URL

_prefix_cache: dict[int, str] = {}


async def get_prefix(pool, guild_id: int) -> str:
    if guild_id in _prefix_cache:
        return _prefix_cache[guild_id]

    if pool is None:
        return DEFAULT_PREFIX

    prefix = await pool.fetchval(
        "SELECT prefix FROM prefix WHERE guild_id = $1", guild_id
    )
    result = prefix if prefix else DEFAULT_PREFIX
    _prefix_cache[guild_id] = result
    return result


async def set_prefix(pool, guild_id: int, prefix: str) -> None:
    if pool:
        await pool.execute(
            "INSERT INTO prefix (guild_id, prefix) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET prefix = $2",
            guild_id,
            prefix,
        )

    _prefix_cache[guild_id] = prefix


async def invalidate_prefix_cache(guild_id: int) -> None:
    """Remove a guild's prefix from cache, e.g. when the prefix row is deleted."""
    _prefix_cache.pop(guild_id, None)


async def create_db_pool() -> Union[asyncpg.pool.Pool, None]:
    ssl_object = ssl.create_default_context()
    ssl_object.check_hostname = False
    ssl_object.verify_mode = ssl.CERT_NONE

    return await asyncpg.create_pool(PG_URL, ssl=ssl_object)


async def bootstrap_database(pool: Union[asyncpg.pool.Pool, None]) -> None:
    if pool is None:
        return

    statements = [
        # PREMIUM
        """CREATE TABLE IF NOT EXISTS premium
        (guild_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, polar_subscription_id TEXT NOT NULL, polar_customer_id TEXT NOT NULL, tier INT DEFAULT 1, status TEXT DEFAULT 'active', current_period_start TIMESTAMP, current_period_end TIMESTAMP, cancel_at_period_end BOOL DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW())""",
        # PREFIX
        """CREATE TABLE IF NOT EXISTS prefix
        (guild_id BIGINT PRIMARY KEY, prefix TEXT DEFAULT 'p!')""",
        # AFK
        """CREATE TABLE IF NOT EXISTS afk
        (guild_id BIGINT, user_id BIGINT, reason TEXT)""",
        # WARNLOGS
        """CREATE TABLE IF NOT EXISTS warnlogs
        (id SERIAL PRIMARY KEY, guild_id BIGINT, user_id BIGINT, mod_id BIGINT, reason TEXT)""",
        # LOGS_CONFIG
        """CREATE TABLE IF NOT EXISTS logs_config
        (guild_id BIGINT PRIMARY KEY, module TEXT[] DEFAULT ARRAY['all'])""",
        # GUILD_LOGS
        """CREATE TABLE IF NOT EXISTS guild_logs
        (guild_id BIGINT PRIMARY KEY, channel_id BIGINT)""",
        # AUTOMOD
        """CREATE TABLE IF NOT EXISTS automod
        (guild_id BIGINT PRIMARY KEY, enabled BOOL DEFAULT false)""",
        # ANTIALT
        """CREATE TABLE IF NOT EXISTS antialt
        (guild_id BIGINT PRIMARY KEY, enabled BOOL DEFAULT false, min_age INT, restricted_role BIGINT, level INT)""",
        # TAGS
        """CREATE TABLE IF NOT EXISTS tags
        (guild_id BIGINT, tag_name TEXT, content TEXT, creator BIGINT)""",
        # STAR_CONFIG
        """CREATE TABLE IF NOT EXISTS star_config
        (guild_id BIGINT PRIMARY KEY, channel_id BIGINT, star_count INT DEFAULT 5, self_star BOOL DEFAULT true)""",
        # STAR_INFO
        """CREATE TABLE IF NOT EXISTS star_info
        (guild_id BIGINT, user_msg_id BIGINT PRIMARY KEY, bot_msg_id BIGINT)""",
        # USER_TIMEZONE
        """CREATE TABLE IF NOT EXISTS user_timezone
        (user_id BIGINT PRIMARY KEY, timezone TEXT)""",
        # TICKETS
        """CREATE TABLE IF NOT EXISTS ticket_logs
        (guild_id BIGINT, thread_id BIGINT PRIMARY KEY, creator_id BIGINT, opened_at TIMESTAMP DEFAULT NOW(), closed_at TIMESTAMP, closed_by BIGINT)""",
    ]

    for statement in statements:
        await pool.execute(statement)

    await pool.execute(
        """
        DELETE FROM afk a
        USING afk b
        WHERE a.ctid < b.ctid
          AND a.guild_id = b.guild_id
          AND a.user_id = b.user_id
        """
    )
    await pool.execute(
        """
        DELETE FROM tags a
        USING tags b
        WHERE a.ctid < b.ctid
          AND a.guild_id = b.guild_id
          AND a.tag_name = b.tag_name
        """
    )
    await pool.execute("ALTER TABLE tags DROP CONSTRAINT IF EXISTS tags_pkey")
    await pool.execute(
        """
        ALTER TABLE tags
        ADD CONSTRAINT tags_pkey PRIMARY KEY (guild_id, tag_name)
        """
    )
    await pool.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS afk_guild_user_idx
        ON afk (guild_id, user_id)
        """
    )
    await pool.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS premium_guild_id_idx
        ON premium (guild_id)
        """
    )
    await pool.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS premium_polar_subscription_idx
        ON premium (polar_subscription_id)
        """
    )
    await pool.execute(
        """
        CREATE INDEX IF NOT EXISTS warnlogs_guild_user_idx
        ON warnlogs (guild_id, user_id)
        """
    )
    await pool.execute(
        """
        CREATE INDEX IF NOT EXISTS star_info_guild_id_idx
        ON star_info (guild_id)
        """
    )
    await pool.execute(
        """
        CREATE INDEX IF NOT EXISTS star_info_bot_msg_id_idx
        ON star_info (bot_msg_id)
        """
    )
