"""Tests for :mod:`app.db.engine` — schema/migrations, foreign_keys, transactions."""

from __future__ import annotations

import aiosqlite
import pytest


async def test_schema_created_with_all_tables(db_conn):
    cursor = await db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    rows = await cursor.fetchall()
    names = {r["name"] for r in rows}
    for required in (
        "users",
        "plans",
        "promos",
        "subscriptions",
        "promo_redemptions",
        "payments",
        "traffic_snapshots",
        "subscription_notifications",
    ):
        assert required in names


async def test_foreign_keys_enabled(db_conn):
    cursor = await db_conn.execute("PRAGMA foreign_keys")
    row = await cursor.fetchone()
    assert row[0] == 1


async def test_foreign_keys_enforced_on_violation(db_conn):
    """Inserting a subscription with a missing user_id should fail."""
    with pytest.raises(aiosqlite.IntegrityError):
        await db_conn.execute(
            "INSERT INTO subscriptions "
            "(user_id, xui_inbound_id, xui_client_uuid, xui_client_email, "
            "xui_sub_id, expires_at, plan_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (9999, 1, "uuid", "email", "sub", "2099-01-01", None),
        )
        await db_conn.commit()


async def test_init_db_creates_file_and_runs_migrations(tmp_path, monkeypatch):
    """init_db is idempotent and creates parent dirs."""
    from app.config import settings
    from app.db.engine import init_db

    target = tmp_path / "deep" / "nested" / "test.db"
    monkeypatch.setattr(settings, "DB_PATH", str(target))

    await init_db()
    assert target.exists()
    # Run twice — must not error.
    await init_db()


async def test_transaction_rolls_back_on_exception(file_db):
    """transaction() must rollback on exception."""
    from app.db.engine import get_conn, transaction

    async with get_conn() as conn:
        await conn.execute(
            "INSERT INTO users (tg_id, username) VALUES (?, ?)", (1, "x")
        )
        await conn.commit()

    with pytest.raises(RuntimeError):
        async with get_conn() as conn:
            async with transaction(conn):
                await conn.execute(
                    "INSERT INTO users (tg_id, username) VALUES (?, ?)", (2, "y")
                )
                raise RuntimeError("boom")

    async with get_conn() as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM users")
        row = await cur.fetchone()
    assert row[0] == 1


async def test_transaction_without_conn_arg(file_db):
    """transaction() with conn=None opens its own connection and commits."""
    from app.db.engine import get_conn, transaction

    async with transaction() as conn:
        await conn.execute(
            "INSERT INTO users (tg_id, username) VALUES (?, ?)", (99, "alice")
        )

    async with get_conn() as conn:
        cur = await conn.execute("SELECT tg_id FROM users WHERE username='alice'")
        row = await cur.fetchone()
    assert row[0] == 99


async def test_transaction_without_conn_rolls_back(file_db):
    """transaction() with conn=None rolls back on exception."""
    from app.db.engine import get_conn, transaction

    with pytest.raises(ValueError):
        async with transaction() as conn:
            await conn.execute(
                "INSERT INTO users (tg_id, username) VALUES (?, ?)", (55, "bob")
            )
            raise ValueError

    async with get_conn() as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM users WHERE tg_id=55")
        row = await cur.fetchone()
    assert row[0] == 0


async def test_apply_migrations_idempotent(db_conn):
    """Running _apply_migrations twice is a no-op (duplicate-column tolerated)."""
    from app.db.engine import _apply_migrations

    # First call done by db_conn fixture; second must not raise.
    await _apply_migrations(db_conn)
    # Verify the migrated column is present.
    cursor = await db_conn.execute("PRAGMA table_info(subscriptions)")
    cols = {r["name"] for r in await cursor.fetchall()}
    assert "xui_sub_id" in cols


async def test_users_lang_column_present_and_defaults_ru(db_conn):
    """The ``users.lang`` migration adds the column with a ``'ru'`` default."""
    cursor = await db_conn.execute("PRAGMA table_info(users)")
    rows = await cursor.fetchall()
    cols = {r["name"]: r for r in rows}
    assert "lang" in cols
    # A row inserted without ``lang`` must default to ``'ru'``.
    await db_conn.execute("INSERT INTO users (tg_id, username) VALUES (?, ?)", (777, "x"))
    await db_conn.commit()
    cur = await db_conn.execute("SELECT lang FROM users WHERE tg_id=777")
    row = await cur.fetchone()
    assert row["lang"] == "ru"


async def test_users_lang_migration_on_legacy_db(tmp_path, monkeypatch):
    """A DB created without ``users.lang`` gets the column added in-place.

    Simulates an upgrade: build a minimal pre-migration ``users`` table (no
    ``lang``), then run :func:`_apply_migrations` and confirm the column is
    backfilled with the ``'ru'`` default for existing rows.
    """
    import aiosqlite as _aiosqlite

    from app.db.engine import _apply_migrations

    db_file = tmp_path / "legacy.db"
    async with _aiosqlite.connect(db_file) as conn:
        conn.row_factory = _aiosqlite.Row
        # Legacy schema: users table WITHOUT the lang column.
        await conn.execute(
            "CREATE TABLE users ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " tg_id INTEGER NOT NULL UNIQUE,"
            " username TEXT, first_name TEXT,"
            " is_admin INTEGER NOT NULL DEFAULT 0,"
            " created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        # The other tables the migration touches must exist too. The
        # ``subscriptions`` table carries ``user_id`` (always present in the
        # real schema) so the ``idx_subscriptions_one_trial`` partial-unique
        # index migration — which references ``user_id`` — can be created.
        await conn.execute("CREATE TABLE plans (id INTEGER PRIMARY KEY)")
        await conn.execute(
            "CREATE TABLE subscriptions (id INTEGER PRIMARY KEY,"
            " user_id INTEGER, xui_sub_id TEXT, plan_id INTEGER)"
        )
        await conn.execute("INSERT INTO users (tg_id, username) VALUES (1, 'old')")
        await conn.commit()

        await _apply_migrations(conn)
        # Idempotent — second run must not raise.
        await _apply_migrations(conn)

        cur = await conn.execute("PRAGMA table_info(users)")
        cols = {r["name"] for r in await cur.fetchall()}
        assert "lang" in cols
        cur = await conn.execute("SELECT lang FROM users WHERE tg_id=1")
        row = await cur.fetchone()
        assert row["lang"] == "ru"


async def test_set_lang_get_lang_round_trip(file_db):
    """``set_lang`` persists a supported language and ``get_lang`` reads it back."""
    from app.db.engine import get_conn
    from app.db.repos import users as users_repo

    async with get_conn() as conn:
        user = await users_repo.create(
            conn, tg_id=42, username="u", first_name="U", language_code="en-US"
        )
        # language_code='en-US' normalizes to 'en' at creation.
        assert user.lang == "en"
        assert await users_repo.get_lang(conn, user.id) == "en"

        await users_repo.set_lang(conn, user.id, "uk")
        assert await users_repo.get_lang(conn, user.id) == "uk"

        # An unsupported code is normalized back to the default via resolve_lang.
        await users_repo.set_lang(conn, user.id, "zz")
        assert await users_repo.get_lang(conn, user.id) == "ru"

        # get_lang for a missing user returns the default language.
        assert await users_repo.get_lang(conn, 99999) == "ru"
