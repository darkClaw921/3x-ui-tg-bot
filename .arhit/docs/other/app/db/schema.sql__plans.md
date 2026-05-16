# app/db/schema.sql::plans

Tariff plans table (CREATE TABLE IF NOT EXISTS plans).

Columns:
- id INTEGER PRIMARY KEY AUTOINCREMENT
- title TEXT NOT NULL — tariff name shown to users
- days INTEGER NOT NULL CHECK (days > 0) — subscription duration
- price_stars INTEGER NOT NULL CHECK (price_stars >= 0) — price in Telegram Stars
- traffic_gb INTEGER NOT NULL DEFAULT 0 CHECK (traffic_gb >= 0) — per-client traffic limit in GB forwarded to 3x-ui as totalGB; 0 means unlimited
- is_active INTEGER NOT NULL DEFAULT 1 — soft-delete flag
- created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

Referenced by subscriptions.plan_id and payments.plan_id (both ON DELETE SET NULL). Soft-deleted via UPDATE is_active=0; never hard-deleted while history exists.
