"""End-to-end purchase journeys for :mod:`app.handlers.user.buy`.

These tests differ from the per-handler unit tests in ``test_handlers_user_buy``
by stringing **several handlers together into one user journey** and asserting
the **real SQLite state** between steps (via ``get_conn()`` + repo functions).
Only the external boundaries are mocked:

* the Telegram Bot API (an ``AsyncMock`` ``bot`` whose ``send_message`` /
  ``send_photo`` / ``send_invoice`` / ``answer_pre_checkout_query`` are recorded),
* the 3x-ui client (a fake ``XuiClient`` whose ``request_json`` answers the
  ``add_client`` / ``get`` / ``list`` calls the provisioning + key-delivery path
  makes).

Everything in between — middleware-free direct handler entry points, services,
repos and the DB — runs for real.

Covered journeys (see the file-level test names):

* **A. New-user purchase** — open buy → pick a single-inbound plan (auto-skip to
  confirm) → confirm (``send_invoice``) → pre_checkout (``ok=True``) →
  successful_payment → an ``active`` subscription + a ``payments`` row exist and
  the keys (vless / QR / subscription URL / ``happ://import/`` guide) were
  delivered.
* **B. Payment idempotency** — replaying the same ``successful_payment``
  (identical ``telegram_payment_charge_id``) does not create a second
  subscription or payment.
* **D. Wallet** — a ``kind='topup'`` payment credits the balance exactly once
  (replay-safe), then paying a plan from balance debits it once and provisions a
  subscription.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.repos.users import User
from app.handlers.user import buy as buy_module
from app.keyboards.user import BuyCB
from app.services import billing
from app.services.inbounds import InboundOption


# --------------------------------------------------------------------------- #
# Helpers — shared with the other e2e modules' patterns.
# --------------------------------------------------------------------------- #


def _user_obj(user_id: int = 1, tg_id: int = 1, is_admin: bool = False) -> User:
    return User(
        id=user_id, tg_id=tg_id, username="u", first_name="X",
        is_admin=is_admin, created_at="2025",
    )


def _state(data: dict | None = None):
    s = AsyncMock()
    s.get_data = AsyncMock(return_value=data or {})
    s.update_data = AsyncMock()
    s.set_state = AsyncMock()
    s.clear = AsyncMock()
    return s


def _cb(chat_id: int = 1, cb_id: str = "cbq"):
    cb = MagicMock()
    cb.id = cb_id
    cb.message = MagicMock()
    cb.message.chat = MagicMock(id=chat_id)
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _stub_inbounds(*ids: int) -> list[InboundOption]:
    return [
        InboundOption(id=i, remark=f"srv-{i}", port=443 + i, enabled=True)
        for i in ids
    ]


def _fake_xui() -> AsyncMock:
    """An xui client that answers the provisioning + key-delivery round-trips.

    ``add_client`` POSTs to ``/panel/api/clients/add`` and reads the returned
    UUID/email; ``get_inbound`` (used by ``deliver_keys``) GETs an inbound. A
    single ``request_json`` that returns a permissive dict satisfies both — the
    real link builder only needs a non-empty inbound to render a vless URI, and
    falls back gracefully if it can't.
    """
    xui = AsyncMock()
    xui.request_json = AsyncMock(
        return_value={
            "id": 1,
            "protocol": "vless",
            "port": 443,
            "streamSettings": json.dumps(
                {"network": "tcp", "security": "none"}
            ),
            "settings": json.dumps({"clients": []}),
        }
    )
    return xui


@pytest.fixture(autouse=True)
def _clear_inbounds_cache():
    from app.services import inbounds as inb

    inb.clear_cache()
    yield
    inb.clear_cache()


def _make_payment_msg(chat_id: int, charge_id: str, amount: int, payload: str):
    """Build a ``Message`` stand-in carrying a ``successful_payment``.

    The ``successful_payment`` mock exposes every attribute the handler reads:
    ``telegram_payment_charge_id`` / ``total_amount`` / ``invoice_payload`` plus
    the recurring-subscription flags (``is_recurring`` / ``is_first_recurring`` /
    ``subscription_expiration_date``) defaulted to a one-off (non-recurring)
    purchase so the buy branch is taken.
    """
    msg = MagicMock()
    msg.chat = MagicMock(id=chat_id)
    msg.answer = AsyncMock()
    msg.successful_payment = MagicMock(
        telegram_payment_charge_id=charge_id,
        total_amount=amount,
        invoice_payload=payload,
        is_recurring=None,
        is_first_recurring=None,
        subscription_expiration_date=None,
    )
    return msg


# --------------------------------------------------------------------------- #
# A. New-user purchase journey (open → pick → confirm → pre_checkout → pay).
# --------------------------------------------------------------------------- #


async def test_e2e_new_user_purchase_full_journey(
    file_db, make_user, make_plan, mock_bot, monkeypatch
):
    """Walk a brand-new user through the whole buy flow and verify DB + delivery."""
    from app.db.engine import get_conn
    from app.db.repos import payments as payments_repo
    from app.db.repos import subscriptions as subs_repo

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        plan = await make_plan(conn, title="1 month", days=30, price_stars=150,
                               inbound_ids=[1])

    xui = _fake_xui()
    monkeypatch.setattr(buy_module, "get_xui_client", AsyncMock(return_value=xui))
    monkeypatch.setattr(
        buy_module, "list_user_inbounds",
        AsyncMock(return_value=_stub_inbounds(1)),
    )

    # --- Step 1: open the buy screen (no active sub → straight to plan list). ---
    cb_open = _cb(chat_id=1)
    state = _state()
    await buy_module.cb_open(cb_open, state, user=user)
    cb_open.message.edit_text.assert_awaited()

    # --- Step 2: pick the (single-inbound) plan → auto-skips to confirm. ---
    cb_pick = _cb(chat_id=1)
    await buy_module.cb_pick_plan(
        cb_pick, BuyCB(action="plan", plan_id=plan.id), state, user=user
    )
    pinned = state.update_data.await_args.kwargs
    assert pinned["inbound_id"] == 1  # single inbound auto-pinned

    # --- Step 3: confirm → an invoice is sent for the right price/inbound. ---
    cb_confirm = _cb(chat_id=1)
    await buy_module.cb_confirm(
        cb_confirm,
        BuyCB(action="confirm", plan_id=plan.id, promo_id=0, inbound_id=1),
        state,
        mock_bot,
        user=user,
    )
    mock_bot.send_invoice.assert_awaited_once()
    inv_kwargs = mock_bot.send_invoice.call_args.kwargs
    assert inv_kwargs["currency"] == "XTR"
    assert inv_kwargs["prices"][0].amount == 150
    invoice_payload = inv_kwargs["payload"]
    assert json.loads(invoice_payload)["i"] == 1

    # --- Step 4: pre_checkout on the real invoice payload → ok=True. ---
    q = MagicMock()
    q.id = "pcq"
    q.from_user = MagicMock(id=user.tg_id)
    q.invoice_payload = invoice_payload
    await buy_module.on_pre_checkout(q, mock_bot)
    assert mock_bot.answer_pre_checkout_query.call_args.kwargs["ok"] is True

    # No subscription should exist yet — only the invoice has been sent.
    async with get_conn() as conn:
        assert await subs_repo.get_active_for_user(conn, user.id) is None

    # --- Step 5: successful_payment → provision + record + deliver keys. ---
    msg = _make_payment_msg(chat_id=1, charge_id="charge-A1", amount=150,
                            payload=invoice_payload)
    await buy_module.on_successful_payment(msg, mock_bot, user=user)

    # DB: an active subscription + a payment row tied to it.
    async with get_conn() as conn:
        active = await subs_repo.get_active_for_user(conn, user.id)
        rec = await payments_repo.get_by_charge_id(conn, "charge-A1")
    assert active is not None
    assert active.status == "active"
    assert active.plan_id == plan.id
    assert rec is not None
    assert rec.stars_amount == 150
    assert rec.subscription_id == active.id

    # Delivery: vless summary + QR photo + subscription URL message + guide.
    assert mock_bot.send_message.await_count >= 2
    mock_bot.send_photo.assert_awaited()  # QR
    sent_texts = [c.args[1] for c in mock_bot.send_message.await_args_list]
    blob = "\n".join(sent_texts)
    assert active.xui_sub_id in blob  # subscription URL carries the sub id
    assert "happ://import/" in blob  # Happ deep-link guide present


# --------------------------------------------------------------------------- #
# B. Payment idempotency — a replayed successful_payment is a no-op.
# --------------------------------------------------------------------------- #


async def test_e2e_payment_replay_is_idempotent(
    file_db, make_user, make_plan, mock_bot, monkeypatch
):
    """Delivering the same charge twice must not create a 2nd sub / payment."""
    from app.db.engine import get_conn
    from app.db.repos import payments as payments_repo
    from app.db.repos import subscriptions as subs_repo

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=2)
        plan = await make_plan(conn, price_stars=100, inbound_ids=[1])

    xui = _fake_xui()
    monkeypatch.setattr(buy_module, "get_xui_client", AsyncMock(return_value=xui))

    payload = billing.build_invoice_payload(plan.id, None, 1)
    msg = _make_payment_msg(chat_id=2, charge_id="charge-B1", amount=100,
                            payload=payload)

    # First delivery — creates everything.
    await buy_module.on_successful_payment(msg, mock_bot, user=user)
    async with get_conn() as conn:
        subs_after_first = await subs_repo.list_for_user(conn, user.id)
        pays_after_first = await payments_repo.list_for_user(conn, user.id)
    assert len(subs_after_first) == 1
    assert len(pays_after_first) == 1

    # Telegram redelivers the exact same update — must short-circuit.
    xui.request_json.reset_mock()
    await buy_module.on_successful_payment(msg, mock_bot, user=user)
    async with get_conn() as conn:
        subs_after_second = await subs_repo.list_for_user(conn, user.id)
        pays_after_second = await payments_repo.list_for_user(conn, user.id)
    assert len(subs_after_second) == 1  # no second subscription
    assert len(pays_after_second) == 1  # no second payment
    # The replay short-circuits before touching the panel.
    xui.request_json.assert_not_called()


# --------------------------------------------------------------------------- #
# D. Wallet journey — top-up credits once, then pay-from-balance debits once.
# --------------------------------------------------------------------------- #


async def test_e2e_wallet_topup_then_pay_from_balance(
    file_db, make_user, make_plan, mock_bot, monkeypatch
):
    """Top-up via successful_payment, then provision a plan from the balance."""
    from app.db.engine import get_conn
    from app.db.repos import payments as payments_repo
    from app.db.repos import subscriptions as subs_repo
    from app.db.repos import wallet as wallet_repo

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=3)
        plan = await make_plan(conn, price_stars=60, inbound_ids=[1])

    xui = _fake_xui()
    monkeypatch.setattr(buy_module, "get_xui_client", AsyncMock(return_value=xui))
    monkeypatch.setattr(
        buy_module, "list_user_inbounds",
        AsyncMock(return_value=_stub_inbounds(1)),
    )

    # --- Step 1: top-up 200 Stars via a kind='topup' successful_payment. ---
    topup_payload = billing.build_topup_payload(200)
    topup_msg = _make_payment_msg(chat_id=3, charge_id="topup-D1", amount=200,
                                  payload=topup_payload)
    await buy_module.on_successful_payment(topup_msg, mock_bot, user=user)

    async with get_conn() as conn:
        assert await wallet_repo.balance(conn, user.id) == 200

    # Replay the top-up → balance stays 200 (idempotent on charge id + ref).
    await buy_module.on_successful_payment(topup_msg, mock_bot, user=user)
    async with get_conn() as conn:
        assert await wallet_repo.balance(conn, user.id) == 200
        topup_txns = await wallet_repo.list_for_user(conn, user.id)
    assert len(topup_txns) == 1  # credited exactly once

    # --- Step 2: pay a 60-Stars plan from the balance. ---
    cb = _cb(chat_id=3, cb_id="cbq-balance")
    state = _state()
    data = BuyCB(action="balance", plan_id=plan.id, promo_id=0, inbound_id=1, sub_id=0)
    await buy_module.cb_pay_from_balance(cb, data, state, mock_bot, user=user)

    async with get_conn() as conn:
        balance = await wallet_repo.balance(conn, user.id)
        active = await subs_repo.get_active_for_user(conn, user.id)
        pays = await payments_repo.list_for_user(conn, user.id)
    assert balance == 140  # 200 - 60 debited once
    assert active is not None  # subscription provisioned from balance
    assert active.status == "active"
    # One real top-up payment + one synthetic wallet payment for the buy.
    assert len(pays) == 2
