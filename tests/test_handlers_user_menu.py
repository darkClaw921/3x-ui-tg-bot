"""Tests for :mod:`app.handlers.user.menu` and :mod:`app.handlers.user.help`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.handlers.user import help as help_mod
from app.handlers.user import menu as menu_mod
from app.handlers.admin import menu as admin_menu_mod


def _state():
    s = AsyncMock()
    s.clear = AsyncMock()
    return s


async def test_cmd_menu(file_db, make_user):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)

    msg = MagicMock()
    msg.answer = AsyncMock()
    await menu_mod.cmd_menu(msg, user=u)
    msg.answer.assert_awaited()


async def test_cmd_menu_no_user(file_db):
    msg = MagicMock()
    msg.answer = AsyncMock()
    await menu_mod.cmd_menu(msg, user=None)
    msg.answer.assert_awaited()


async def test_cb_menu(file_db, make_user):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await menu_mod.cb_menu(cb, user=u)
    cb.message.edit_text.assert_awaited()


async def test_cb_cancel(file_db, make_user):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await menu_mod.cb_cancel(cb, state, user=u)
    state.clear.assert_awaited()


async def test_cb_help(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await help_mod.cb_help(cb)
    cb.message.edit_text.assert_awaited()


async def test_admin_cmd_admin(file_db):
    msg = MagicMock()
    msg.answer = AsyncMock()
    await admin_menu_mod.cmd_admin(msg)
    msg.answer.assert_awaited()


async def test_admin_open_main(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await admin_menu_mod.open_main(cb)
    cb.message.edit_text.assert_awaited()


async def test_admin_cancel(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await admin_menu_mod.cancel_fsm(cb, state)
    state.clear.assert_awaited()
