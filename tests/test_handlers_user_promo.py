"""Tests for :mod:`app.handlers.user.promo`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.handlers.user import promo as promo_mod
from app.keyboards.user import PromoActCB
from app.xui import XuiError


def _state():
    s = AsyncMock()
    s.get_data = AsyncMock(return_value={})
    s.update_data = AsyncMock()
    s.set_state = AsyncMock()
    s.clear = AsyncMock()
    return s


async def test_cb_open(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await promo_mod.cb_open(cb, state)
    cb.message.edit_text.assert_awaited()
    state.set_state.assert_awaited()


async def test_msg_code_no_user(file_db, mock_bot):
    msg = MagicMock()
    msg.text = "x"
    msg.answer = AsyncMock()
    state = _state()
    await promo_mod.msg_code(msg, state, mock_bot, user=None)
    msg.answer.assert_awaited()


async def test_msg_code_invalid(file_db, make_user, mock_bot):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)

    msg = MagicMock()
    msg.text = "BAD"
    msg.answer = AsyncMock()
    state = _state()
    await promo_mod.msg_code(msg, state, mock_bot, user=u)
    msg.answer.assert_awaited()
    # State NOT cleared (stays in waiting_code).
    state.clear.assert_not_awaited()


async def test_msg_code_discount_type_routed_to_buy(
    file_db, make_user, make_promo, mock_bot
):
    """percent/flat_stars promos are rejected here with a hint."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        await make_promo(conn, code="DISCOUNT", type="percent", value=10)

    msg = MagicMock()
    msg.text = "discount"
    msg.answer = AsyncMock()
    msg.chat = MagicMock(id=1)
    state = _state()
    await promo_mod.msg_code(msg, state, mock_bot, user=u)
    state.clear.assert_awaited()
    msg.answer.assert_awaited()


async def test_msg_code_free_days_happy(
    file_db, make_user, make_promo, mock_bot, monkeypatch
):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        await make_promo(conn, code="FREE", type="free_days", value=7)

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"id": "u"})
    monkeypatch.setattr(promo_mod, "get_xui_client", AsyncMock(return_value=xui))
    monkeypatch.setattr(promo_mod, "deliver_keys", AsyncMock())

    msg = MagicMock()
    msg.text = "free"
    msg.answer = AsyncMock()
    msg.chat = MagicMock(id=42)
    state = _state()
    await promo_mod.msg_code(msg, state, mock_bot, user=u)
    state.clear.assert_awaited()
    promo_mod.deliver_keys.assert_awaited()


async def test_msg_code_xui_failure(
    file_db, make_user, make_promo, mock_bot, monkeypatch
):
    """xui failure → user notified, promo NOT redeemed."""
    from app.db.engine import get_conn
    from app.db.repos import promos as promos_repo

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        promo = await make_promo(conn, code="FREE", type="free_days", value=7)

    xui = AsyncMock()
    xui.request_json = AsyncMock(side_effect=XuiError("down"))
    monkeypatch.setattr(promo_mod, "get_xui_client", AsyncMock(return_value=xui))

    msg = MagicMock()
    msg.text = "free"
    msg.answer = AsyncMock()
    msg.chat = MagicMock(id=42)
    state = _state()
    await promo_mod.msg_code(msg, state, mock_bot, user=u)
    msg.answer.assert_awaited()
    # Promo's used_count is unchanged.
    async with get_conn() as conn:
        refreshed = await promos_repo.get(conn, promo.id)
    assert refreshed.used_count == 0


async def test_msg_code_double_activation(
    file_db, make_user, make_promo, mock_bot, monkeypatch
):
    """Re-using a free_days promo for the same user is rejected."""
    from app.db.engine import get_conn
    from app.db.repos import promos as promos_repo

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        promo = await make_promo(conn, code="FREE", type="free_days", value=7)
        # Pre-redeem.
        await promos_repo.try_redeem(
            conn, promo_id=promo.id, user_id=u.id, subscription_id=None
        )

    msg = MagicMock()
    msg.text = "free"
    msg.answer = AsyncMock()
    state = _state()
    await promo_mod.msg_code(msg, state, mock_bot, user=u)
    msg.answer.assert_awaited()
    state.clear.assert_not_awaited()
