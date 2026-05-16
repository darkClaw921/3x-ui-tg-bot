"""Tests for :mod:`app.handlers.admin.users`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.handlers.admin import users as users_mod
from app.keyboards.admin import AdminCB, UserCB
from app.xui import XuiError


def _state(data=None):
    s = AsyncMock()
    s.get_data = AsyncMock(return_value=data or {})
    s.update_data = AsyncMock()
    s.set_state = AsyncMock()
    s.clear = AsyncMock()
    return s


def test_safe_escapes_html():
    assert users_mod._safe("<a>") == "&lt;a&gt;"
    assert users_mod._safe(None) == "—"


def test_format_payment_basic():
    from app.db.repos.payments import Payment

    p = Payment(
        id=1, user_id=1, subscription_id=None, telegram_charge_id="C",
        stars_amount=10, plan_id=2, promo_id=3, status="paid",
        created_at="2025",
    )
    line = users_mod._format_payment(p)
    assert "C" in line
    assert "10" in line
    assert "plan#2" in line


def test_format_payment_refunded():
    from app.db.repos.payments import Payment

    p = Payment(
        id=1, user_id=1, subscription_id=None, telegram_charge_id="C",
        stars_amount=10, plan_id=None, promo_id=None, status="refunded",
        created_at="2025",
    )
    line = users_mod._format_payment(p)
    assert "↩" in line


async def test_resolve_user_query_digit(file_db, make_user):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        await make_user(conn, tg_id=42)

    u = await users_mod._resolve_user_query("42")
    assert u is not None and u.tg_id == 42


async def test_resolve_user_query_username(file_db, make_user):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        await make_user(conn, tg_id=1, username="Alice")

    u = await users_mod._resolve_user_query("@alice")
    assert u is not None


async def test_resolve_user_query_empty():
    assert await users_mod._resolve_user_query("") is None
    assert await users_mod._resolve_user_query("  ") is None


async def test_cb_open_users(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await users_mod.cb_open_users(cb, state)
    state.set_state.assert_awaited()


async def test_cb_search(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await users_mod.cb_search(cb, state)
    state.set_state.assert_awaited()


async def test_st_query_empty(file_db):
    msg = MagicMock()
    msg.text = "   "
    msg.answer = AsyncMock()
    state = _state()
    await users_mod.st_query(msg, state)
    state.clear.assert_not_awaited()


async def test_st_query_not_found(file_db):
    msg = MagicMock()
    msg.text = "9999999"
    msg.answer = AsyncMock()
    state = _state()
    await users_mod.st_query(msg, state)
    state.clear.assert_awaited()


async def test_st_query_found(file_db, make_user, monkeypatch):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=42)

    msg = MagicMock()
    msg.text = "42"
    msg.answer = AsyncMock()
    msg.edit_text = AsyncMock()
    state = _state()

    monkeypatch.setattr(
        users_mod, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    await users_mod.st_query(msg, state)
    state.clear.assert_awaited()


async def test_cb_card_existing(file_db, make_user, monkeypatch):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    monkeypatch.setattr(
        users_mod, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    await users_mod.cb_card(cb, UserCB(action="card", id=u.id))
    cb.message.edit_text.assert_awaited()


async def test_cb_card_missing(file_db):
    cb = MagicMock()
    cb.answer = AsyncMock()
    await users_mod.cb_card(cb, UserCB(action="card", id=999))
    cb.answer.assert_awaited()


async def test_cb_revoke_happy(
    file_db, make_user, make_subscription, monkeypatch
):
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        sub = await make_subscription(conn, user_id=u.id)

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value=None)
    monkeypatch.setattr(users_mod, "get_xui_client", AsyncMock(return_value=xui))

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await users_mod.cb_revoke(
        cb, UserCB(action="revoke", id=sub.id, user_id=u.id)
    )
    async with get_conn() as conn:
        fresh = await subs_repo.get(conn, sub.id)
    assert fresh.status == "revoked"


async def test_cb_revoke_invalid_request(file_db):
    cb = MagicMock()
    cb.answer = AsyncMock()
    await users_mod.cb_revoke(cb, UserCB(action="revoke", id=0, user_id=0))
    cb.answer.assert_awaited()


async def test_cb_revoke_sub_not_found(file_db):
    cb = MagicMock()
    cb.answer = AsyncMock()
    await users_mod.cb_revoke(cb, UserCB(action="revoke", id=999, user_id=1))
    cb.answer.assert_awaited()


async def test_cb_revoke_wrong_owner(
    file_db, make_user, make_subscription
):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u1 = await make_user(conn, tg_id=1)
        u2 = await make_user(conn, tg_id=2)
        sub = await make_subscription(conn, user_id=u1.id)

    cb = MagicMock()
    cb.answer = AsyncMock()
    await users_mod.cb_revoke(cb, UserCB(action="revoke", id=sub.id, user_id=u2.id))
    cb.answer.assert_awaited()


async def test_cb_toggle_admin(file_db, make_user):
    from app.db.engine import get_conn
    from app.db.repos import users as users_repo

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await users_mod.cb_toggle_admin(cb, UserCB(action="toggle_admin", id=u.id))
    async with get_conn() as conn:
        fresh = await users_repo.get_by_id(conn, u.id)
    assert fresh.is_admin is True


async def test_cb_toggle_admin_missing(file_db):
    cb = MagicMock()
    cb.answer = AsyncMock()
    await users_mod.cb_toggle_admin(cb, UserCB(action="toggle_admin", id=9999))
    cb.answer.assert_awaited()


async def test_fetch_traffic_line_xui_error(
    file_db, make_user, make_subscription, monkeypatch
):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        sub = await make_subscription(conn, user_id=u.id)

    xui = AsyncMock()
    xui.request_json = AsyncMock(side_effect=XuiError("down"))
    monkeypatch.setattr(users_mod, "get_xui_client", AsyncMock(return_value=xui))

    line = await users_mod._fetch_traffic_line(sub)
    assert "панель" in line.lower() or "недоступна" in line.lower()


async def test_fetch_traffic_line_empty_obj(
    file_db, make_user, make_subscription, monkeypatch
):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        sub = await make_subscription(conn, user_id=u.id)

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value=None)
    monkeypatch.setattr(users_mod, "get_xui_client", AsyncMock(return_value=xui))

    line = await users_mod._fetch_traffic_line(sub)
    assert "не найден" in line.lower() or "клиент" in line.lower()


async def test_fetch_traffic_line_inactive_sub(file_db, make_user, make_subscription):
    from datetime import UTC, datetime, timedelta
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        sub = await make_subscription(
            conn, user_id=u.id, expires_at=datetime.now(UTC) - timedelta(days=1)
        )
    line = await users_mod._fetch_traffic_line(sub)
    assert line == ""


async def test_fetch_traffic_line_unexpected_exception(
    file_db, make_user, make_subscription, monkeypatch
):
    """A non-XuiError exception is caught and returns 'ошибка'."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        sub = await make_subscription(conn, user_id=u.id)

    monkeypatch.setattr(
        users_mod, "get_xui_client", AsyncMock(side_effect=RuntimeError("oops"))
    )
    line = await users_mod._fetch_traffic_line(sub)
    assert "ошибка" in line.lower()


async def test_fetch_traffic_line_bad_int(
    file_db, make_user, make_subscription, monkeypatch
):
    """If panel returns garbage in up/down → 'некорректный ответ'."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        sub = await make_subscription(conn, user_id=u.id)

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"up": "BAD", "down": "X"})
    monkeypatch.setattr(users_mod, "get_xui_client", AsyncMock(return_value=xui))

    line = await users_mod._fetch_traffic_line(sub)
    assert "некорректный" in line.lower()


async def test_fetch_traffic_line_ok(
    file_db, make_user, make_subscription, monkeypatch
):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        sub = await make_subscription(conn, user_id=u.id)

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"up": 1024, "down": 2048})
    monkeypatch.setattr(users_mod, "get_xui_client", AsyncMock(return_value=xui))
    line = await users_mod._fetch_traffic_line(sub)
    assert "↑" in line and "↓" in line


async def test_build_card_with_subs_and_payments(
    file_db, make_user, make_subscription, monkeypatch
):
    """Cover the long _build_card branch with active+inactive subs and payments."""
    from datetime import UTC, datetime, timedelta
    from app.db.engine import get_conn
    from app.db.repos import payments as payments_repo

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        # Active sub.
        await make_subscription(conn, user_id=u.id)
        # Several inactive subs.
        for i in range(8):
            await make_subscription(
                conn,
                user_id=u.id,
                xui_client_uuid=f"u{i}",
                xui_client_email=f"e{i}",
                expires_at=datetime.now(UTC) - timedelta(days=i + 1),
            )
        # Several payments.
        for i in range(15):
            await payments_repo.create(
                conn,
                user_id=u.id,
                subscription_id=None,
                telegram_charge_id=f"c{i}",
                stars_amount=i + 1,
                plan_id=None,
                promo_id=None,
            )

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"up": 1, "down": 2})
    monkeypatch.setattr(users_mod, "get_xui_client", AsyncMock(return_value=xui))

    text, sub_id, is_admin = await users_mod._build_card(u)
    assert sub_id is not None
    assert "истёкших" in text or "истекших" in text


async def test_cb_revoke_xui_failure(
    file_db, make_user, make_subscription, monkeypatch
):
    """If the revoke service raises an unexpected exception, the handler answers with the error."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        sub = await make_subscription(conn, user_id=u.id)

    # Force the revoke service to raise (non-XuiError).
    from app.services import subscriptions as subs_svc

    monkeypatch.setattr(
        subs_svc, "revoke", AsyncMock(side_effect=RuntimeError("oops"))
    )
    monkeypatch.setattr(
        users_mod, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await users_mod.cb_revoke(
        cb, UserCB(action="revoke", id=sub.id, user_id=u.id)
    )
    cb.answer.assert_awaited()
