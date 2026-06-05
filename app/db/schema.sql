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
-- ``is_blocked`` (0/1) flags a user banned by an admin. A blocked user is
-- short-circuited by :class:`app.middlewares.blocked.BlockedUserMiddleware`
-- before any handler runs (admins are never blocked). Toggled from the admin
-- user card («🚫 Заблокировать / 🟢 Разблокировать»).
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id       INTEGER NOT NULL UNIQUE,
    username    TEXT,
    first_name  TEXT,
    is_admin    INTEGER NOT NULL DEFAULT 0,
    lang        TEXT NOT NULL DEFAULT 'ru',
    is_blocked  INTEGER NOT NULL DEFAULT 0,
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

-- Plan inbounds (many-to-many between plans and 3x-ui inbound ids) ----------
-- ``inbound_id`` holds the panel's inbound primary key (numeric id from 3x-ui),
-- NOT a local row reference, hence no FK on it. A single plan can be served
-- by one or more inbounds; ``ON DELETE CASCADE`` keeps the table consistent
-- whenever a plan is hard-deleted.
CREATE TABLE IF NOT EXISTS plan_inbounds (
    plan_id    INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    inbound_id INTEGER NOT NULL,
    PRIMARY KEY (plan_id, inbound_id)
);

CREATE INDEX IF NOT EXISTS idx_plan_inbounds_plan ON plan_inbounds(plan_id);

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
                          CHECK (status IN ('active', 'expired', 'revoked')),
    is_trial          INTEGER NOT NULL DEFAULT 0,
    -- ``auto_renew`` enrols the subscription in automatic renewal (1) — driven
    -- either by a native Telegram Star subscription (``tg_sub_charge_id`` set)
    -- or the wallet fallback (``tg_sub_charge_id`` NULL → the scheduler charges
    -- the user's Stars balance). ``tg_sub_charge_id`` holds the recurring
    -- payment's ``telegram_payment_charge_id`` needed by
    -- ``bot.edit_user_star_subscription`` to cancel / re-enable the native
    -- subscription.
    auto_renew        INTEGER NOT NULL DEFAULT 0,
    tg_sub_charge_id  TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_status ON subscriptions(user_id, status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_expires_at ON subscriptions(expires_at);

-- Partial-unique index: race-proof "one trial per user". Only ``is_trial=1``
-- rows are constrained, so a user holds at most one trial subscription while
-- their regular/paid subscriptions remain unconstrained.
CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_one_trial
    ON subscriptions(user_id) WHERE is_trial = 1;

-- Index over ``tg_sub_charge_id`` — accelerates the recurring-charge lookup
-- (``get_active_auto_renew_for``) and the wallet-fallback due scan
-- (``list_auto_renew_due``, which filters ``tg_sub_charge_id IS NULL``).
CREATE INDEX IF NOT EXISTS idx_subscriptions_tg_sub_charge
    ON subscriptions(tg_sub_charge_id);

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
-- ('3d', '1d', '0d'), 'expired' for the post-expiry final message, or
-- 'traffic80' for the one-off "80% of traffic quota used" alert (Phase 4).
--
-- ``kind`` is intentionally free-text (no CHECK constraint) so new notification
-- kinds can be added in code without a destructive table rebuild on existing
-- databases — validation lives in
-- :func:`app.db.repos.subscriptions.try_mark_notification_sent`
-- (:data:`app.db.repos.subscriptions.NOTIFICATION_KINDS`). The UNIQUE
-- (subscription_id, kind) constraint guarantees each user receives a given
-- notification at most once per subscription.
CREATE TABLE IF NOT EXISTS subscription_notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL,
    sent_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (subscription_id, kind)
);

CREATE INDEX IF NOT EXISTS idx_subscription_notifications_sub
    ON subscription_notifications(subscription_id);

-- Wallet transactions --------------------------------------------------------
-- Append-only ledger of every Stars movement on a user's in-bot balance. The
-- current balance is never stored as a column — it is always recomputed as
-- ``COALESCE(SUM(amount), 0)`` over this table, so the ledger is the single
-- source of truth and can never drift out of sync.
--
-- ``amount`` is a *signed* integer: credits (topup / refund / referral_bonus /
-- admin_grant) are positive, debits (spend / payment) are negative.
--
-- ``ref`` is an optional deterministic idempotency token (e.g.
-- ``topup:<charge_id>`` or ``buy:<...>``). The partial-unique index
-- ``idx_wallet_ref`` enforces global uniqueness for non-NULL refs only, so the
-- same logical event can be inserted at most once (replay / double-credit /
-- double-spend protection) while rows that intentionally have no ref are not
-- constrained.
CREATE TABLE IF NOT EXISTS wallet_transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type        TEXT NOT NULL
                    CHECK (type IN ('topup', 'spend', 'refund',
                                    'referral_bonus', 'admin_grant', 'payment')),
    amount      INTEGER NOT NULL,
    ref         TEXT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_wallet_transactions_user
    ON wallet_transactions(user_id);

-- Partial-unique index: global idempotency by deterministic ref. Only non-NULL
-- refs are constrained, so multiple ref-less rows (rare, but allowed) coexist.
CREATE UNIQUE INDEX IF NOT EXISTS idx_wallet_ref
    ON wallet_transactions(ref) WHERE ref IS NOT NULL;

-- Referrals -------------------------------------------------------------------
-- One row per *referred* user (``referred_id`` is UNIQUE), recording who
-- invited them. ``status`` starts at 'pending' when the link is followed and
-- flips to 'rewarded' exactly once, after the referred user's first payment,
-- by :func:`app.db.repos.referrals.try_mark_rewarded` (an atomic UPDATE WHERE
-- status='pending'). The UNIQUE(referred_id) constraint plus that guarded
-- UPDATE guarantee the referrer bonus is paid at most once per referred user.
CREATE TABLE IF NOT EXISTS referrals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    referred_id  INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    status       TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'rewarded')),
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    rewarded_at  TIMESTAMP NULL
);

CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id);

-- Gift codes ------------------------------------------------------------------
-- A purchasable subscription a buyer pays for but does NOT redeem themselves —
-- instead a unique ``code`` is minted and handed to a recipient who activates
-- it later. ``status`` starts 'active' when minted (after the buyer's payment
-- is recorded), flips to 'redeemed' exactly once via
-- :func:`app.db.repos.gift_codes.try_redeem` (atomic UPDATE WHERE status='active'
-- under BEGIN IMMEDIATE), or to 'refunded' if the purchase is reversed.
-- ``plan_id`` / ``payment_id`` / ``subscription_id`` / ``redeemed_by`` are
-- nullable FKs that become SET NULL on delete so a gift's audit trail survives
-- the deletion of the referenced plan / payment / subscription / user.
CREATE TABLE IF NOT EXISTS gift_codes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL UNIQUE,
    plan_id         INTEGER NULL REFERENCES plans(id) ON DELETE SET NULL,
    inbound_id      INTEGER NOT NULL,
    buyer_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    payment_id      INTEGER NULL REFERENCES payments(id) ON DELETE SET NULL,
    status          TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'redeemed', 'refunded')),
    redeemed_by     INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
    subscription_id INTEGER NULL REFERENCES subscriptions(id) ON DELETE SET NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    redeemed_at     TIMESTAMP NULL
);

CREATE INDEX IF NOT EXISTS idx_gift_codes_code ON gift_codes(code);
CREATE INDEX IF NOT EXISTS idx_gift_codes_buyer ON gift_codes(buyer_id);

-- Support tickets -------------------------------------------------------------
-- A two-way conversation between a user and the admins, relayed through the bot.
-- One row per ticket; ``status`` walks 'open' (user wrote, awaiting an admin) →
-- 'answered' (admin replied, awaiting the user) → 'closed' (resolved, terminal).
-- ``updated_at`` is bumped on every status change / new message so the open list
-- can be sorted by recency. The transcript lives in ``ticket_messages``.
CREATE TABLE IF NOT EXISTS tickets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'answered', 'closed')),
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets(user_id);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);

-- Ticket messages -------------------------------------------------------------
-- Append-only transcript of a ticket. ``sender`` is 'user' or 'admin'; ``text``
-- is the message body; ``tg_message_id`` optionally records the Telegram
-- message id the text was relayed from (best-effort audit, nullable).
CREATE TABLE IF NOT EXISTS ticket_messages (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id      INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    sender         TEXT NOT NULL CHECK (sender IN ('user', 'admin')),
    text           TEXT NOT NULL,
    tg_message_id  INTEGER NULL,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ticket_messages_ticket
    ON ticket_messages(ticket_id);

-- Audit log -------------------------------------------------------------------
-- Append-only trail of privileged admin actions (plan / promo CRUD, user
-- revoke / toggle_admin / grant_sub / block, broadcast). ``action`` is a short
-- verb (e.g. 'plan.create', 'user.block'); ``target_type`` / ``target_id``
-- identify the affected entity; ``details`` is an optional JSON blob with extra
-- context. ``admin_id`` references the acting admin's ``users.id`` (SET NULL on
-- delete so the trail survives the admin's account removal).
CREATE TABLE IF NOT EXISTS audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id     INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
    action       TEXT NOT NULL,
    target_type  TEXT NULL,
    target_id    INTEGER NULL,
    details      TEXT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_admin ON audit_log(admin_id);

-- Health status ----------------------------------------------------------------
-- Last-known reachability of the 3x-ui panel. A single logical row (one per
-- ``component``, currently only 'xui') stores the current ``status`` ('up' |
-- 'down'), the most recent failure reason in ``last_error`` and ``changed_at``
-- marking the moment the state last *flipped*. The scheduler's health-check job
-- persists this so it can alert admins ONLY on an up↔down transition rather than
-- on every probe.
CREATE TABLE IF NOT EXISTS health_status (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    component   TEXT NOT NULL UNIQUE DEFAULT 'xui',
    status      TEXT NOT NULL CHECK (status IN ('up', 'down')),
    last_error  TEXT NULL,
    changed_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
