"""Tests for :mod:`app.handlers.user.wallet` — the wallet screen + top-up."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

from app.handlers.user import wallet as wallet_handler
from app.keyboards.user import WalletCB


async def test_cb_open_shows_balance_and_history(file_db, make_user, monkeypatch):
    from app.db.engine import get_conn
    from app.services import wallet as wallet_service

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        await wallet_service.credit(conn, user.id, 250, type="topup", ref="t:1")
        await wallet_service.try_spend(conn, user.id, 50, ref="buy:1")

    monkeypatch.setattr(
        wallet_handler.settings, "WALLET_TOPUP_PRESETS", [50, 100], raising=False
    )

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await wallet_handler.cb_open(cb, user=user, lang="ru")

    text = cb.message.edit_text.call_args.args[0]
    assert "200" in text  # 250 - 50
    assert "Пополнение" in text  # topup history label (RU)
    cb.answer.assert_awaited()


async def test_cb_open_no_user_alerts(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await wallet_handler.cb_open(cb, user=None, lang="en")
    cb.message.edit_text.assert_not_awaited()
    assert cb.answer.call_args.kwargs.get("show_alert") is True


async def test_cb_open_empty_history(file_db, make_user):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await wallet_handler.cb_open(cb, user=user, lang="en")
    text = cb.message.edit_text.call_args.args[0]
    assert "No transactions yet" in text


async def test_cb_topup_shows_presets(file_db, monkeypatch):
    monkeypatch.setattr(
        wallet_handler.settings, "WALLET_TOPUP_PRESETS", [50, 100, 250], raising=False
    )
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await wallet_handler.cb_topup(cb, lang="en")
    # The keyboard exposes one button per preset + a back row.
    markup = cb.message.edit_text.call_args.kwargs["reply_markup"]
    flat = [b for row in markup.inline_keyboard for b in row]
    pick_buttons = [
        b for b in flat if WalletCB.unpack(b.callback_data).action == "pick"
    ]
    assert len(pick_buttons) == 3


async def test_cb_topup_no_presets(file_db, monkeypatch):
    monkeypatch.setattr(
        wallet_handler.settings, "WALLET_TOPUP_PRESETS", [], raising=False
    )
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await wallet_handler.cb_topup(cb, lang="en")
    text = cb.message.edit_text.call_args.args[0]
    assert "temporarily unavailable" in text


async def test_cb_pick_sends_topup_invoice(file_db):
    bot = AsyncMock()
    bot.send_invoice = AsyncMock(return_value=MagicMock())
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.chat = MagicMock(id=99)
    cb.answer = AsyncMock()
    await wallet_handler.cb_pick(
        cb, WalletCB(action="pick", stars=100), bot, lang="en"
    )
    bot.send_invoice.assert_awaited()
    kwargs = bot.send_invoice.call_args.kwargs
    assert kwargs["chat_id"] == 99
    assert json.loads(kwargs["payload"]) == {"k": "topup", "t": 100}


async def test_cb_pick_zero_stars_rejected(file_db):
    bot = AsyncMock()
    bot.send_invoice = AsyncMock()
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.chat = MagicMock(id=1)
    cb.answer = AsyncMock()
    await wallet_handler.cb_pick(cb, WalletCB(action="pick", stars=0), bot, lang="en")
    bot.send_invoice.assert_not_awaited()
    assert cb.answer.call_args.kwargs.get("show_alert") is True
