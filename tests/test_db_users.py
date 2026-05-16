"""Tests for :mod:`app.db.repos.users`."""

from __future__ import annotations

import aiosqlite
import pytest

from app.db.repos import users as users_repo


async def test_get_by_tg_id_not_found(db_conn):
    assert await users_repo.get_by_tg_id(db_conn, 999) is None


async def test_get_by_id_not_found(db_conn):
    assert await users_repo.get_by_id(db_conn, 999) is None


async def test_create_and_get_by_tg_id(db_conn):
    u = await users_repo.create(db_conn, tg_id=42, username="alice", first_name="A")
    assert u.tg_id == 42
    assert u.username == "alice"
    assert u.is_admin is False

    got = await users_repo.get_by_tg_id(db_conn, 42)
    assert got is not None
    assert got.id == u.id


async def test_create_duplicate_tg_id(db_conn):
    await users_repo.create(db_conn, tg_id=1, username="u", first_name="X")
    with pytest.raises(aiosqlite.IntegrityError):
        await users_repo.create(db_conn, tg_id=1, username="dup", first_name="X")


async def test_get_or_create_existing_no_change(db_conn, monkeypatch):
    """get_or_create reuses the existing row when admin flag matches."""
    from app.config import settings

    monkeypatch.setattr(settings, "ADMIN_IDS", [1, 2])

    u1 = await users_repo.get_or_create(
        db_conn, tg_id=10, username="u", first_name="X"
    )
    assert u1.is_admin is False
    u2 = await users_repo.get_or_create(
        db_conn, tg_id=10, username="u", first_name="X"
    )
    assert u2.id == u1.id
    assert u2.is_admin is False


async def test_get_or_create_promotes_to_admin(db_conn, monkeypatch):
    """If the existing user's is_admin diverges from settings, sync it."""
    from app.config import settings

    monkeypatch.setattr(settings, "ADMIN_IDS", [])
    u1 = await users_repo.get_or_create(
        db_conn, tg_id=10, username="u", first_name="X"
    )
    assert u1.is_admin is False

    monkeypatch.setattr(settings, "ADMIN_IDS", [10])
    u2 = await users_repo.get_or_create(
        db_conn, tg_id=10, username="u", first_name="X"
    )
    assert u2.is_admin is True


async def test_get_or_create_revokes_admin(db_conn, monkeypatch):
    """Same in the reverse direction — admin → non-admin if removed from env."""
    from app.config import settings

    monkeypatch.setattr(settings, "ADMIN_IDS", [10])
    u1 = await users_repo.get_or_create(
        db_conn, tg_id=10, username="u", first_name="X"
    )
    assert u1.is_admin is True

    monkeypatch.setattr(settings, "ADMIN_IDS", [])
    u2 = await users_repo.get_or_create(
        db_conn, tg_id=10, username="u", first_name="X"
    )
    assert u2.is_admin is False


async def test_set_admin(db_conn):
    u = await users_repo.create(db_conn, tg_id=1, username="x", first_name="X")
    await users_repo.set_admin(db_conn, u.id, True)
    refreshed = await users_repo.get_by_id(db_conn, u.id)
    assert refreshed.is_admin is True

    await users_repo.set_admin(db_conn, u.id, False)
    refreshed = await users_repo.get_by_id(db_conn, u.id)
    assert refreshed.is_admin is False


async def test_get_by_username_with_at(db_conn):
    await users_repo.create(db_conn, tg_id=1, username="Alice", first_name="X")
    got = await users_repo.get_by_username(db_conn, "@Alice")
    assert got is not None
    assert got.tg_id == 1


async def test_get_by_username_case_insensitive(db_conn):
    await users_repo.create(db_conn, tg_id=1, username="Alice", first_name="X")
    got = await users_repo.get_by_username(db_conn, "alice")
    assert got is not None
    got = await users_repo.get_by_username(db_conn, "ALICE")
    assert got is not None


async def test_get_by_username_empty(db_conn):
    assert await users_repo.get_by_username(db_conn, "") is None
    assert await users_repo.get_by_username(db_conn, "@") is None
    assert await users_repo.get_by_username(db_conn, "  ") is None


async def test_get_by_username_missing(db_conn):
    assert await users_repo.get_by_username(db_conn, "nobody") is None


async def test_user_from_row_construct(db_conn):
    """Cover the from_row classmethod path explicitly."""
    await users_repo.create(db_conn, tg_id=1, username="u", first_name="X")
    cur = await db_conn.execute("SELECT * FROM users WHERE tg_id=1")
    row = await cur.fetchone()
    from app.db.repos.users import User

    u = User.from_row(row)
    assert u.tg_id == 1
    assert u.username == "u"
