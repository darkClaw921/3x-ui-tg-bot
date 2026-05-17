# app/db/engine.py

Async-engine SQLite поверх aiosqlite. Содержит:

- _SCHEMA_PATH — путь к app/db/schema.sql.
- _resolve_db_path() — возвращает Path из settings.DB_PATH.
- _configure_connection(conn) — применяет PRAGMA foreign_keys=ON, PRAGMA journal_mode=WAL и устанавливает row_factory=aiosqlite.Row. Вызывается на каждом freshly opened connection.
- _apply_migrations(conn) — лёгкие идемпотентные миграции после executescript(schema.sql):
  - ALTER TABLE ... ADD COLUMN с обработкой 'duplicate column'/'already exists' (для subscriptions.xui_sub_id и plans.traffic_gb).
  - CREATE TABLE/INDEX IF NOT EXISTS tuple create_table_migrations — содержит subscription_notifications + idx, plan_inbounds + idx_plan_inbounds_plan (для подъёма уже существующих БД до новой схемы).
  - Backfill plan_inbounds: INSERT OR IGNORE INTO plan_inbounds (plan_id, inbound_id) SELECT id, ? FROM plans WHERE id NOT IN (SELECT plan_id FROM plan_inbounds) с параметром settings.XUI_INBOUND_ID. Условие WHERE id NOT IN (...) гарантирует идемпотентность на уровне отдельного плана — повторный init_db() не перезатирает админский выбор inbounds. Если XUI_INBOUND_ID не задан — backfill пропускается с warning.
- init_db() — создаёт parent dir для DB_PATH, читает schema.sql, выполняет executescript + _apply_migrations + commit. Безопасна для повторных вызовов на каждом старте бота.
- get_conn() async context manager — открывает свежий connection с pragmas. Соединения короткоживущие, по одному на unit of work (нет shared connection между tasks).
- transaction(conn=None) async context manager — оборачивает BEGIN IMMEDIATE / COMMIT / ROLLBACK блок. BEGIN IMMEDIATE захватывает RESERVED lock сразу (аналог SELECT FOR UPDATE), используется в критических секциях вроде try_redeem на promo_redemptions. Если conn передан — reuse, иначе открывает новый.

Зависимости: app.config.settings (DB_PATH, XUI_INBOUND_ID), aiosqlite, loguru.
