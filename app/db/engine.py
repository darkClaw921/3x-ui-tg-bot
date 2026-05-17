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
                kind            TEXT NOT NULL
                                    CHECK (kind IN ('3d', '1d', '0d', 'expired')),
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
    )
    for name, stmt in create_table_migrations:
        try:
            await conn.execute(stmt)
        except aiosqlite.OperationalError as exc:
            logger.warning("migration {} failed: {}", name, exc)
            raise

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
