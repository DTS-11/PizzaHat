"""PostgreSQL connection and schema bootstrap.

Creates the asyncpg pool from ``PG_URL`` and ensures all active application
tables and indexes exist at startup.
"""

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
        # EMBED_TEMPLATES
        """CREATE TABLE IF NOT EXISTS embed_templates
        (id SERIAL PRIMARY KEY, guild_id BIGINT, name TEXT, data JSONB, created_by BIGINT, created_at TIMESTAMP DEFAULT NOW())""",
        # PREMIUM
        """CREATE TABLE IF NOT EXISTS premium
        (guild_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, polar_subscription_id TEXT NOT NULL UNIQUE, polar_customer_id TEXT NOT NULL, tier INT DEFAULT 1, status TEXT DEFAULT 'active', current_period_start TIMESTAMP, current_period_end TIMESTAMP, cancel_at_period_end BOOL DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW())""",
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
        # STAR_INFO
        """CREATE TABLE IF NOT EXISTS star_info
        (guild_id BIGINT, user_msg_id BIGINT PRIMARY KEY, bot_msg_id BIGINT)""",
        # USER_TIMEZONE
        """CREATE TABLE IF NOT EXISTS user_timezone
        (user_id BIGINT PRIMARY KEY, timezone TEXT)""",
        # TICKET_PANEL
        """CREATE TABLE IF NOT EXISTS ticket_panels
        (id SERIAL PRIMARY KEY, guild_id BIGINT, channel_id BIGINT, message_id BIGINT, name TEXT, template_id INT REFERENCES embed_templates(id) ON DELETE SET NULL, button_label TEXT DEFAULT 'Create Ticket', button_emoji TEXT, support_role_id BIGINT, enabled BOOL DEFAULT TRUE)""",
        # TICKET_LOGS
        """CREATE TABLE IF NOT EXISTS ticket_logs
        (guild_id BIGINT, thread_id BIGINT PRIMARY KEY, creator_id BIGINT, opened_at TIMESTAMP DEFAULT NOW(), closed_at TIMESTAMP, closed_by BIGINT)""",
        # ROLE_MENUS
        """CREATE TABLE IF NOT EXISTS role_menus
        (id SERIAL PRIMARY KEY, guild_id BIGINT NOT NULL, channel_id BIGINT, message_id BIGINT, name TEXT NOT NULL, title TEXT, description TEXT, template_id INT REFERENCES embed_templates(id) ON DELETE SET NULL, type TEXT NOT NULL DEFAULT 'button', mode TEXT NOT NULL DEFAULT 'multi', max_selections INT, required_role_id BIGINT, enabled BOOL DEFAULT TRUE, created_at TIMESTAMP DEFAULT NOW(), created_by BIGINT)""",
        # ROLE_MENU_ITEMS
        """CREATE TABLE IF NOT EXISTS role_menu_items
        (menu_id INT NOT NULL REFERENCES role_menus(id) ON DELETE CASCADE, role_id BIGINT NOT NULL, label TEXT, emoji TEXT, description TEXT, position INT DEFAULT 0, PRIMARY KEY (menu_id, role_id))""",
        # WORKFLOWS (unified Trigger -> Condition -> Action engine)
        """CREATE TABLE IF NOT EXISTS workflows
        (id SERIAL PRIMARY KEY,
         guild_id BIGINT NOT NULL,
         name TEXT NOT NULL,
         enabled BOOLEAN DEFAULT TRUE,
         trigger_type TEXT NOT NULL,
         trigger_config JSONB NOT NULL DEFAULT '{}'::jsonb,
         conditions JSONB NOT NULL DEFAULT '[]'::jsonb,
         actions JSONB NOT NULL DEFAULT '[]'::jsonb,
         created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
         updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
    ]

    for statement in statements:
        await pool.execute(statement)

    indexes = [
        "CREATE INDEX IF NOT EXISTS warnlogs_guild_user_idx ON warnlogs (guild_id, user_id)",
        "CREATE INDEX IF NOT EXISTS warnlogs_created_at_idx ON warnlogs (guild_id, user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS star_info_guild_id_idx ON star_info (guild_id)",
        "CREATE INDEX IF NOT EXISTS star_info_bot_msg_id_idx ON star_info (bot_msg_id)",
        "CREATE INDEX IF NOT EXISTS role_menus_guild_id_idx ON role_menus (guild_id)",
        "CREATE INDEX IF NOT EXISTS workflows_guild_id_idx ON workflows (guild_id)",
        "CREATE INDEX IF NOT EXISTS workflows_guild_enabled_idx ON workflows (guild_id, enabled) WHERE enabled = TRUE",
        "CREATE INDEX IF NOT EXISTS workflows_guild_trigger_idx ON workflows (guild_id, trigger_type)",
    ]

    for index in indexes:
        await pool.execute(index)
