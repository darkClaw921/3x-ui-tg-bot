# app/db/schema.sql

SQLite-схема всех таблиц бота, идемпотентна (CREATE TABLE/INDEX IF NOT EXISTS). Применяется через executescript в app/db/engine.py::init_db на каждом старте.

Таблицы:
- users (id, tg_id UNIQUE, username, first_name, is_admin, created_at) + idx_users_tg_id — пользователи Telegram.
- plans (id, title, days>0, price_stars≥0, traffic_gb≥0 default 0, is_active default 1, created_at) — тарифы. Soft-delete через is_active=0.
- plan_inbounds (plan_id REFERENCES plans(id) ON DELETE CASCADE, inbound_id, PRIMARY KEY (plan_id, inbound_id)) + idx_plan_inbounds_plan — many-to-many между тарифами и inbound id из 3x-ui панели. inbound_id хранится без FK (это id из 3x-ui, не локальная запись). CASCADE гарантирует консистентность при удалении тарифа.
- promos (id, code UNIQUE, type IN ('percent','flat_stars','free_days'), value, max_uses default 0, used_count default 0, expires_at NULL, created_at, created_by REFERENCES users ON DELETE SET NULL) + idx_promos_code — промокоды.
- subscriptions (id, user_id REFERENCES users ON DELETE CASCADE, xui_inbound_id, xui_client_uuid, xui_client_email, xui_sub_id default '', expires_at, created_at, plan_id REFERENCES plans ON DELETE SET NULL, status IN ('active','expired','revoked') default 'active') + 3 индекса (user_id, user+status, expires_at) — подписки пользователей.
- promo_redemptions (id, promo_id REFERENCES promos ON DELETE CASCADE, user_id REFERENCES users ON DELETE CASCADE, subscription_id REFERENCES subscriptions ON DELETE SET NULL, redeemed_at) + 2 индекса — история использования промокодов.
- payments (id, user_id, subscription_id, telegram_charge_id UNIQUE, stars_amount, plan_id, promo_id, status IN ('paid','refunded') default 'paid', created_at) + 2 индекса — платежи Telegram Stars.
- traffic_snapshots (id, subscription_id REFERENCES subscriptions ON DELETE CASCADE, up default 0, down default 0, taken_at) + индекс (subscription_id, taken_at) — снимки трафика.
- subscription_notifications (id, subscription_id REFERENCES subscriptions ON DELETE CASCADE, kind IN ('3d','1d','0d','expired'), sent_at, UNIQUE (subscription_id, kind)) + индекс — дедуп-журнал уведомлений шедулера.

FK включаются на уровне connection через PRAGMA foreign_keys=ON (см. app/db/engine.py::_configure_connection).
