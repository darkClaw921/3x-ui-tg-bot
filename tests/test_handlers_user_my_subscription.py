"""Tests for :mod:`app.handlers.user.my_subscription`.

After Phase 4 the «Моя подписка» screen renders **all** of the user's
subscriptions (active first, sorted by ``expires_at`` DESC; then
expired/revoked, sorted by ``created_at`` DESC) with per-subscription
inline buttons:

* 🆕 «Купить новую подписку» — always at the top — :class:`BuyCB(action='new')`.
* For every visible sub: 🔑 «Ключи #N» plus, when the sub is active,
  🛒 «Продлить #N».
* ◀ «В меню» — at the bottom.

The list is capped at five subscriptions; if the user has more, a
``«… и ещё N подписок»`` footer line appears under the cards.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.repos.users import User
from app.handlers.user import my_subscription as my_sub_mod
from app.keyboards.user import BuyCB, SubCB, UserCB
from app.xui import XuiError


# --------------------------------------------------------------------- #
# Pure helpers — formatting / parsing
# --------------------------------------------------------------------- #


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


def test_pluralize_subs_one():
    assert my_sub_mod._pluralize_subs(1) == "подписка"


def test_pluralize_subs_few():
    assert my_sub_mod._pluralize_subs(2) == "подписки"
    assert my_sub_mod._pluralize_subs(4) == "подписки"


def test_pluralize_subs_many():
    assert my_sub_mod._pluralize_subs(5) == "подписок"
    assert my_sub_mod._pluralize_subs(11) == "подписок"
    assert my_sub_mod._pluralize_subs(21) == "подписка"


# --------------------------------------------------------------------- #
# Helpers to read keyboard structure
# --------------------------------------------------------------------- #


def _kb_buttons(markup) -> list[list[tuple[str, str]]]:
    """Return ``[[(text, callback_data), ...], ...]`` for one ``InlineKeyboardMarkup``."""
    rows = []
    for row in markup.inline_keyboard:
        rows.append([(btn.text, btn.callback_data or "") for btn in row])
    return rows


def _flat_buttons(markup) -> list[tuple[str, str]]:
    """Return a flat list of ``(text, callback_data)`` across all rows."""
    out: list[tuple[str, str]] = []
    for row in markup.inline_keyboard:
        for btn in row:
            out.append((btn.text, btn.callback_data or ""))
    return out


def _mock_callback() -> MagicMock:
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


# --------------------------------------------------------------------- #
# cb_open_my — empty / single / many
# --------------------------------------------------------------------- #


async def test_cb_open_my_no_subs_renders_buy_cta(file_db, make_user):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)

    cb = _mock_callback()
    await my_sub_mod.cb_open_my(cb, user=user)
    cb.message.edit_text.assert_awaited()
    text = cb.message.edit_text.call_args.args[0]
    assert "Купить" in text or "нет подписки" in text.lower()

    markup = cb.message.edit_text.call_args.kwargs["reply_markup"]
    flat = _flat_buttons(markup)
    # The no-sub screen uses BuyCB(action='open') — its 'Купить' CTA is
    # the only button (plus '◀ В меню').
    open_packed = BuyCB(action="open").pack()
    assert any(cb_data == open_packed for _, cb_data in flat)


async def test_cb_open_my_single_active_sub_renders_card_with_actions(
    file_db, make_user, make_subscription, monkeypatch
):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        sub = await make_subscription(conn, user_id=user.id)

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"up": 100, "down": 200})
    monkeypatch.setattr(my_sub_mod, "get_xui_client", AsyncMock(return_value=xui))

    cb = _mock_callback()
    await my_sub_mod.cb_open_my(cb, user=user)

    cb.message.edit_text.assert_awaited()
    text = cb.message.edit_text.call_args.args[0]
    assert f"#{sub.id}" in text  # card mentions the sub
    assert "активна" in text.lower()

    markup = cb.message.edit_text.call_args.kwargs["reply_markup"]
    flat = _flat_buttons(markup)
    # Top buy-new button.
    assert (
        "🆕 Купить новую подписку",
        BuyCB(action="new").pack(),
    ) in flat
    # Per-sub: keys + extend.
    assert (
        f"🔑 Ключи #{sub.id}",
        SubCB(action="keys", sub_id=sub.id).pack(),
    ) in flat
    assert (
        f"🛒 Продлить #{sub.id}",
        BuyCB(action="extend", sub_id=sub.id).pack(),
    ) in flat
    # Bottom back-to-menu.
    assert ("◀ В меню", UserCB(area="menu").pack()) in flat


async def test_cb_open_my_renders_all_subscriptions(
    file_db, make_user, make_subscription, monkeypatch
):
    """≥2 active subs → every one of them gets its own keys+extend buttons."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        sub1 = await make_subscription(
            conn,
            user_id=user.id,
            xui_client_uuid="u1",
            xui_client_email="e1",
            expires_at=datetime.now(UTC) + timedelta(days=5),
        )
        sub2 = await make_subscription(
            conn,
            user_id=user.id,
            xui_client_uuid="u2",
            xui_client_email="e2",
            expires_at=datetime.now(UTC) + timedelta(days=15),
        )

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"up": 0, "down": 0})
    monkeypatch.setattr(my_sub_mod, "get_xui_client", AsyncMock(return_value=xui))

    cb = _mock_callback()
    await my_sub_mod.cb_open_my(cb, user=user)

    text = cb.message.edit_text.call_args.args[0]
    assert f"#{sub1.id}" in text and f"#{sub2.id}" in text

    markup = cb.message.edit_text.call_args.kwargs["reply_markup"]
    flat = _flat_buttons(markup)

    for sub in (sub1, sub2):
        assert (
            f"🔑 Ключи #{sub.id}",
            SubCB(action="keys", sub_id=sub.id).pack(),
        ) in flat
        assert (
            f"🛒 Продлить #{sub.id}",
            BuyCB(action="extend", sub_id=sub.id).pack(),
        ) in flat


async def test_cb_open_my_expired_sub_has_no_extend_button(
    file_db, make_user, make_subscription, monkeypatch
):
    """Expired/inactive subs surface ONLY the 'Ключи #N' button.

    Rationale: the buy flow's ``cb_pick_action_extend`` rejects
    non-active subs, so showing «Продлить» would dead-end the user. The
    top «🆕 Купить новую подписку» button is the canonical way to buy
    when nothing is active.
    """
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        sub = await make_subscription(
            conn,
            user_id=user.id,
            expires_at=datetime.now(UTC) - timedelta(days=1),  # already expired
        )

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"up": 0, "down": 0})
    monkeypatch.setattr(my_sub_mod, "get_xui_client", AsyncMock(return_value=xui))

    cb = _mock_callback()
    await my_sub_mod.cb_open_my(cb, user=user)

    markup = cb.message.edit_text.call_args.kwargs["reply_markup"]
    flat = _flat_buttons(markup)
    extend_packed = BuyCB(action="extend", sub_id=sub.id).pack()
    keys_packed = SubCB(action="keys", sub_id=sub.id).pack()
    assert (f"🔑 Ключи #{sub.id}", keys_packed) in flat
    assert all(cb_data != extend_packed for _, cb_data in flat)
    # Buy-new still visible at the top.
    assert (
        "🆕 Купить новую подписку",
        BuyCB(action="new").pack(),
    ) in flat


async def test_cb_open_my_caps_at_5_and_shows_footer(
    file_db, make_user, make_subscription, monkeypatch
):
    """7 active subs → 5 visible cards + '… и ещё 2 подписки' footer.

    The keyboard must also reflect the cap — only the visible subs get
    per-sub button rows; the hidden ones are referenced solely by the
    footer line in the message body.
    """
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        ids: list[int] = []
        for i in range(7):
            s = await make_subscription(
                conn,
                user_id=user.id,
                xui_client_uuid=f"u{i}",
                xui_client_email=f"e{i}",
                # Different expires_at so sort is deterministic.
                expires_at=datetime.now(UTC) + timedelta(days=30 - i),
            )
            ids.append(s.id)

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"up": 0, "down": 0})
    monkeypatch.setattr(my_sub_mod, "get_xui_client", AsyncMock(return_value=xui))

    cb = _mock_callback()
    await my_sub_mod.cb_open_my(cb, user=user)

    text = cb.message.edit_text.call_args.args[0]
    assert "ещё" in text and "2" in text
    # Top 5 (latest expiry) appear in the body; the trailing two do not.
    visible_ids = ids[:5]
    hidden_ids = ids[5:]
    for sub_id in visible_ids:
        assert f"#{sub_id}" in text
    # The footer mentions «ещё 2 подписки» — but the per-card lines for
    # the hidden subs (their #N as a bold header) must NOT be present.
    for sub_id in hidden_ids:
        assert f"<b>Подписка #{sub_id}</b>" not in text

    markup = cb.message.edit_text.call_args.kwargs["reply_markup"]
    flat = _flat_buttons(markup)
    for sub_id in visible_ids:
        assert any(cb_data == SubCB(action="keys", sub_id=sub_id).pack() for _, cb_data in flat)
    for sub_id in hidden_ids:
        assert all(cb_data != SubCB(action="keys", sub_id=sub_id).pack() for _, cb_data in flat)


async def test_cb_open_my_active_sorted_by_expiry_desc(
    file_db, make_user, make_subscription, monkeypatch
):
    """Active subs are listed by ``expires_at`` DESC (newest expiry first)."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        # Insert in random order; the screen must re-order.
        s_short = await make_subscription(
            conn,
            user_id=user.id,
            xui_client_uuid="u_short",
            xui_client_email="e_short",
            expires_at=datetime.now(UTC) + timedelta(days=2),
        )
        s_long = await make_subscription(
            conn,
            user_id=user.id,
            xui_client_uuid="u_long",
            xui_client_email="e_long",
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        s_mid = await make_subscription(
            conn,
            user_id=user.id,
            xui_client_uuid="u_mid",
            xui_client_email="e_mid",
            expires_at=datetime.now(UTC) + timedelta(days=10),
        )

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"up": 0, "down": 0})
    monkeypatch.setattr(my_sub_mod, "get_xui_client", AsyncMock(return_value=xui))

    cb = _mock_callback()
    await my_sub_mod.cb_open_my(cb, user=user)

    text = cb.message.edit_text.call_args.args[0]
    long_pos = text.find(f"<b>Подписка #{s_long.id}</b>")
    mid_pos = text.find(f"<b>Подписка #{s_mid.id}</b>")
    short_pos = text.find(f"<b>Подписка #{s_short.id}</b>")
    assert -1 < long_pos < mid_pos < short_pos, (
        f"Expected long → mid → short order, got positions: "
        f"long={long_pos} mid={mid_pos} short={short_pos}"
    )


async def test_cb_open_my_active_before_inactive(
    file_db, make_user, make_subscription, monkeypatch
):
    """Active sub appears above an expired sib even when the expired row is newer."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        sub_expired = await make_subscription(
            conn,
            user_id=user.id,
            xui_client_uuid="u_exp",
            xui_client_email="e_exp",
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        sub_active = await make_subscription(
            conn,
            user_id=user.id,
            xui_client_uuid="u_act",
            xui_client_email="e_act",
            expires_at=datetime.now(UTC) + timedelta(days=10),
        )

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"up": 0, "down": 0})
    monkeypatch.setattr(my_sub_mod, "get_xui_client", AsyncMock(return_value=xui))

    cb = _mock_callback()
    await my_sub_mod.cb_open_my(cb, user=user)

    text = cb.message.edit_text.call_args.args[0]
    active_pos = text.find(f"<b>Подписка #{sub_active.id}</b>")
    expired_pos = text.find(f"<b>Подписка #{sub_expired.id}</b>")
    assert -1 < active_pos < expired_pos


async def test_cb_open_my_top_button_is_buy_new(
    file_db, make_user, make_subscription, monkeypatch
):
    """The very first inline button is always 'Купить новую' (sub_id=0).

    This invariant lets the user start a fresh purchase even when every
    existing subscription is expired — without going back to the main
    menu first.
    """
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        await make_subscription(conn, user_id=user.id)

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"up": 0, "down": 0})
    monkeypatch.setattr(my_sub_mod, "get_xui_client", AsyncMock(return_value=xui))

    cb = _mock_callback()
    await my_sub_mod.cb_open_my(cb, user=user)

    markup = cb.message.edit_text.call_args.kwargs["reply_markup"]
    first_row = markup.inline_keyboard[0]
    assert len(first_row) == 1
    assert first_row[0].text == "🆕 Купить новую подписку"
    assert first_row[0].callback_data == BuyCB(action="new").pack()


async def test_cb_open_my_xui_error(file_db, make_user, make_subscription, monkeypatch):
    """Panel error must NOT crash the card."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        await make_subscription(conn, user_id=user.id)

    xui = AsyncMock()
    xui.request_json = AsyncMock(side_effect=XuiError("down"))
    monkeypatch.setattr(my_sub_mod, "get_xui_client", AsyncMock(return_value=xui))

    cb = _mock_callback()
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
    """Smoke: 1 expired + 1 active still renders without crashing."""
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

    cb = _mock_callback()
    await my_sub_mod.cb_open_my(cb, user=user)
    cb.message.edit_text.assert_awaited()


# --------------------------------------------------------------------- #
# cb_resend_keys — kept from earlier phases
# --------------------------------------------------------------------- #


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


# --------------------------------------------------------------------- #
# Pure helpers — status / days / traffic
# --------------------------------------------------------------------- #


def test_format_status_lines():
    from app.db.repos.subscriptions import Subscription

    future = (datetime.now(UTC) + timedelta(days=5)).isoformat(sep=" ")
    past = (datetime.now(UTC) - timedelta(days=5)).isoformat(sep=" ")

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
    """Many extra subs → '… и ещё N' line in the body."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        # One active
        await make_subscription(conn, user_id=user.id)
        # 8 inactive (expired)
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

    cb = _mock_callback()
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


# --------------------------------------------------------------------- #
# Sort helper — direct unit tests
# --------------------------------------------------------------------- #


def _make_sub(sub_id: int, *, expires_at: datetime, status: str = "active",
              created_at: datetime | None = None):
    from app.db.repos.subscriptions import Subscription

    return Subscription(
        id=sub_id, user_id=1, xui_inbound_id=1, xui_client_uuid=f"u{sub_id}",
        xui_client_email=f"e{sub_id}", xui_sub_id=f"s{sub_id}",
        expires_at=expires_at.isoformat(sep=" "),
        created_at=(created_at or datetime.now(UTC)).isoformat(sep=" "),
        plan_id=None, status=status,
    )


def test_sort_subs_active_then_inactive():
    now = datetime.now(UTC)
    a1 = _make_sub(1, expires_at=now + timedelta(days=5))
    a2 = _make_sub(2, expires_at=now + timedelta(days=20))
    e3 = _make_sub(3, expires_at=now - timedelta(days=1), status="expired")
    r4 = _make_sub(4, expires_at=now - timedelta(days=2), status="revoked")
    ordered = my_sub_mod._sort_subs([e3, a1, r4, a2])
    # Active (sorted by expires_at DESC): a2 then a1.
    # Then inactive — order by created_at DESC (here both 'now') ties → id DESC.
    assert [s.id for s in ordered[:2]] == [a2.id, a1.id]
    # Inactive must come after; both present in any tie order.
    assert {s.id for s in ordered[2:]} == {e3.id, r4.id}
