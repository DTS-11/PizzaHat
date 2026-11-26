-- Remove legacy tables that survived 0001 because no replacement table or view
-- shares their name. None are referenced by the Discord engine; their data is
-- not migrated by design.

DO $zync_drop_orphans$
DECLARE
    object_name TEXT;
    object_kind "char";
BEGIN
    FOREACH object_name IN ARRAY ARRAY[
        'afk', 'auto_responders', 'guild_themes', 'join_automation',
        'prefix', 'scheduled_messages', 'star_config', 'event_actions'
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
$zync_drop_orphans$;
