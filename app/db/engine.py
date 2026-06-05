"""aiosqlite database engine and lifecycle helpers.

The bot uses a single SQLite file at :data:`app.config.settings.DB_PATH`.
Connections are short-lived: every unit of work opens its own connection via
:func:`get_conn` (an :func:`contextlib.asynccontextmanager`). This keeps the
code simple, avoids cross-task connection sharing, and matches aiosqlite's
recommended usage.

At startup :func:`init_db` ensures the parent directory exists and applies
``app/db/schema.sql`` (idempotent: every statement uses
``CREATE … IF NOT EXISTS``).

Two pragmas are enforced on every connection:

* ``PRAGMA foreign_keys = ON`` — SQLite ships with FK enforcement OFF; we must
  re-enable it on every new connection (the pragma is per-connection).
* ``PRAGMA journal_mode = WAL`` — better concurrency for our read-heavy
  workload (the bot reads constantly to render menus and writes during
  payments and admin actions).

The :func:`transaction` context manager wraps a ``BEGIN IMMEDIATE`` /
``COMMIT`` / ``ROLLBACK`` block — used for critical sections like promo
redemption where we need a serializable write lock to prevent races on
``used_count``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from loguru import logger

from app.config import settings

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _resolve_db_path() -> Path:
    """Return the configured DB path as a :class:`Path` (not yet created)."""
    return Path(settings.DB_PATH)


async def _configure_connection(conn: aiosqlite.Connection) -> None:
    """Apply per-connection pragmas and row factory.

    Must be called on every freshly opened connection — SQLite pragmas like
    ``foreign_keys`` are NOT persisted across connections.
    """
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON;")
    await conn.execute("PRAGMA journal_mode = WAL;")


async def _relax_subscription_notifications_kind(
    conn: aiosqlite.Connection,
) -> None:
    """Drop the legacy ``CHECK (kind IN (...))`` on ``subscription_notifications``.

    Phase 4 adds new notification kinds (e.g. ``'traffic80'``) on top of the
    historical ``'3d' / '1d' / '0d' / 'expired'`` set. Older databases were
    created with a ``CHECK`` constraint that hard-codes the old four kinds, and
    SQLite cannot drop a column constraint via ``ALTER TABLE``. Rather than a
    destructive rebuild on every boot, this migration is **conditional and
    data-preserving**:

    * It inspects ``sqlite_master.sql`` for the table. If the DDL no longer
      contains a ``CHECK`` clause (fresh installs, or already-migrated DBs) it
      is a **no-op** — so the migration is idempotent.
    * If a ``CHECK`` is present it rebuilds the table without it inside a single
      transaction, copying every existing row across, then swaps the new table
      in. Row ids and the ``UNIQUE (subscription_id, kind)`` dedup semantics are
      preserved.

    Validation of allowed kinds now lives in code
    (:func:`app.db.repos.subscriptions.try_mark_notification_sent`), so the
    column is intentionally free-text at the DB level.
    """
    cursor = await conn.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type = 'table' AND name = 'subscription_notifications'"
    )
    row = await cursor.fetchone()
    if row is None:
        return  # table not created yet — nothing to relax
    ddl = row["sql"] or ""
    if "CHECK" not in ddl.upper():
        return  # already free-text (fresh install or previously migrated)

    logger.info(
        "migration: relaxing subscription_notifications.kind CHECK constraint "
        "(data-preserving rebuild)"
    )
    # FK enforcement must be off during a table swap or the rename/drop dance
    # trips the self-referencing FKs. We restore it afterwards.
    await conn.execute("PRAGMA foreign_keys = OFF")
    try:
        await conn.execute("BEGIN")
        await conn.execute(
            """
            CREATE TABLE subscription_notifications_new (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_id INTEGER NOT NULL
                                    REFERENCES subscriptions(id) ON DELETE CASCADE,
                kind            TEXT NOT NULL,
                sent_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (subscription_id, kind)
            )
            """
        )
        await conn.execute(
            "INSERT INTO subscription_notifications_new "
            "(id, subscription_id, kind, sent_at) "
            "SELECT id, subscription_id, kind, sent_at "
            "FROM subscription_notifications"
        )
        await conn.execute("DROP TABLE subscription_notifications")
        await conn.execute(
            "ALTER TABLE subscription_notifications_new "
            "RENAME TO subscription_notifications"
        )
        # The index is dropped together with the old table — recreate it.
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_subscription_notifications_sub "
            "ON subscription_notifications(subscription_id)"
        )
        await conn.commit()
    except BaseException:
        await conn.rollback()
        raise
    finally:
        await conn.execute("PRAGMA foreign_keys = ON")


async def _apply_migrations(conn: aiosqlite.Connection) -> None:
    """Apply lightweight, idempotent column additions on top of ``schema.sql``.

    SQLite cannot express ``ADD COLUMN IF NOT EXISTS``, so each migration
    is wrapped in a try/except that swallows the "duplicate column" error.
    Used for non-breaking additions to existing tables where dropping the
    DB during development would be inconvenient.
    """
    migrations = (
        # Subscriptions: ``xui_sub_id`` stores the panel's ``subId`` used by
        # the public subscription URL (``/sub/<sub_id>``). Older databases
        # created before this column existed must be upgraded in-place.
        "ALTER TABLE subscriptions ADD COLUMN xui_sub_id TEXT NOT NULL DEFAULT ''",
        # Plans: ``traffic_gb`` declares the per-client traffic limit (GB) that
        # the bot forwards to the 3x-ui panel as ``totalGB``. 0 means unlimited
        # (matches xui semantics). Older databases created before this column
        # existed must be upgraded in-place; existing plans default to 0 (no
        # limit) for backwards-compatible behaviour.
        "ALTER TABLE plans ADD COLUMN traffic_gb INTEGER NOT NULL DEFAULT 0",
        # Users: ``lang`` stores the user's preferred UI language (one of
        # ``app.i18n.SUPPORTED_LANGS``). New users get a value resolved from
        # their Telegram ``language_code`` at registration; existing rows on an
        # upgraded DB default to ``'ru'`` (the historical single language) so no
        # backfill is required and the UI stays unchanged for them.
        "ALTER TABLE users ADD COLUMN lang TEXT NOT NULL DEFAULT 'ru'",
        # Subscriptions: ``is_trial`` flags a free trial subscription (1) vs a
        # regular/paid one (0). Used to enforce the "one trial per user" rule
        # (see ``idx_subscriptions_one_trial`` below) and to hide the trial
        # button once a user has already claimed theirs. Existing rows on an
        # upgraded DB default to 0 (non-trial) so the migration is non-breaking.
        "ALTER TABLE subscriptions ADD COLUMN is_trial INTEGER NOT NULL DEFAULT 0",
        # Subscriptions: ``auto_renew`` flags a subscription enrolled in
        # automatic renewal (1) vs a one-off purchase (0). It drives both
        # auto-renewal mechanisms — native Telegram Star subscriptions (paired
        # with a non-NULL ``tg_sub_charge_id`` below) and the wallet fallback
        # (``tg_sub_charge_id`` stays NULL and the scheduler charges the user's
        # Stars balance). Existing rows on an upgraded DB default to 0 so the
        # migration is non-breaking.
        "ALTER TABLE subscriptions ADD COLUMN auto_renew INTEGER NOT NULL DEFAULT 0",
        # Subscriptions: ``tg_sub_charge_id`` stores the recurring Telegram Star
        # subscription's ``telegram_payment_charge_id``. It is required by
        # ``bot.edit_user_star_subscription`` to cancel / re-enable a native
        # subscription and distinguishes native Star subscriptions (non-NULL)
        # from the wallet fallback (NULL) in ``list_auto_renew_due``. Nullable;
        # existing / non-recurring rows keep NULL.
        "ALTER TABLE subscriptions ADD COLUMN tg_sub_charge_id TEXT",
        # Users: ``is_blocked`` (0/1) flags a user banned by an admin. A blocked
        # user is rejected by ``BlockedUserMiddleware`` before any handler runs.
        # Existing rows on an upgraded DB default to 0 (not blocked) so the
        # migration is non-breaking.
        "ALTER TABLE users ADD COLUMN is_blocked INTEGER NOT NULL DEFAULT 0",
    )
    for stmt in migrations:
        try:
            await conn.execute(stmt)
        except aiosqlite.OperationalError as exc:
            msg = str(exc).lower()
            if "duplicate column" in msg or "already exists" in msg:
                continue
            raise

    # ``CREATE TABLE IF NOT EXISTS`` migrations — used for tables added after
    # the initial schema was shipped. These are also present in ``schema.sql``
    # so fresh installs do not need them, but applying them here ensures
    # already-running databases pick up new tables without manual SQL.
    create_table_migrations = (
        (
            "subscription_notifications",
            """
            CREATE TABLE IF NOT EXISTS subscription_notifications (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_id INTEGER NOT NULL
                                    REFERENCES subscriptions(id) ON DELETE CASCADE,
                kind            TEXT NOT NULL,
                sent_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (subscription_id, kind)
            )
            """,
        ),
        (
            "idx_subscription_notifications_sub",
            "CREATE INDEX IF NOT EXISTS idx_subscription_notifications_sub "
            "ON subscription_notifications(subscription_id)",
        ),
        # ``plan_inbounds`` — many-to-many between ``plans`` and 3x-ui inbound ids.
        # Required for the multi-inbound feature where one plan can be served by
        # several inbounds (e.g. Germany + Netherlands). Inbound id is the panel's
        # primary key, not a local row, so it has no FK.
        (
            "plan_inbounds",
            """
            CREATE TABLE IF NOT EXISTS plan_inbounds (
                plan_id    INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
                inbound_id INTEGER NOT NULL,
                PRIMARY KEY (plan_id, inbound_id)
            )
            """,
        ),
        (
            "idx_plan_inbounds_plan",
            "CREATE INDEX IF NOT EXISTS idx_plan_inbounds_plan "
            "ON plan_inbounds(plan_id)",
        ),
        # ``wallet_transactions`` — append-only Stars-balance ledger. Balance is
        # never stored; it is always recomputed as ``SUM(amount)`` over this
        # table. ``amount`` is signed (credits positive, debits negative). See
        # ``schema.sql`` for the full column-level documentation.
        (
            "wallet_transactions",
            """
            CREATE TABLE IF NOT EXISTS wallet_transactions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL
                                REFERENCES users(id) ON DELETE CASCADE,
                type        TEXT NOT NULL
                                CHECK (type IN ('topup', 'spend', 'refund',
                                                'referral_bonus', 'admin_grant',
                                                'payment')),
                amount      INTEGER NOT NULL,
                ref         TEXT NULL,
                created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ),
        (
            "idx_wallet_transactions_user",
            "CREATE INDEX IF NOT EXISTS idx_wallet_transactions_user "
            "ON wallet_transactions(user_id)",
        ),
        # Partial-unique index — global idempotency by deterministic ``ref``.
        # Only non-NULL refs are constrained, so a duplicate ``ref`` is rejected
        # by the DB while ref-less rows stay unconstrained.
        (
            "idx_wallet_ref",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_wallet_ref "
            "ON wallet_transactions(ref) WHERE ref IS NOT NULL",
        ),
        # Partial-unique index — race-proof "one trial per user". Only rows
        # with ``is_trial=1`` are constrained, so a user can hold at most one
        # trial subscription while their regular/paid subscriptions stay
        # unconstrained. Two concurrent ``activate_trial`` calls for the same
        # user cannot both insert a trial row: the second hits an
        # IntegrityError (mapped to "trial already used" at the service layer).
        (
            "idx_subscriptions_one_trial",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_one_trial "
            "ON subscriptions(user_id) WHERE is_trial = 1",
        ),
        # Index over ``tg_sub_charge_id`` — speeds up the recurring-charge
        # lookup (``get_active_auto_renew_for``) and the wallet-fallback due
        # scan (``list_auto_renew_due``, which filters ``tg_sub_charge_id IS
        # NULL``). Created after the ALTER above adds the column.
        (
            "idx_subscriptions_tg_sub_charge",
            "CREATE INDEX IF NOT EXISTS idx_subscriptions_tg_sub_charge "
            "ON subscriptions(tg_sub_charge_id)",
        ),
        # ``referrals`` — one row per referred user (``referred_id`` UNIQUE),
        # recording who invited them and whether the referral bonus has been
        # paid. See ``schema.sql`` for the full column documentation.
        (
            "referrals",
            """
            CREATE TABLE IF NOT EXISTS referrals (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id  INTEGER NOT NULL
                                 REFERENCES users(id) ON DELETE CASCADE,
                referred_id  INTEGER NOT NULL UNIQUE
                                 REFERENCES users(id) ON DELETE CASCADE,
                status       TEXT NOT NULL DEFAULT 'pending'
                                 CHECK (status IN ('pending', 'rewarded')),
                created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                rewarded_at  TIMESTAMP NULL
            )
            """,
        ),
        (
            "idx_referrals_referrer",
            "CREATE INDEX IF NOT EXISTS idx_referrals_referrer "
            "ON referrals(referrer_id)",
        ),
        # ``gift_codes`` — purchasable subscription codes a buyer pays for but
        # a recipient redeems. See ``schema.sql`` for full column docs.
        (
            "gift_codes",
            """
            CREATE TABLE IF NOT EXISTS gift_codes (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                code            TEXT NOT NULL UNIQUE,
                plan_id         INTEGER NULL REFERENCES plans(id) ON DELETE SET NULL,
                inbound_id      INTEGER NOT NULL,
                buyer_id        INTEGER NOT NULL
                                    REFERENCES users(id) ON DELETE CASCADE,
                payment_id      INTEGER NULL
                                    REFERENCES payments(id) ON DELETE SET NULL,
                status          TEXT NOT NULL DEFAULT 'active'
                                    CHECK (status IN ('active', 'redeemed', 'refunded')),
                redeemed_by     INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
                subscription_id INTEGER NULL
                                    REFERENCES subscriptions(id) ON DELETE SET NULL,
                created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                redeemed_at     TIMESTAMP NULL
            )
            """,
        ),
        (
            "idx_gift_codes_code",
            "CREATE INDEX IF NOT EXISTS idx_gift_codes_code ON gift_codes(code)",
        ),
        (
            "idx_gift_codes_buyer",
            "CREATE INDEX IF NOT EXISTS idx_gift_codes_buyer "
            "ON gift_codes(buyer_id)",
        ),
        # ``tickets`` — one row per support conversation. ``status`` walks
        # 'open' → 'answered' → 'closed'. See ``schema.sql`` for full docs.
        (
            "tickets",
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL
                                REFERENCES users(id) ON DELETE CASCADE,
                status      TEXT NOT NULL DEFAULT 'open'
                                CHECK (status IN ('open', 'answered', 'closed')),
                created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ),
        (
            "idx_tickets_user",
            "CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets(user_id)",
        ),
        (
            "idx_tickets_status",
            "CREATE INDEX IF NOT EXISTS idx_tickets_status "
            "ON tickets(status)",
        ),
        # ``ticket_messages`` — append-only transcript of a ticket. ``sender`` is
        # 'user' or 'admin'. See ``schema.sql`` for full docs.
        (
            "ticket_messages",
            """
            CREATE TABLE IF NOT EXISTS ticket_messages (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id      INTEGER NOT NULL
                                   REFERENCES tickets(id) ON DELETE CASCADE,
                sender         TEXT NOT NULL
                                   CHECK (sender IN ('user', 'admin')),
                text           TEXT NOT NULL,
                tg_message_id  INTEGER NULL,
                created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ),
        (
            "idx_ticket_messages_ticket",
            "CREATE INDEX IF NOT EXISTS idx_ticket_messages_ticket "
            "ON ticket_messages(ticket_id)",
        ),
        # ``audit_log`` — append-only trail of privileged admin actions. See
        # ``schema.sql`` for full column documentation.
        (
            "audit_log",
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id     INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
                action       TEXT NOT NULL,
                target_type  TEXT NULL,
                target_id    INTEGER NULL,
                details      TEXT NULL,
                created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ),
        (
            "idx_audit_log_created",
            "CREATE INDEX IF NOT EXISTS idx_audit_log_created "
            "ON audit_log(created_at)",
        ),
        (
            "idx_audit_log_admin",
            "CREATE INDEX IF NOT EXISTS idx_audit_log_admin "
            "ON audit_log(admin_id)",
        ),
        # ``health_status`` — last-known reachability of the 3x-ui panel. A
        # single logical row holds the current state ('up' | 'down'),
        # ``last_error`` for the most recent failure reason and ``changed_at``
        # marking when the state last *flipped* (not every probe). The
        # health-check job reads/writes this row to decide whether to alert
        # admins — it only notifies on an up↔down transition, so the previous
        # state must be persisted across job runs. See ``schema.sql``.
        (
            "health_status",
            """
            CREATE TABLE IF NOT EXISTS health_status (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                component   TEXT NOT NULL UNIQUE DEFAULT 'xui',
                status      TEXT NOT NULL CHECK (status IN ('up', 'down')),
                last_error  TEXT NULL,
                changed_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ),
    )
    for name, stmt in create_table_migrations:
        try:
            await conn.execute(stmt)
        except aiosqlite.OperationalError as exc:
            logger.warning("migration {} failed: {}", name, exc)
            raise

    await _relax_subscription_notifications_kind(conn)

    # Backfill ``plan_inbounds`` for legacy plans that have no rows yet.
    # On an old DB (created before the multi-inbound feature) every existing
    # plan was implicitly served by ``settings.XUI_INBOUND_ID``. We INSERT one
    # row per such plan so the new code can rely on every active plan having
    # at least one inbound. The condition ``plan.id NOT IN (SELECT plan_id ...)``
    # makes this idempotent at the per-plan level — admins can freely customise
    # plan_inbounds afterwards without `init_db()` resetting their choice on
    # subsequent boots. If ``XUI_INBOUND_ID`` is missing or zero we skip the
    # backfill with a warning rather than failing — the install is misconfigured
    # but the migration itself must not crash startup.
    default_inbound_id = getattr(settings, "XUI_INBOUND_ID", None)
    if default_inbound_id:
        await conn.execute(
            "INSERT OR IGNORE INTO plan_inbounds (plan_id, inbound_id) "
            "SELECT id, ? FROM plans "
            "WHERE id NOT IN (SELECT plan_id FROM plan_inbounds)",
            (default_inbound_id,),
        )
    else:
        logger.warning(
            "plan_inbounds backfill skipped: settings.XUI_INBOUND_ID is not set"
        )


async def init_db() -> None:
    """Create the DB file (and parent directory) if missing and apply schema.

    Safe to call on every bot start; ``schema.sql`` is fully idempotent.
    Also runs ``_apply_migrations`` for columns added after the initial
    schema was shipped (no-op on fresh databases).
    """
    db_path = _resolve_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")

    logger.info(f"Initializing SQLite DB at {db_path}")
    async with aiosqlite.connect(db_path) as conn:
        await _configure_connection(conn)
        await conn.executescript(schema_sql)
        await _apply_migrations(conn)
        await conn.commit()
    logger.info("DB schema ready.")


@asynccontextmanager
async def get_conn() -> AsyncIterator[aiosqlite.Connection]:
    """Yield a configured :class:`aiosqlite.Connection`.

    Usage::

        async with get_conn() as conn:
            row = await (await conn.execute("SELECT 1")).fetchone()

    The connection is closed automatically on exit. Callers are responsible
    for committing their writes (or using :func:`transaction`).
    """
    db_path = _resolve_db_path()
    async with aiosqlite.connect(db_path) as conn:
        await _configure_connection(conn)
        yield conn


@asynccontextmanager
async def transaction(
    conn: aiosqlite.Connection | None = None,
) -> AsyncIterator[aiosqlite.Connection]:
    """Async context manager wrapping a ``BEGIN IMMEDIATE`` block.

    ``BEGIN IMMEDIATE`` acquires a RESERVED lock immediately, preventing other
    writers from racing — this is the SQLite equivalent of ``SELECT … FOR
    UPDATE``. Use it for critical sections like ``try_redeem`` on promo codes.

    If ``conn`` is provided, the existing connection is reused (so the caller
    can do additional work inside the same transaction). Otherwise a fresh
    connection is opened and closed.

    On exception inside the ``async with`` block, the transaction is rolled
    back and the exception is re-raised.
    """
    if conn is not None:
        await conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            await conn.rollback()
            raise
        else:
            await conn.commit()
        return

    async with get_conn() as new_conn:
        await new_conn.execute("BEGIN IMMEDIATE")
        try:
            yield new_conn
        except BaseException:
            await new_conn.rollback()
            raise
        else:
            await new_conn.commit()
