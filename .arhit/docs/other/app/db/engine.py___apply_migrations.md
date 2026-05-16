# app/db/engine.py::_apply_migrations

Apply lightweight idempotent column additions on top of schema.sql.

SQLite cannot express ADD COLUMN IF NOT EXISTS, so each migration is wrapped in a try/except that swallows the 'duplicate column' / 'already exists' OperationalError.

Current ALTER migrations:
- subscriptions.xui_sub_id TEXT NOT NULL DEFAULT '' — for the panel subId used by /sub/<sub_id>.
- plans.traffic_gb INTEGER NOT NULL DEFAULT 0 — per-client traffic limit (GB) forwarded to 3x-ui as totalGB; existing rows default to 0 (no limit).

Additionally creates the subscription_notifications table and its index via CREATE TABLE/INDEX IF NOT EXISTS for databases initialised before those were shipped in schema.sql.
