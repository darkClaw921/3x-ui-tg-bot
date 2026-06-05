# app/db/engine.py

Движок aiosqlite. init_db применяет schema.sql + _apply_migrations (идемпотентные ALTER TABLE ADD COLUMN в try/except: xui_sub_id, traffic_gb, users.lang TEXT NOT NULL DEFAULT 'ru') + create_table_migrations (subscription_notifications, plan_inbounds + backfill). get_conn (asynccontextmanager, PRAGMA fk+WAL), transaction (BEGIN IMMEDIATE).
