"""Tests for :mod:`app.handlers.user.buy`."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.repos.users import User
from app.handlers.user import buy as buy_module
from app.keyboards.user import BuyCB
from app.xui import XuiError


def _user(user_id=1, tg_id=1, is_admin=False):
    return User(
        id=user_id, tg_id=tg_id, username="u", first_name="X",
        is_admin=is_admin, created_at="2025",
    )


def _state():
    """Build a mock FSMContext."""
    s = AsyncMock()
    s.get_data = AsyncMock(return_value={})
    s.update_data = AsyncMock()
    s.set_state = AsyncMock()
    s.clear = AsyncMock()
    return s


async def test_cb_open_no_plans(file_db, mock_bot):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await buy_module.cb_open(cb, state)
    cb.message.edit_text.assert_awaited()


async def test_cb_open_with_plans(file_db, make_plan, mock_bot):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        await make_plan(conn)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await buy_module.cb_open(cb, state)
    cb.message.edit_text.assert_awaited()


async def test_cb_pick_plan_with_existing_promo_in_state(
    file_db, make_plan, make_promo
):
    """Picking a plan preserves a promo_id already in FSM."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        plan = await make_plan(conn)
        promo = await make_promo(conn, code="X")

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"promo_id": promo.id})
    callback_data = BuyCB(action="plan", plan_id=plan.id)
    await buy_module.cb_pick_plan(cb, callback_data, state)
    cb.message.edit_text.assert_awaited()


async def test_cb_pick_plan_unknown_or_inactive(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    cb_data = BuyCB(action="plan", plan_id=999)
    await buy_module.cb_pick_plan(cb, cb_data, state)
    cb.answer.assert_awaited_once()


async def test_cb_apply_promo(file_db, make_plan):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        plan = await make_plan(conn)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await buy_module.cb_apply_promo(cb, BuyCB(action="apply_promo", plan_id=plan.id), state)
    cb.message.edit_text.assert_awaited()


async def test_msg_promo_code_valid(file_db, make_plan, make_promo):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        plan = await make_plan(conn)
        promo = await make_promo(conn, code="GOOD")
        user = _user(user_id=1)

    msg = MagicMock()
    msg.text = "good"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"plan_id": plan.id})

    # Insert user into DB so promo's "already redeemed" check works.
    async with get_conn() as conn:
        from app.db.repos.users import create

        u = await create(conn, tg_id=user.tg_id, username="u", first_name="X")

    await buy_module.msg_promo_code(msg, state, user=u)
    msg.answer.assert_awaited()
    state.update_data.assert_awaited()


async def test_msg_promo_code_invalid(file_db, make_plan):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        plan = await make_plan(conn)
        from app.db.repos.users import create as ucreate

        u = await ucreate(conn, tg_id=1, username="u", first_name="X")

    msg = MagicMock()
    msg.text = "bogus"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"plan_id": plan.id})
    await buy_module.msg_promo_code(msg, state, user=u)
    msg.answer.assert_awaited()


async def test_msg_promo_code_no_user(file_db):
    msg = MagicMock()
    msg.text = "x"
    msg.answer = AsyncMock()
    state = _state()
    await buy_module.msg_promo_code(msg, state, user=None)
    msg.answer.assert_awaited()


async def test_msg_promo_code_plan_unavailable(file_db, make_plan):
    """If the plan got deactivated between selection and promo input."""
    from app.db.engine import get_conn
    from app.db.repos import plans as plans_repo
    from app.db.repos.users import create as ucreate

    async with get_conn() as conn:
        plan = await make_plan(conn)
        await plans_repo.deactivate(conn, plan.id)
        u = await ucreate(conn, tg_id=1, username="u", first_name="X")

    msg = MagicMock()
    msg.text = "any"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"plan_id": plan.id})
    await buy_module.msg_promo_code(msg, state, user=u)
    state.clear.assert_awaited()


async def test_cb_confirm_sends_invoice(file_db, make_plan, mock_bot):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        plan = await make_plan(conn, price_stars=42)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.chat = MagicMock(id=999)
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await buy_module.cb_confirm(
        cb, BuyCB(action="confirm", plan_id=plan.id, promo_id=0), state, mock_bot
    )
    mock_bot.send_invoice.assert_awaited()
    kwargs = mock_bot.send_invoice.call_args.kwargs
    assert kwargs["currency"] == "XTR"
    assert kwargs["prices"][0].amount == 42


async def test_cb_confirm_invalid_plan(file_db, mock_bot):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.chat = MagicMock(id=1)
    cb.answer = AsyncMock()
    state = _state()
    await buy_module.cb_confirm(
        cb, BuyCB(action="confirm", plan_id=999), state, mock_bot
    )
    cb.answer.assert_awaited()
    mock_bot.send_invoice.assert_not_awaited()


async def test_cb_confirm_no_chat_id(file_db, make_plan, mock_bot):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        plan = await make_plan(conn)

    cb = MagicMock()
    cb.message = None
    cb.answer = AsyncMock()
    state = _state()
    await buy_module.cb_confirm(
        cb, BuyCB(action="confirm", plan_id=plan.id), state, mock_bot
    )
    cb.answer.assert_awaited()
    mock_bot.send_invoice.assert_not_awaited()


async def test_pre_checkout_ok(file_db, make_plan, mock_bot):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        plan = await make_plan(conn)

    payload = json.dumps({"plan_id": plan.id, "promo_id": None})
    q = MagicMock()
    q.id = "qid"
    q.invoice_payload = payload
    await buy_module.on_pre_checkout(q, mock_bot)
    mock_bot.answer_pre_checkout_query.assert_awaited()
    kwargs = mock_bot.answer_pre_checkout_query.call_args.kwargs
    assert kwargs["ok"] is True


async def test_pre_checkout_bad_payload(file_db, mock_bot):
    q = MagicMock()
    q.id = "qid"
    q.invoice_payload = "{not-json"
    await buy_module.on_pre_checkout(q, mock_bot)
    kwargs = mock_bot.answer_pre_checkout_query.call_args.kwargs
    assert kwargs["ok"] is False


async def test_pre_checkout_plan_deactivated(file_db, make_plan, mock_bot):
    from app.db.engine import get_conn
    from app.db.repos import plans as plans_repo

    async with get_conn() as conn:
        plan = await make_plan(conn)
        await plans_repo.deactivate(conn, plan.id)
    payload = json.dumps({"plan_id": plan.id, "promo_id": None})
    q = MagicMock()
    q.id = "qid"
    q.invoice_payload = payload
    await buy_module.on_pre_checkout(q, mock_bot)
    kwargs = mock_bot.answer_pre_checkout_query.call_args.kwargs
    assert kwargs["ok"] is False


async def test_pre_checkout_promo_invalid(file_db, make_plan, make_promo, mock_bot):
    from app.db.engine import get_conn
    from app.db.repos import promos as promos_repo

    async with get_conn() as conn:
        plan = await make_plan(conn)
        promo = await make_promo(conn, code="X")
        await promos_repo.deactivate(conn, promo.id)
    payload = json.dumps({"plan_id": plan.id, "promo_id": promo.id})
    q = MagicMock()
    q.id = "qid"
    q.invoice_payload = payload
    await buy_module.on_pre_checkout(q, mock_bot)
    kwargs = mock_bot.answer_pre_checkout_query.call_args.kwargs
    assert kwargs["ok"] is False


async def test_successful_payment_happy_path(
    file_db, make_user, make_plan, mock_bot, monkeypatch
):
    from app.db.engine import get_conn
    from app.db.repos import payments as payments_repo

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        plan = await make_plan(conn)

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"id": "u"})
    monkeypatch.setattr(buy_module, "get_xui_client", AsyncMock(return_value=xui))
    # Patch deliver_keys to skip the real inbound fetch.
    monkeypatch.setattr(buy_module, "deliver_keys", AsyncMock())

    payload = json.dumps({"plan_id": plan.id, "promo_id": None})
    msg = MagicMock()
    msg.chat = MagicMock(id=1)
    msg.answer = AsyncMock()
    msg.successful_payment = MagicMock(
        telegram_payment_charge_id="charge-1",
        total_amount=plan.price_stars,
        invoice_payload=payload,
    )
    await buy_module.on_successful_payment(msg, mock_bot, user=user)
    # Payment recorded.
    async with get_conn() as conn:
        rec = await payments_repo.get_by_charge_id(conn, "charge-1")
    assert rec is not None
    assert rec.stars_amount == plan.price_stars


async def test_successful_payment_idempotent(
    file_db, make_user, make_plan, mock_bot, monkeypatch
):
    """A duplicate charge_id is short-circuited (no second sub)."""
    from app.db.engine import get_conn
    from app.db.repos import payments as payments_repo

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        plan = await make_plan(conn)
        await payments_repo.create(
            conn,
            user_id=user.id,
            subscription_id=None,
            telegram_charge_id="dup-charge",
            stars_amount=10,
            plan_id=plan.id,
            promo_id=None,
        )

    xui = AsyncMock()
    monkeypatch.setattr(buy_module, "get_xui_client", AsyncMock(return_value=xui))
    monkeypatch.setattr(buy_module, "deliver_keys", AsyncMock())

    payload = json.dumps({"plan_id": plan.id, "promo_id": None})
    msg = MagicMock()
    msg.chat = MagicMock(id=1)
    msg.answer = AsyncMock()
    msg.successful_payment = MagicMock(
        telegram_payment_charge_id="dup-charge",
        total_amount=20,
        invoice_payload=payload,
    )
    await buy_module.on_successful_payment(msg, mock_bot, user=user)
    # No new payment row added.
    async with get_conn() as conn:
        cur = await conn.execute(
            "SELECT COUNT(*) FROM payments WHERE telegram_charge_id='dup-charge'"
        )
        n = (await cur.fetchone())[0]
    assert n == 1
    # xui.request_json should not have been called (we short-circuited).
    xui.request_json.assert_not_called()


async def test_successful_payment_bad_payload(
    file_db, make_user, mock_bot, monkeypatch
):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)

    msg = MagicMock()
    msg.chat = MagicMock(id=1)
    msg.answer = AsyncMock()
    msg.successful_payment = MagicMock(
        telegram_payment_charge_id="c1",
        total_amount=10,
        invoice_payload="{garbage",
    )
    await buy_module.on_successful_payment(msg, mock_bot, user=user)
    msg.answer.assert_awaited()


async def test_successful_payment_no_user(file_db, mock_bot):
    msg = MagicMock()
    msg.successful_payment = MagicMock()
    await buy_module.on_successful_payment(msg, mock_bot, user=None)
    # Should silently return.


async def test_successful_payment_xui_fail_records_payment(
    file_db, make_user, make_plan, mock_bot, monkeypatch
):
    """If xui.add_client fails, payment is still recorded with subscription_id=None."""
    from app.db.engine import get_conn
    from app.db.repos import payments as payments_repo

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        plan = await make_plan(conn)

    xui = AsyncMock()
    xui.request_json = AsyncMock(side_effect=XuiError("down"))
    monkeypatch.setattr(buy_module, "get_xui_client", AsyncMock(return_value=xui))
    monkeypatch.setattr(buy_module, "deliver_keys", AsyncMock())

    payload = json.dumps({"plan_id": plan.id, "promo_id": None})
    msg = MagicMock()
    msg.chat = MagicMock(id=1)
    msg.answer = AsyncMock()
    msg.successful_payment = MagicMock(
        telegram_payment_charge_id="c-xui-fail",
        total_amount=plan.price_stars,
        invoice_payload=payload,
    )
    await buy_module.on_successful_payment(msg, mock_bot, user=user)
    async with get_conn() as conn:
        rec = await payments_repo.get_by_charge_id(conn, "c-xui-fail")
    assert rec is not None
    assert rec.subscription_id is None
    # User got the "we'll activate manually" message.
    msg.answer.assert_awaited()


async def test_successful_payment_with_promo_redemption(
    file_db, make_user, make_plan, make_promo, mock_bot, monkeypatch
):
    """successful_payment + promo → promo redeemed via service."""
    from app.db.engine import get_conn
    from app.db.repos import promos as promos_repo

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        plan = await make_plan(conn)
        promo = await make_promo(conn, code="SAVE", max_uses=10)

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"id": "u"})
    monkeypatch.setattr(buy_module, "get_xui_client", AsyncMock(return_value=xui))
    monkeypatch.setattr(buy_module, "deliver_keys", AsyncMock())

    payload = json.dumps({"plan_id": plan.id, "promo_id": promo.id})
    msg = MagicMock()
    msg.chat = MagicMock(id=1)
    msg.answer = AsyncMock()
    msg.successful_payment = MagicMock(
        telegram_payment_charge_id="c-prm",
        total_amount=plan.price_stars,
        invoice_payload=payload,
    )
    await buy_module.on_successful_payment(msg, mock_bot, user=user)
    async with get_conn() as conn:
        refreshed = await promos_repo.get(conn, promo.id)
    assert refreshed.used_count == 1


async def test_pre_checkout_missing_plan(file_db, mock_bot):
    """pre_checkout with a non-existent plan_id returns ok=False."""
    payload = json.dumps({"plan_id": 9999, "promo_id": None})
    q = MagicMock()
    q.id = "qid"
    q.invoice_payload = payload
    await buy_module.on_pre_checkout(q, mock_bot)
    kwargs = mock_bot.answer_pre_checkout_query.call_args.kwargs
    assert kwargs["ok"] is False


async def test_successful_payment_plan_deleted(
    file_db, make_user, mock_bot, monkeypatch
):
    """If plan referenced in payload is missing → record payment, alert user."""
    from app.db.engine import get_conn
    from app.db.repos import payments as payments_repo

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)

    msg = MagicMock()
    msg.chat = MagicMock(id=1)
    msg.answer = AsyncMock()
    msg.successful_payment = MagicMock(
        telegram_payment_charge_id="c-noplan",
        total_amount=20,
        invoice_payload=json.dumps({"plan_id": 999, "promo_id": None}),
    )
    await buy_module.on_successful_payment(msg, mock_bot, user=user)
    async with get_conn() as conn:
        rec = await payments_repo.get_by_charge_id(conn, "c-noplan")
    assert rec is not None
    msg.answer.assert_awaited()
