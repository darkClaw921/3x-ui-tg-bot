"""Tests for :mod:`app.handlers.user.my_subscription`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.repos.users import User
from app.handlers.user import my_subscription as my_sub_mod
from app.keyboards.user import SubCB, UserCB
from app.xui import XuiError


def test_format_bytes_zero():
    assert my_sub_mod._format_bytes(0) == "0 B"


def test_format_bytes_kb():
    assert my_sub_mod._format_bytes(1024) == "1.0 KB"


def test_format_bytes_gb():
    assert my_sub_mod._format_bytes(5 * 1024 ** 3) == "5.0 GB"


def test_format_bytes_negative_clamped():
    assert my_sub_mod._format_bytes(-100) == "0 B"


def test_parse_iso_with_space():
    dt = my_sub_mod._parse_iso("2025-01-01 12:00:00")
    assert dt.year == 2025


def test_days_delta_future():
    future = (datetime.now(UTC) + timedelta(days=5)).isoformat(sep=" ")
    assert my_sub_mod._days_delta(future) >= 4


def test_days_delta_past():
    past = (datetime.now(UTC) - timedelta(days=2)).isoformat(sep=" ")
    assert my_sub_mod._days_delta(past) <= -2


async def test_cb_open_my_no_subscription(file_db, make_user):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await my_sub_mod.cb_open_my(cb, user=user)
    cb.message.edit_text.assert_awaited()
    text = cb.message.edit_text.call_args.args[0]
    assert "Купить" in text or "нет подписки" in text.lower()


async def test_cb_open_my_with_active_sub(
    file_db, make_user, make_subscription, monkeypatch
):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        await make_subscription(conn, user_id=user.id)

    # Mock the panel call.
    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"up": 100, "down": 200})
    monkeypatch.setattr(my_sub_mod, "get_xui_client", AsyncMock(return_value=xui))

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await my_sub_mod.cb_open_my(cb, user=user)
    cb.message.edit_text.assert_awaited()


async def test_cb_open_my_xui_error(file_db, make_user, make_subscription, monkeypatch):
    """Panel error must NOT crash the card."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        await make_subscription(conn, user_id=user.id)

    xui = AsyncMock()
    xui.request_json = AsyncMock(side_effect=XuiError("down"))
    monkeypatch.setattr(my_sub_mod, "get_xui_client", AsyncMock(return_value=xui))

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await my_sub_mod.cb_open_my(cb, user=user)
    text = cb.message.edit_text.call_args.args[0]
    assert "не удалось" in text.lower() or "панель" in text.lower()


async def test_cb_open_my_user_none(file_db):
    cb = MagicMock()
    cb.answer = AsyncMock()
    await my_sub_mod.cb_open_my(cb, user=None)
    cb.answer.assert_awaited()


async def test_cb_open_my_multiple_subs(
    file_db, make_user, make_subscription, monkeypatch
):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        await make_subscription(
            conn,
            user_id=user.id,
            xui_client_uuid="u1",
            xui_client_email="e1",
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        await make_subscription(
            conn,
            user_id=user.id,
            xui_client_uuid="u2",
            xui_client_email="e2",
            expires_at=datetime.now(UTC) + timedelta(days=10),
        )

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"up": 0, "down": 0})
    monkeypatch.setattr(my_sub_mod, "get_xui_client", AsyncMock(return_value=xui))

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await my_sub_mod.cb_open_my(cb, user=user)
    cb.message.edit_text.assert_awaited()


async def test_cb_resend_keys_no_user(file_db, mock_bot):
    cb = MagicMock()
    cb.answer = AsyncMock()
    await my_sub_mod.cb_resend_keys(cb, SubCB(action="keys", sub_id=1), mock_bot, user=None)
    cb.answer.assert_awaited()


async def test_cb_resend_keys_no_sub_id(file_db, make_user, mock_bot):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
    cb = MagicMock()
    cb.answer = AsyncMock()
    await my_sub_mod.cb_resend_keys(cb, SubCB(action="keys", sub_id=0), mock_bot, user=u)
    cb.answer.assert_awaited()


async def test_cb_resend_keys_ownership_mismatch(
    file_db, make_user, make_subscription, mock_bot
):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u1 = await make_user(conn, tg_id=1)
        u2 = await make_user(conn, tg_id=2)
        sub = await make_subscription(conn, user_id=u1.id)

    cb = MagicMock()
    cb.answer = AsyncMock()
    await my_sub_mod.cb_resend_keys(
        cb, SubCB(action="keys", sub_id=sub.id), mock_bot, user=u2
    )
    cb.answer.assert_awaited()


async def test_cb_resend_keys_no_message(file_db, make_user, make_subscription, mock_bot):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        sub = await make_subscription(conn, user_id=u.id)

    cb = MagicMock()
    cb.message = None
    cb.answer = AsyncMock()
    await my_sub_mod.cb_resend_keys(
        cb, SubCB(action="keys", sub_id=sub.id), mock_bot, user=u
    )
    cb.answer.assert_awaited()


async def test_cb_resend_keys_happy(
    file_db, make_user, make_subscription, mock_bot, monkeypatch
):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        sub = await make_subscription(conn, user_id=u.id)

    monkeypatch.setattr(my_sub_mod, "get_xui_client", AsyncMock(return_value=AsyncMock()))
    monkeypatch.setattr(my_sub_mod, "deliver_keys", AsyncMock())

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.chat = MagicMock(id=42)
    cb.answer = AsyncMock()
    await my_sub_mod.cb_resend_keys(
        cb, SubCB(action="keys", sub_id=sub.id), mock_bot, user=u
    )
    cb.answer.assert_awaited()


def test_format_status_lines():
    from app.db.repos.subscriptions import Subscription
    from datetime import UTC, datetime, timedelta

    future = (datetime.now(UTC) + timedelta(days=5)).isoformat(sep=" ")
    past = (datetime.now(UTC) - timedelta(days=5)).isoformat(sep=" ")
    today = datetime.now(UTC).isoformat(sep=" ")

    s_active = Subscription(
        id=1, user_id=1, xui_inbound_id=1, xui_client_uuid="u",
        xui_client_email="e", xui_sub_id="s", expires_at=future,
        created_at="2025", plan_id=None, status="active",
    )
    s_revoked = Subscription(
        id=2, user_id=1, xui_inbound_id=1, xui_client_uuid="u",
        xui_client_email="e", xui_sub_id="s", expires_at=future,
        created_at="2025", plan_id=None, status="revoked",
    )
    s_expired = Subscription(
        id=3, user_id=1, xui_inbound_id=1, xui_client_uuid="u",
        xui_client_email="e", xui_sub_id="s", expires_at=past,
        created_at="2025", plan_id=None, status="expired",
    )

    assert "активна" in my_sub_mod._format_status_line(s_active)
    assert "отозвана" in my_sub_mod._format_status_line(s_revoked)
    assert "истекла" in my_sub_mod._format_status_line(s_expired)


def test_format_days_line_today():
    from app.db.repos.subscriptions import Subscription
    from datetime import UTC, datetime, timedelta

    today_plus = (datetime.now(UTC) + timedelta(hours=2)).isoformat(sep=" ")
    s = Subscription(
        id=1, user_id=1, xui_inbound_id=1, xui_client_uuid="u",
        xui_client_email="e", xui_sub_id="s", expires_at=today_plus,
        created_at="2025", plan_id=None, status="active",
    )
    line = my_sub_mod._format_days_line(s)
    assert "сегодня" in line.lower()


def test_format_days_line_yesterday():
    from app.db.repos.subscriptions import Subscription
    from datetime import UTC, datetime, timedelta

    past = (datetime.now(UTC) - timedelta(days=2)).isoformat(sep=" ")
    s = Subscription(
        id=1, user_id=1, xui_inbound_id=1, xui_client_uuid="u",
        xui_client_email="e", xui_sub_id="s", expires_at=past,
        created_at="2025", plan_id=None, status="expired",
    )
    line = my_sub_mod._format_days_line(s)
    assert "назад" in line.lower()


async def test_fetch_traffics_bad_int(file_db, make_user, make_subscription, monkeypatch):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        sub = await make_subscription(conn, user_id=u.id)

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"up": "BAD", "down": "BAD"})
    monkeypatch.setattr(my_sub_mod, "get_xui_client", AsyncMock(return_value=xui))
    up, down, ok = await my_sub_mod._fetch_traffics(sub)
    assert ok is False


async def test_fetch_traffics_panel_unexpected_exception(
    file_db, make_user, make_subscription, monkeypatch
):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        sub = await make_subscription(conn, user_id=u.id)

    monkeypatch.setattr(
        my_sub_mod, "get_xui_client", AsyncMock(side_effect=RuntimeError("x"))
    )
    up, down, ok = await my_sub_mod._fetch_traffics(sub)
    assert ok is False


async def test_cb_open_my_lots_of_inactive(
    file_db, make_user, make_subscription, monkeypatch
):
    """Many extra subs → '… и ещё N' line."""
    from datetime import UTC, datetime, timedelta
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        # One active
        await make_subscription(conn, user_id=user.id)
        # 8 inactive
        for i in range(8):
            await make_subscription(
                conn,
                user_id=user.id,
                xui_client_uuid=f"u{i}",
                xui_client_email=f"e{i}",
                expires_at=datetime.now(UTC) - timedelta(days=i + 1),
            )

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"up": 0, "down": 0})
    monkeypatch.setattr(my_sub_mod, "get_xui_client", AsyncMock(return_value=xui))

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await my_sub_mod.cb_open_my(cb, user=user)
    text = cb.message.edit_text.call_args.args[0]
    assert "ещё" in text


async def test_cb_resend_keys_xui_error_message(
    file_db, make_user, make_subscription, mock_bot, monkeypatch
):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        sub = await make_subscription(conn, user_id=u.id)

    monkeypatch.setattr(my_sub_mod, "get_xui_client", AsyncMock(return_value=AsyncMock()))
    monkeypatch.setattr(
        my_sub_mod, "deliver_keys", AsyncMock(side_effect=XuiError("down"))
    )

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.chat = MagicMock(id=42)
    cb.answer = AsyncMock()
    await my_sub_mod.cb_resend_keys(
        cb, SubCB(action="keys", sub_id=sub.id), mock_bot, user=u
    )
    mock_bot.send_message.assert_awaited()
