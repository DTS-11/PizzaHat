-- This is the first managed migration. The Discord engine is a new deployment:
-- no legacy data is imported. Repeatable bootstrap SQL has been replaced by an
-- ordered migration ledger so future schema changes are explicit and reviewable.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Object names overlap between the legacy tables and the new views, and
-- PostgreSQL raises WrongObjectTypeError when DROP TABLE targets a view (or
-- vice versa). Inspect pg_class and drop whatever type is actually present.
DO $lucent_drop$
DECLARE
    object_name TEXT;
    object_kind "char";
BEGIN
    FOREACH object_name IN ARRAY ARRAY[
        'role_menu_items', 'role_menus', 'ticket_panels', 'tickets',
        'ticket_logs', 'workflow_runs', 'workflow_run_state', 'workflows',
        'workflow_definitions', 'moderation_case_edits', 'moderation_cases',
        'warnlogs', 'automation_config', 'automod', 'antialt', 'guild_config',
        'guild_logs', 'logs_config', 'star_info', 'tags', 'embed_templates',
        'user_preferences', 'user_timezone', 'scheduled_tasks', 'wordlists',
        'subscriptions', 'premium'
    ]
    LOOP
        SELECT c.relkind INTO object_kind
        FROM pg_class AS c
        WHERE c.relname = object_name
          AND c.relnamespace = 'public'::regnamespace;

        IF object_kind = 'v' THEN
            EXECUTE format('DROP VIEW IF EXISTS %I CASCADE', object_name);
        ELSIF object_kind IN ('r', 'p', 'f') THEN
            EXECUTE format('DROP TABLE IF EXISTS %I CASCADE', object_name);
        END IF;
    END LOOP;
END
$lucent_drop$;


CREATE TABLE guild_config (
    guild_id BIGINT PRIMARY KEY,
    log_channel_id BIGINT,
    log_modules TEXT[] NOT NULL DEFAULT ARRAY['all']::TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE automation_config (
    guild_id BIGINT PRIMARY KEY,
    automod JSONB NOT NULL DEFAULT '{}'::jsonb,
    antialt JSONB NOT NULL DEFAULT '{}'::jsonb,
    safety JSONB NOT NULL DEFAULT '{}'::jsonb,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE subscriptions (
    guild_id BIGINT PRIMARY KEY,
    owner_user_id BIGINT NOT NULL,
    polar_subscription_id TEXT NOT NULL UNIQUE,
    polar_customer_id TEXT NOT NULL,
    tier INTEGER NOT NULL DEFAULT 0 CHECK (tier BETWEEN 0 AND 2),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'cancelled', 'expired')),
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Kept as a read-only compatibility view. All code paths should move to the
-- entitlement service, but third-party SQL integrations can still inspect it.
CREATE VIEW premium AS
SELECT
    guild_id,
    owner_user_id AS user_id,
    polar_subscription_id,
    polar_customer_id,
    tier,
    status,
    current_period_start,
    current_period_end,
    cancel_at_period_end,
    created_at,
    updated_at
FROM subscriptions;

CREATE INDEX subscriptions_status_period_idx
    ON subscriptions (status, current_period_end)
    WHERE status = 'active';


CREATE TABLE user_preferences (
    user_id BIGINT PRIMARY KEY,
    timezone TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE VIEW user_timezone AS
SELECT user_id, timezone FROM user_preferences;


CREATE TABLE embed_templates (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (guild_id, name)
);

CREATE INDEX embed_templates_guild_id_idx ON embed_templates (guild_id);


CREATE TABLE tags (
    guild_id BIGINT NOT NULL,
    tag_name TEXT NOT NULL,
    content TEXT NOT NULL,
    creator BIGINT NOT NULL,
    uses INTEGER NOT NULL DEFAULT 0 CHECK (uses >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (guild_id, tag_name)
);


CREATE TABLE moderation_cases (
    case_id UUID PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    subject_user_id BIGINT NOT NULL,
    moderator_user_id BIGINT NOT NULL,
    action_type TEXT NOT NULL CHECK (action_type IN (
        'warn', 'timeout', 'kick', 'ban', 'unban', 'autoban', 'automod', 'antialt'
    )),
    source TEXT NOT NULL DEFAULT 'manual' CHECK (source IN (
        'manual', 'automod', 'antialt', 'workflow', 'migration'
    )),
    reason TEXT NOT NULL DEFAULT '',
    duration_seconds INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'resolved', 'expired')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    idempotency_key TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX moderation_cases_guild_subject_idx
    ON moderation_cases (guild_id, subject_user_id, created_at DESC);
CREATE INDEX moderation_cases_guild_moderator_idx
    ON moderation_cases (guild_id, moderator_user_id, created_at DESC);
CREATE INDEX moderation_cases_guild_action_idx
    ON moderation_cases (guild_id, action_type)
    WHERE status = 'active';

CREATE TABLE moderation_case_edits (
    edit_id BIGSERIAL PRIMARY KEY,
    case_id UUID NOT NULL REFERENCES moderation_cases(case_id) ON DELETE CASCADE,
    edited_by BIGINT NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE ticket_panels (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    template_id INTEGER REFERENCES embed_templates(id) ON DELETE SET NULL,
    button_label TEXT NOT NULL DEFAULT 'Open Ticket',
    button_emoji TEXT,
    support_role_id BIGINT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (guild_id, name)
);

CREATE INDEX ticket_panels_guild_id_idx ON ticket_panels (guild_id);

CREATE TABLE tickets (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    thread_id BIGINT NOT NULL UNIQUE,
    panel_id INTEGER REFERENCES ticket_panels(id) ON DELETE SET NULL,
    creator_id BIGINT NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    closed_by BIGINT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    subject TEXT
);

CREATE INDEX tickets_guild_open_idx ON tickets (guild_id, opened_at DESC);
CREATE UNIQUE INDEX tickets_one_open_per_creator_idx
    ON tickets (guild_id, creator_id)
    WHERE status = 'open';


CREATE TABLE role_menus (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT,
    message_id BIGINT,
    name TEXT NOT NULL,
    title TEXT,
    description TEXT,
    template_id INTEGER REFERENCES embed_templates(id) ON DELETE SET NULL,
    type TEXT NOT NULL DEFAULT 'button' CHECK (type IN ('button', 'select')),
    mode TEXT NOT NULL DEFAULT 'multi' CHECK (mode IN ('single', 'multi')),
    max_selections INTEGER CHECK (max_selections IS NULL OR max_selections BETWEEN 1 AND 25),
    required_role_id BIGINT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (guild_id, name)
);

CREATE INDEX role_menus_guild_id_idx ON role_menus (guild_id);

CREATE TABLE role_menu_items (
    menu_id INTEGER NOT NULL REFERENCES role_menus(id) ON DELETE CASCADE,
    role_id BIGINT NOT NULL,
    label TEXT,
    emoji TEXT,
    description TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (menu_id, role_id)
);


CREATE TABLE workflow_definitions (
    id SERIAL PRIMARY KEY,
    definition_id UUID NOT NULL UNIQUE,
    guild_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version >= 1),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    trigger_type TEXT NOT NULL CHECK (trigger_type IN (
        'member_join', 'member_leave', 'message_create', 'message_delete',
        'reaction_add', 'role_update', 'schedule', 'safety_alert',
        'moderation_event', 'ticket_created'
    )),
    trigger_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    conditions JSONB NOT NULL DEFAULT '[]'::jsonb,
    actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (guild_id, name)
);

-- The command surface and runner keep using the compact column names exposed
-- by this view; portable identifiers and revision data remain on the base table.
CREATE VIEW workflows AS
SELECT
    id,
    guild_id,
    name,
    enabled,
    trigger_type,
    trigger_config,
    conditions,
    actions,
    created_at,
    updated_at
FROM workflow_definitions;

CREATE INDEX workflow_definitions_guild_enabled_idx
    ON workflow_definitions (guild_id, enabled, trigger_type)
    WHERE enabled = TRUE;
CREATE INDEX workflow_definitions_schedule_idx
    ON workflow_definitions (enabled, trigger_type)
    WHERE trigger_type = 'schedule' AND enabled = TRUE;

CREATE TABLE workflow_runs (
    run_id UUID PRIMARY KEY,
    workflow_id INTEGER NOT NULL REFERENCES workflow_definitions(id) ON DELETE CASCADE,
    guild_id BIGINT NOT NULL,
    trigger_type TEXT NOT NULL,
    event_key TEXT UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'cancelled', 'skipped')),
    matched_conditions JSONB NOT NULL DEFAULT '[]'::jsonb,
    action_results JSONB NOT NULL DEFAULT '[]'::jsonb,
    error TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX workflow_runs_workflow_idx
    ON workflow_runs (workflow_id, started_at DESC);
CREATE INDEX workflow_runs_guild_idx
    ON workflow_runs (guild_id, started_at DESC);

CREATE TABLE workflow_run_state (
    state_id UUID PRIMARY KEY,
    workflow_id INTEGER NOT NULL REFERENCES workflow_definitions(id) ON DELETE CASCADE,
    guild_id BIGINT NOT NULL,
    scope_key TEXT NOT NULL,
    run_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workflow_id, scope_key)
);

CREATE TABLE scheduled_tasks (
    task_id UUID PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN (
        'unban', 'restore_verification', 'workflow_schedule', 'workflow_cooldown'
    )),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    run_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'done', 'cancelled', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX scheduled_tasks_due_idx
    ON scheduled_tasks (status, run_at)
    WHERE status = 'pending';

CREATE TABLE workflow_dedupe (
    guild_id BIGINT NOT NULL,
    source_message_id BIGINT NOT NULL,
    bot_message_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (guild_id, source_message_id)
);

CREATE VIEW star_info AS
SELECT guild_id, source_message_id AS user_msg_id, bot_message_id AS bot_msg_id
FROM workflow_dedupe;

CREATE TABLE wordlists (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    terms TEXT[] NOT NULL DEFAULT '{}'::TEXT[],
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    updated_by BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (guild_id, name)
);
