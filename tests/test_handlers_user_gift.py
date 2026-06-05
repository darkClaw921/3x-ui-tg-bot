"""Tests for :mod:`app.handlers.user.gift` — gift redemption via menu."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.handlers.user import gift as gift_handler
from app.services import gifts as gifts_service
from app.states.user import GiftRedeem


async def test_cb_redeem_enters_state(file_db, make_user):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = AsyncMock()
    await gift_handler.cb_redeem(cb, state, user=user, lang="ru")
    state.set_state.assert_awaited_with(GiftRedeem.waiting_code)


async def test_cb_redeem_no_user_alerts(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = AsyncMock()
    await gift_handler.cb_redeem(cb, state, user=None, lang="en")
    assert cb.answer.call_args.kwargs.get("show_alert") is True


async def test_msg_code_happy_path(file_db, make_user, make_plan, monkeypatch):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        buyer = await make_user(conn, tg_id=1)
        recip = await make_user(conn, tg_id=2)
        plan = await make_plan(conn, days=30, inbound_ids=[5])
        gift = await gifts_service.make_gift_code(
            conn, plan_id=plan.id, inbound_id=5, buyer_id=buyer.id
        )

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"id": "uuid", "email": "e"})
    monkeypatch.setattr(gift_handler, "get_xui_client", AsyncMock(return_value=xui))
    monkeypatch.setattr(gift_handler, "deliver_keys", AsyncMock())
    monkeypatch.setattr(gift_handler, "notify_gift_buyer", AsyncMock())

    bot = AsyncMock()
    state = AsyncMock()
    msg = AsyncMock()
    msg.chat = MagicMock(id=2)
    msg.text = gift.code.lower()
    await gift_handler.msg_code(msg, state, bot, user=recip, lang="ru")

    gift_handler.deliver_keys.assert_awaited_once()
    gift_handler.notify_gift_buyer.assert_awaited_once()
    state.clear.assert_awaited()


async def test_msg_code_not_found(file_db, make_user, monkeypatch):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        recip = await make_user(conn, tg_id=2)

    monkeypatch.setattr(
        gift_handler, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    bot = AsyncMock()
    state = AsyncMock()
    msg = AsyncMock()
    msg.chat = MagicMock(id=2)
    msg.text = "GIFT-NONE0000"
    await gift_handler.msg_code(msg, state, bot, user=recip, lang="ru")
    # stays in state (no clear), shows error.
    state.clear.assert_not_awaited()
    msg.answer.assert_awaited()


async def test_msg_code_already_redeemed(file_db, make_user, make_plan, monkeypatch):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        buyer = await make_user(conn, tg_id=1)
        recip = await make_user(conn, tg_id=2)
        plan = await make_plan(conn, days=30, inbound_ids=[5])
        gift = await gifts_service.make_gift_code(
            conn, plan_id=plan.id, inbound_id=5, buyer_id=buyer.id
        )

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"id": "uuid", "email": "e"})
    monkeypatch.setattr(gift_handler, "get_xui_client", AsyncMock(return_value=xui))
    monkeypatch.setattr(gift_handler, "deliver_keys", AsyncMock())
    monkeypatch.setattr(gift_handler, "notify_gift_buyer", AsyncMock())

    bot = AsyncMock()
    state = AsyncMock()
    msg = AsyncMock()
    msg.chat = MagicMock(id=2)
    msg.text = gift.code
    # First redeem succeeds.
    await gift_handler.msg_code(msg, state, bot, user=recip, lang="ru")
    # Second redeem of same code → not_active path.
    state2 = AsyncMock()
    msg2 = AsyncMock()
    msg2.chat = MagicMock(id=2)
    msg2.text = gift.code
    await gift_handler.msg_code(msg2, state2, bot, user=recip, lang="ru")
    state2.clear.assert_not_awaited()
    msg2.answer.assert_awaited()


async def test_notify_gift_buyer_dms(file_db, make_user, make_plan):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        buyer = await make_user(conn, tg_id=1)
        plan = await make_plan(conn, days=30, inbound_ids=[5])
        gift = await gifts_service.make_gift_code(
            conn, plan_id=plan.id, inbound_id=5, buyer_id=buyer.id
        )
    bot = AsyncMock()
    await gift_handler.notify_gift_buyer(bot, gift)
    assert bot.send_message.await_count == 1
    assert bot.send_message.await_args.args[0] == buyer.tg_id
