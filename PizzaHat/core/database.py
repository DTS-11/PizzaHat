import ssl
from typing import Union

import asyncpg

from utils.config import PG_URL


async def create_db_pool() -> Union[asyncpg.pool.Pool, None]:
    ssl_object = ssl.create_default_context()
    ssl_object.check_hostname = False
    ssl_object.verify_mode = ssl.CERT_NONE

    return await asyncpg.create_pool(PG_URL, ssl=ssl_object)


async def bootstrap_database(pool: Union[asyncpg.pool.Pool, None]) -> None:
    if pool is None:
        return

    statements = [
        """CREATE TABLE IF NOT EXISTS premium
        (guild_id BIGINT PRIMARY KEY)""",
        """CREATE TABLE IF NOT EXISTS afk
        (guild_id BIGINT, user_id BIGINT, reason TEXT)""",
        """CREATE TABLE IF NOT EXISTS warnlogs
        (id SERIAL PRIMARY KEY, guild_id BIGINT, user_id BIGINT, mod_id BIGINT, reason TEXT)""",
        """CREATE TABLE IF NOT EXISTS logs_config
        (guild_id BIGINT PRIMARY KEY, module TEXT[] DEFAULT ARRAY['all'])""",
        """CREATE TABLE IF NOT EXISTS guild_logs
        (guild_id BIGINT PRIMARY KEY, channel_id BIGINT)""",
        """CREATE TABLE IF NOT EXISTS automod
        (guild_id BIGINT PRIMARY KEY, enabled BOOL DEFAULT false)""",
        """CREATE TABLE IF NOT EXISTS antialt
        (guild_id BIGINT PRIMARY KEY, enabled BOOL DEFAULT false, min_age INT, restricted_role BIGINT, level INT)""",
        """CREATE TABLE IF NOT EXISTS tags
        (guild_id BIGINT, tag_name TEXT, content TEXT, creator BIGINT)""",
        """CREATE TABLE IF NOT EXISTS star_config
        (guild_id BIGINT PRIMARY KEY, channel_id BIGINT, star_count INT DEFAULT 5, self_star BOOL DEFAULT true)""",
        """CREATE TABLE IF NOT EXISTS star_info
        (guild_id BIGINT, user_msg_id BIGINT PRIMARY KEY, bot_msg_id BIGINT)""",
        """CREATE TABLE IF NOT EXISTS user_timezone
        (user_id BIGINT PRIMARY KEY, timezone TEXT)""",
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
