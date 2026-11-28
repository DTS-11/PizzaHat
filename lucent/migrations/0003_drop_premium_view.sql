-- The compatibility view from 0001 is no longer needed: all readers query
-- subscriptions directly. Drop it so the schema has a single billing object.
DROP VIEW IF EXISTS premium;
