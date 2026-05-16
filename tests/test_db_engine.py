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
