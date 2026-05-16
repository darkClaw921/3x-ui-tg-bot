"""Tests for :mod:`app.handlers.start`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.repos.users import User
from app.handlers.start import cmd_start


def _user(*, is_admin: bool, user_id: int = 1, tg_id: int = 1) -> User:
    return User(
        id=user_id,
        tg_id=tg_id,
        username="u",
        first_name="X",
        is_admin=is_admin,
        created_at="2025",
    )


async def test_start_admin(file_db):
    msg = MagicMock()
    msg.answer = AsyncMock()
    await cmd_start(msg, user=_user(is_admin=True))
    msg.answer.assert_awaited_once()
    kw = msg.answer.call_args.kwargs
    text = msg.answer.call_args.args[0] if msg.answer.call_args.args else kw.get("text", "")
    assert "Админ" in text


async def test_start_user_no_subscription(file_db, make_user):
    """Standard user without sub → shows main user menu."""
    from app.db.engine import get_conn
    from app.db.repos.users import get_by_tg_id

    async with get_conn() as conn:
        # Use the factory through the same connection.
        from app.db.repos.users import create

        u = await create(conn, tg_id=10, username="x", first_name="X")

    msg = MagicMock()
    msg.answer = AsyncMock()
    await cmd_start(msg, user=u)
    msg.answer.assert_awaited_once()


async def test_start_user_with_subscription(file_db, make_user, make_subscription):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=5)
        await make_subscription(conn, user_id=u.id)

    msg = MagicMock()
    msg.answer = AsyncMock()
    await cmd_start(msg, user=u)
    msg.answer.assert_awaited_once()


async def test_start_user_is_none(file_db):
    """If user is None (middleware failed), still answer."""
    msg = MagicMock()
    msg.answer = AsyncMock()
    await cmd_start(msg, user=None)
    msg.answer.assert_awaited_once()
