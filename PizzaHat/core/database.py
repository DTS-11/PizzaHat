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
        (guild_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, polar_subscription_id TEXT NOT NULL UNIQUE, polar_customer_id TEXT NOT NULL, tier INT DEFAULT 1, status TEXT DEFAULT 'active', current_period_start TIMESTAMP, current_period_end TIMESTAMP, cancel_at_period_end BOOL DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW())""",
        # PREFIX
        """CREATE TABLE IF NOT EXISTS prefix
        (guild_id BIGINT PRIMARY KEY, prefix TEXT DEFAULT 'p!')""",
        # AFK
        """CREATE TABLE IF NOT EXISTS afk
        (guild_id BIGINT, user_id BIGINT, reason TEXT, UNIQUE (guild_id, user_id))""",
        # WARNLOGS
        """CREATE TABLE IF NOT EXISTS warnlogs
        (id SERIAL PRIMARY KEY, guild_id BIGINT, user_id BIGINT, mod_id BIGINT, reason TEXT, created_at TIMESTAMP DEFAULT NOW())""",
        # LOGS_CONFIG
        """CREATE TABLE IF NOT EXISTS logs_config
        (guild_id BIGINT PRIMARY KEY, module TEXT[] DEFAULT ARRAY['all'])""",
        # GUILD_LOGS
        """CREATE TABLE IF NOT EXISTS guild_logs
        (guild_id BIGINT PRIMARY KEY, channel_id BIGINT)""",
        # AUTOMOD
        """CREATE TABLE IF NOT EXISTS automod
        (guild_id BIGINT PRIMARY KEY, enabled BOOL DEFAULT false, modules TEXT[] DEFAULT ARRAY['banned_words', 'all_caps', 'message_spam', 'invites', 'mass_mentions', 'emoji_spam', 'zalgo_text'], warn_action TEXT DEFAULT 'none', warn_threshold INT DEFAULT 0, config JSONB DEFAULT '{}')""",
        # ANTIALT
        """CREATE TABLE IF NOT EXISTS antialt
        (guild_id BIGINT PRIMARY KEY, enabled BOOL DEFAULT false, min_age INT, restricted_role BIGINT, level INT)""",
        # TAGS
        """CREATE TABLE IF NOT EXISTS tags
        (guild_id BIGINT, tag_name TEXT, content TEXT, creator BIGINT, uses INT DEFAULT 0, PRIMARY KEY (guild_id, tag_name))""",
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
        # GUILD_THEMES
        """CREATE TABLE IF NOT EXISTS guild_themes
        (guild_id BIGINT PRIMARY KEY, accent_color TEXT)""",
        # WORKFLOWS (legacy — kept for backwards compat, superseded by event_actions)
        """CREATE TABLE IF NOT EXISTS workflows
        (id SERIAL PRIMARY KEY, guild_id BIGINT NOT NULL, name TEXT NOT NULL, trigger_type TEXT NOT NULL, trigger_config JSONB DEFAULT '{}', actions JSONB DEFAULT '[]', enabled BOOL DEFAULT TRUE, created_at TIMESTAMP DEFAULT NOW(), created_by BIGINT NOT NULL)""",
        # AUTO_RESPONDERS
        """CREATE TABLE IF NOT EXISTS auto_responders
        (id SERIAL PRIMARY KEY, guild_id BIGINT NOT NULL, trigger_text TEXT NOT NULL, trigger_type TEXT DEFAULT 'contains', response TEXT NOT NULL, channel_ids BIGINT[] DEFAULT '{}', role_ids BIGINT[] DEFAULT '{}', cooldown_seconds INT DEFAULT 0, enabled BOOL DEFAULT TRUE, use_count INT DEFAULT 0, created_at TIMESTAMP DEFAULT NOW(), created_by BIGINT NOT NULL)""",
        # SCHEDULED_MESSAGES
        """CREATE TABLE IF NOT EXISTS scheduled_messages
        (id SERIAL PRIMARY KEY, guild_id BIGINT NOT NULL, channel_id BIGINT NOT NULL, message TEXT NOT NULL, schedule_type TEXT DEFAULT 'once', interval_type TEXT, next_run TIMESTAMPTZ NOT NULL, timezone TEXT DEFAULT 'UTC', enabled BOOL DEFAULT TRUE, last_run TIMESTAMPTZ, run_count INT DEFAULT 0, created_at TIMESTAMP DEFAULT NOW(), created_by BIGINT NOT NULL)""",
        # JOIN_AUTOMATION
        """CREATE TABLE IF NOT EXISTS join_automation
        (guild_id BIGINT PRIMARY KEY, enabled BOOL DEFAULT TRUE, auto_role_ids BIGINT[] DEFAULT '{}', welcome_channel_id BIGINT, welcome_message TEXT, welcome_dm TEXT, created_at TIMESTAMP DEFAULT NOW())""",
        # EVENT_ACTIONS
        """CREATE TABLE IF NOT EXISTS event_actions
        (id SERIAL PRIMARY KEY, guild_id BIGINT NOT NULL, name TEXT NOT NULL, event_type TEXT NOT NULL, actions JSONB DEFAULT '[]', enabled BOOL DEFAULT TRUE, run_count INT DEFAULT 0, created_at TIMESTAMP DEFAULT NOW(), created_by BIGINT NOT NULL)""",
    ]

    for statement in statements:
        await pool.execute(statement)

    indexes = [
        "CREATE INDEX IF NOT EXISTS warnlogs_guild_user_idx ON warnlogs (guild_id, user_id)",
        "CREATE INDEX IF NOT EXISTS warnlogs_created_at_idx ON warnlogs (guild_id, user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS star_info_guild_id_idx ON star_info (guild_id)",
        "CREATE INDEX IF NOT EXISTS star_info_bot_msg_id_idx ON star_info (bot_msg_id)",
        "CREATE INDEX IF NOT EXISTS workflows_guild_id_idx ON workflows (guild_id)",
        "CREATE INDEX IF NOT EXISTS auto_responders_guild_id_idx ON auto_responders (guild_id)",
        "CREATE INDEX IF NOT EXISTS scheduled_messages_guild_id_idx ON scheduled_messages (guild_id)",
        "CREATE INDEX IF NOT EXISTS scheduled_messages_next_run_idx ON scheduled_messages (next_run) WHERE enabled = TRUE",
        "CREATE INDEX IF NOT EXISTS event_actions_guild_id_idx ON event_actions (guild_id)",
    ]

    for index in indexes:
        await pool.execute(index)
