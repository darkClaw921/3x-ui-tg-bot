-- ---------------------------------------------------------------------------
-- 3x-ui-tg-bot — SQLite schema
-- ---------------------------------------------------------------------------
-- The schema is fully idempotent: it relies on ``CREATE TABLE IF NOT EXISTS``
-- and ``CREATE INDEX IF NOT EXISTS`` so that ``init_db()`` can re-run safely
-- on every bot start.
--
-- Foreign keys are declared inline. They are only enforced when the connection
-- has ``PRAGMA foreign_keys = ON`` (set by ``app/db/engine.py``).
-- ---------------------------------------------------------------------------

-- Users -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id       INTEGER NOT NULL UNIQUE,
    username    TEXT,
    first_name  TEXT,
    is_admin    INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_tg_id ON users(tg_id);

-- Plans (tariffs) -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS plans (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    days         INTEGER NOT NULL CHECK (days > 0),
    price_stars  INTEGER NOT NULL CHECK (price_stars >= 0),
    traffic_gb   INTEGER NOT NULL DEFAULT 0 CHECK (traffic_gb >= 0),
    is_active    INTEGER NOT NULL DEFAULT 1,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Promos ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS promos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    type        TEXT NOT NULL CHECK (type IN ('percent', 'flat_stars', 'free_days')),
    value       INTEGER NOT NULL,
    max_uses    INTEGER NOT NULL DEFAULT 0,
    used_count  INTEGER NOT NULL DEFAULT 0,
    expires_at  TIMESTAMP NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by  INTEGER NULL REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_promos_code ON promos(code);

-- Subscriptions --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS subscriptions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    xui_inbound_id    INTEGER NOT NULL,
    xui_client_uuid   TEXT NOT NULL,
    xui_client_email  TEXT NOT NULL,
    xui_sub_id        TEXT NOT NULL DEFAULT '',
    expires_at        TIMESTAMP NOT NULL,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    plan_id           INTEGER NULL REFERENCES plans(id) ON DELETE SET NULL,
    status            TEXT NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active', 'expired', 'revoked'))
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_status ON subscriptions(user_id, status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_expires_at ON subscriptions(expires_at);

-- Promo redemptions ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS promo_redemptions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    promo_id        INTEGER NOT NULL REFERENCES promos(id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subscription_id INTEGER NULL REFERENCES subscriptions(id) ON DELETE SET NULL,
    redeemed_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_promo_redemptions_promo_id ON promo_redemptions(promo_id);
CREATE INDEX IF NOT EXISTS idx_promo_redemptions_user_id ON promo_redemptions(user_id);

-- Payments -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS payments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subscription_id     INTEGER NULL REFERENCES subscriptions(id) ON DELETE SET NULL,
    telegram_charge_id  TEXT NOT NULL UNIQUE,
    stars_amount        INTEGER NOT NULL,
    plan_id             INTEGER NULL REFERENCES plans(id) ON DELETE SET NULL,
    promo_id            INTEGER NULL REFERENCES promos(id) ON DELETE SET NULL,
    status              TEXT NOT NULL DEFAULT 'paid'
                            CHECK (status IN ('paid', 'refunded')),
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_telegram_charge_id ON payments(telegram_charge_id);

-- Traffic snapshots ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS traffic_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    up              INTEGER NOT NULL DEFAULT 0,
    down            INTEGER NOT NULL DEFAULT 0,
    taken_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_traffic_snapshots_sub_taken_at
    ON traffic_snapshots(subscription_id, taken_at);

-- Subscription notifications -------------------------------------------------
-- Deduplication ledger for the scheduler's reminder + expiry notification jobs.
-- ``kind`` encodes how-many-days-before-expiry the message belongs to
-- ('3d', '1d', '0d') or 'expired' for the post-expiry final message.
-- The UNIQUE (subscription_id, kind) constraint guarantees each user receives
-- a given reminder at most once per subscription.
CREATE TABLE IF NOT EXISTS subscription_notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL
                        CHECK (kind IN ('3d', '1d', '0d', 'expired')),
    sent_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (subscription_id, kind)
);

CREATE INDEX IF NOT EXISTS idx_subscription_notifications_sub
    ON subscription_notifications(subscription_id);
