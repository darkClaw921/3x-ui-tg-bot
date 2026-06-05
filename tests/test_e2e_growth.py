"""End-to-end growth-loop journeys: trial, referrals, gifts, auto-renewal.

Like :mod:`test_e2e_purchase`, these chain multiple handlers / jobs into one
scenario and assert the real SQLite state between steps; only the Telegram Bot
API and the 3x-ui client are mocked.

Covered journeys:

* **C. Trial** — activating the free trial creates an ``is_trial`` subscription;
  a second activation is refused (one trial per user).
* **E. Referrals** — invitee starts via ``/start ref_<inviter>`` (binds a
  ``pending`` referral); the invitee's first payment credits the inviter's
  wallet exactly once (a second payment does not re-pay); a self-referral is
  ignored.
* **F. Gifts** — a buyer pays a gift invoice → a gift code is minted (no
  subscription for the buyer); the recipient activates ``/start gift_<code>`` →
  a subscription is provisioned for the recipient and the code is ``redeemed``;
  a second redeem is blocked.
* **G. Native auto-renew** — first recurring charge provisions + flags
  ``auto_renew`` with the recurring charge id; a subsequent recurring charge
  extends the same subscription; cancelling from «Моя подписка» calls
  ``edit_user_star_subscription(is_canceled=True)`` and clears the flag.
* **H. Wallet-fallback auto-renew job** — a due wallet-fallback sub is charged
  once and extended; an empty wallet notifies without charging; a same-period
  re-run does not double-charge.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.handlers import start as start_module
from app.handlers.user import buy as buy_module
from app.handlers.user import trial as trial_handler
from app.services import billing
from app.services.inbounds import InboundOption


# --------------------------------------------------------------------------- #
# Shared helpers (mirroring the per-handler test fixtures).
# --------------------------------------------------------------------------- #


def _state(data: dict | None = None):
    s = AsyncMock()
    s.get_data = AsyncMock(return_value=data or {})
    s.update_data = AsyncMock()
    s.set_state = AsyncMock()
    s.clear = AsyncMock()
    return s


def _cmd(args: str | None):
    c = MagicMock()
    c.args = args
    return c


def _fake_xui() -> AsyncMock:
    xui = AsyncMock()
    xui.request_json = AsyncMock(
        return_value={
            "id": 1,
            "protocol": "vless",
            "port": 443,
            "streamSettings": json.dumps({"network": "tcp", "security": "none"}),
            "settings": json.dumps({"clients": []}),
        }
    )
    return xui


def _recurring_payment_msg(
    chat_id: int,
    charge_id: str,
    amount: int,
    payload: str,
    *,
    is_recurring: bool | None,
    is_first: bool | None,
    sub_expiration: int | None = None,
):
    msg = MagicMock()
    msg.chat = MagicMock(id=chat_id)
    msg.answer = AsyncMock()
    msg.successful_payment = MagicMock(
        telegram_payment_charge_id=charge_id,
        total_amount=amount,
        invoice_payload=payload,
        is_recurring=is_recurring,
        is_first_recurring=is_first,
        subscription_expiration_date=sub_expiration,
    )
    return msg


def _buy_payment_msg(chat_id: int, charge_id: str, amount: int, payload: str):
    return _recurring_payment_msg(
        chat_id, charge_id, amount, payload,
        is_recurring=None, is_first=None,
    )


@pytest.fixture(autouse=True)
def _clear_inbounds_cache():
    from app.services import inbounds as inb

    inb.clear_cache()
    yield
    inb.clear_cache()


# --------------------------------------------------------------------------- #
# C. Trial — activate once, second activation refused.
# --------------------------------------------------------------------------- #


async def test_e2e_trial_activate_then_second_refused(
    file_db, make_user, mock_bot, monkeypatch
):
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo

    monkeypatch.setattr(trial_handler.settings, "TRIAL_DAYS", 3, raising=False)
    monkeypatch.setattr(trial_handler.settings, "TRIAL_TRAFFIC_GB", 0, raising=False)

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=10)

    xui = _fake_xui()
    monkeypatch.setattr(trial_handler, "get_xui_client", AsyncMock(return_value=xui))
    monkeypatch.setattr(
        trial_handler, "list_user_inbounds",
        AsyncMock(return_value=[InboundOption(id=5, remark="DE", port=443, enabled=True)]),
    )

    # --- Step 1: open trial → single inbound auto-activates. ---
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.chat = MagicMock(id=10)
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await trial_handler.cb_open(cb, state, mock_bot, user=user, lang="ru")

    async with get_conn() as conn:
        subs = await subs_repo.list_for_user(conn, user.id)
        assert await subs_repo.has_trial(conn, user.id) is True
    assert len(subs) == 1
    assert subs[0].is_trial is True

    # --- Step 2: open trial again → refused (one trial per user). ---
    cb2 = MagicMock()
    cb2.message = MagicMock()
    cb2.message.chat = MagicMock(id=10)
    cb2.message.edit_text = AsyncMock()
    cb2.answer = AsyncMock()
    state2 = _state()
    await trial_handler.cb_open(cb2, state2, mock_bot, user=user, lang="ru")
    assert cb2.answer.call_args.kwargs.get("show_alert") is True

    async with get_conn() as conn:
        subs_after = await subs_repo.list_for_user(conn, user.id)
    assert len(subs_after) == 1  # still exactly one (no second trial)


# --------------------------------------------------------------------------- #
# E. Referrals — bind on /start, reward on first payment exactly once.
# --------------------------------------------------------------------------- #


async def test_e2e_referral_bind_and_reward_once(
    file_db, make_user, make_plan, mock_bot, monkeypatch
):
    from app.db.engine import get_conn
    from app.db.repos import referrals as referrals_repo
    from app.db.repos import wallet as wallet_repo

    monkeypatch.setattr(settings, "REFERRAL_BONUS_STARS", 25, raising=False)

    async with get_conn() as conn:
        inviter = await make_user(conn, tg_id=100)
        invitee = await make_user(conn, tg_id=200)
        plan = await make_plan(conn, price_stars=100, inbound_ids=[1])

    # --- Step 1: invitee follows /start ref_<inviter.tg_id> → pending bind. ---
    msg = MagicMock()
    msg.answer = AsyncMock()
    await start_module.cmd_start(
        msg, command=_cmd(f"ref_{inviter.tg_id}"), bot=mock_bot, user=invitee
    )
    async with get_conn() as conn:
        ref = await referrals_repo.get_by_referred(conn, invitee.id)
    assert ref is not None
    assert ref.referrer_id == inviter.id
    assert ref.status == "pending"

    # --- Step 2: invitee's first payment → inviter credited exactly once. ---
    xui = _fake_xui()
    monkeypatch.setattr(buy_module, "get_xui_client", AsyncMock(return_value=xui))
    payload = billing.build_invoice_payload(plan.id, None, 1)
    pay_msg = _buy_payment_msg(chat_id=200, charge_id="ref-pay-1", amount=100,
                              payload=payload)
    await buy_module.on_successful_payment(pay_msg, mock_bot, user=invitee)

    async with get_conn() as conn:
        assert await wallet_repo.balance(conn, inviter.id) == 25
        ref_after = await referrals_repo.get_by_referred(conn, invitee.id)
    assert ref_after.status == "rewarded"

    # --- Step 3: a second payment must NOT re-pay the inviter. ---
    pay_msg2 = _buy_payment_msg(chat_id=200, charge_id="ref-pay-2", amount=100,
                               payload=payload)
    await buy_module.on_successful_payment(pay_msg2, mock_bot, user=invitee)
    async with get_conn() as conn:
        assert await wallet_repo.balance(conn, inviter.id) == 25  # unchanged


async def test_e2e_referral_self_referral_ignored(
    file_db, make_user, mock_bot, monkeypatch
):
    """A user cannot invite themselves — no binding is created."""
    from app.db.engine import get_conn
    from app.db.repos import referrals as referrals_repo

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=300)

    msg = MagicMock()
    msg.answer = AsyncMock()
    await start_module.cmd_start(
        msg, command=_cmd(f"ref_{u.tg_id}"), bot=mock_bot, user=u
    )
    async with get_conn() as conn:
        ref = await referrals_repo.get_by_referred(conn, u.id)
    assert ref is None  # self-referral ignored


# --------------------------------------------------------------------------- #
# F. Gifts — buy mints a code, recipient redeems via deep-link, replay blocked.
# --------------------------------------------------------------------------- #


async def test_e2e_gift_buy_then_redeem(
    file_db, make_user, make_plan, mock_bot, monkeypatch
):
    from app.db.engine import get_conn
    from app.db.repos import gift_codes as gift_repo
    from app.db.repos import subscriptions as subs_repo

    async with get_conn() as conn:
        buyer = await make_user(conn, tg_id=100)
        recipient = await make_user(conn, tg_id=200)
        plan = await make_plan(conn, days=30, price_stars=120, inbound_ids=[5])

    xui = _fake_xui()
    monkeypatch.setattr(buy_module, "get_xui_client", AsyncMock(return_value=xui))
    # get_bot_username is consulted to build the activation deep-link in the DM.
    monkeypatch.setattr(buy_module, "get_bot_username", AsyncMock(return_value="thebot"))

    # --- Step 1: buyer pays a gift invoice → a code is minted, NO buyer sub. ---
    gift_payload = billing.build_gift_payload(plan.id, 5)
    gift_msg = _buy_payment_msg(chat_id=100, charge_id="gift-pay-1", amount=120,
                               payload=gift_payload)
    await buy_module.on_successful_payment(gift_msg, mock_bot, user=buyer)

    async with get_conn() as conn:
        buyer_subs = await subs_repo.list_for_user(conn, buyer.id)
        cur = await conn.execute(
            "SELECT code FROM gift_codes WHERE buyer_id=? AND status='active'",
            (buyer.id,),
        )
        row = await cur.fetchone()
    assert buyer_subs == []  # buyer is not provisioned a subscription
    assert row is not None
    code = row["code"]
    # The buyer got a DM carrying the minted code.
    gift_msg.answer.assert_awaited()
    assert code in gift_msg.answer.call_args.args[0]

    # --- Step 2: recipient activates /start gift_<code> → recipient sub + redeemed. ---
    monkeypatch.setattr(start_module, "get_xui_client", AsyncMock(return_value=xui))
    monkeypatch.setattr(start_module, "deliver_keys", AsyncMock())
    rmsg = MagicMock()
    rmsg.answer = AsyncMock()
    rmsg.chat = MagicMock(id=200)
    await start_module.cmd_start(
        rmsg, command=_cmd(f"gift_{code}"), bot=mock_bot, user=recipient
    )

    async with get_conn() as conn:
        recip_subs = await subs_repo.list_for_user(conn, recipient.id)
        gift_after = await gift_repo.get_by_code(conn, code)
    assert len(recip_subs) == 1  # recipient now has a subscription
    assert gift_after.status == "redeemed"
    start_module.deliver_keys.assert_awaited_once()

    # --- Step 3: a second redeem of the same code is blocked. ---
    rmsg2 = MagicMock()
    rmsg2.answer = AsyncMock()
    rmsg2.chat = MagicMock(id=200)
    start_module.deliver_keys.reset_mock()
    await start_module.cmd_start(
        rmsg2, command=_cmd(f"gift_{code}"), bot=mock_bot, user=recipient
    )
    async with get_conn() as conn:
        recip_subs_after = await subs_repo.list_for_user(conn, recipient.id)
    assert len(recip_subs_after) == 1  # no second subscription from a replay
    start_module.deliver_keys.assert_not_awaited()


# --------------------------------------------------------------------------- #
# G. Native Star auto-renew — first charge, subsequent charge, cancel.
# --------------------------------------------------------------------------- #


async def test_e2e_native_subscription_first_then_renew_then_cancel(
    file_db, make_user, make_plan, mock_bot, monkeypatch
):
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo
    from app.handlers.user import my_subscription as mysub_module
    from app.keyboards.user import SubCB

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=400)
        plan = await make_plan(conn, days=30, price_stars=100, inbound_ids=[1])

    xui = _fake_xui()
    monkeypatch.setattr(buy_module, "get_xui_client", AsyncMock(return_value=xui))

    sub_payload = billing.build_subscription_payload(plan.id, 1)

    # --- Step 1: first recurring charge → provision + auto_renew + charge id. ---
    first_msg = _recurring_payment_msg(
        chat_id=400, charge_id="sub-charge-1", amount=100, payload=sub_payload,
        is_recurring=True, is_first=True,
    )
    await buy_module.on_successful_payment(first_msg, mock_bot, user=user)

    async with get_conn() as conn:
        sub = await subs_repo.get_active_auto_renew_for(conn, user.id, plan.id)
    assert sub is not None
    assert sub.auto_renew is True
    assert sub.tg_sub_charge_id == "sub-charge-1"
    first_expiry = sub.expires_at

    # --- Step 2: a subsequent recurring charge extends the SAME subscription. ---
    next_period = int((datetime.now(UTC) + timedelta(days=60)).timestamp())
    second_msg = _recurring_payment_msg(
        chat_id=400, charge_id="sub-charge-2", amount=100, payload=sub_payload,
        is_recurring=True, is_first=False, sub_expiration=next_period,
    )
    await buy_module.on_successful_payment(second_msg, mock_bot, user=user)

    async with get_conn() as conn:
        sub_after = await subs_repo.get(conn, sub.id)
        all_subs = await subs_repo.list_for_user(conn, user.id)
    assert len(all_subs) == 1  # extended, not a new row
    assert sub_after.expires_at > first_expiry  # pushed forward

    # --- Step 3: cancel auto-renew from «Моя подписка». ---
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.chat = MagicMock(id=400)
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    cancel_bot = AsyncMock()
    cancel_bot.edit_user_star_subscription = AsyncMock(return_value=True)
    await mysub_module.cb_cancel_auto_renew(
        cb, SubCB(action="cancel_renew", sub_id=sub.id), cancel_bot,
        user=user, lang="ru",
    )

    cancel_bot.edit_user_star_subscription.assert_awaited_once()
    cancel_kwargs = cancel_bot.edit_user_star_subscription.call_args.kwargs
    assert cancel_kwargs["is_canceled"] is True
    assert cancel_kwargs["telegram_payment_charge_id"] == "sub-charge-1"

    async with get_conn() as conn:
        sub_final = await subs_repo.get(conn, sub.id)
    assert sub_final.auto_renew is False  # local flag cleared


# --------------------------------------------------------------------------- #
# H. Wallet-fallback auto-renew job — charge once, insufficient notifies, dedup.
# --------------------------------------------------------------------------- #


async def test_e2e_wallet_autorenew_job_charges_and_dedups(
    file_db, make_user, make_plan, make_subscription, mock_bot, monkeypatch
):
    from app.db.engine import get_conn
    from app.db.repos import payments as payments_repo
    from app.db.repos import subscriptions as subs_repo
    from app.db.repos import wallet as wallet_repo
    from app.services import wallet as wallet_service
    from app import scheduler as sch_module

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=500)
        plan = await make_plan(conn, price_stars=80, inbound_ids=[1])
        sub = await make_subscription(
            conn, user_id=user.id, plan_id=plan.id, xui_inbound_id=1,
            expires_at=datetime.now(UTC) + timedelta(hours=10),
        )
        # Wallet-fallback auto-renew (no tg charge id) + funded wallet.
        await subs_repo.set_auto_renew(conn, sub.id, True)
        await wallet_service.credit(conn, user.id, 200, type="topup", ref="seed")
        old_expiry = sub.expires_at

    xui = _fake_xui()
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=xui))

    new_dt = datetime.now(UTC) + timedelta(days=30)

    async def _fake_extend(*, conn, xui, user, plan, promo, inbound_id, extend_sub_id):
        await subs_repo.extend(conn, extend_sub_id, new_dt)
        return await subs_repo.get(conn, extend_sub_id)

    monkeypatch.setattr(
        sch_module.subs_service, "create_or_extend",
        AsyncMock(side_effect=_fake_extend),
    )

    # --- First run: charge 80, extend, synthetic payment, DM. ---
    await sch_module.auto_renew_job(mock_bot)
    async with get_conn() as conn:
        bal = await wallet_repo.balance(conn, user.id)
        fresh = await subs_repo.get(conn, sub.id)
        spend_txn = await wallet_repo.get_by_ref(
            conn, f"autorenew:{sub.id}:{old_expiry}"
        )
        pay = await payments_repo.get_by_charge_id(
            conn, f"wallet:autorenew:{spend_txn.id}"
        )
    assert bal == 120  # 200 - 80
    assert fresh.expires_at > old_expiry  # extended
    assert pay is not None  # synthetic payment recorded

    # --- Same-period re-run: the deterministic ref blocks a double charge. ---
    # Reset the stub so the second run keeps expires_at fixed (same ref).
    async def _fake_extend_noop(*, conn, xui, user, plan, promo, inbound_id, extend_sub_id):
        return await subs_repo.get(conn, extend_sub_id)

    # Move the sub's expiry back so it is due again, but keep the SAME period
    # string the first charge used → ref collision → no second debit.
    async with get_conn() as conn:
        await subs_repo.extend(
            conn, sub.id, datetime.now(UTC) + timedelta(hours=10)
        )
    # The new period differs, so to test dedup we re-run against the original
    # period by pinning expires_at back to old_expiry.
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE subscriptions SET expires_at=? WHERE id=?",
            (old_expiry, sub.id),
        )
        await conn.commit()
    monkeypatch.setattr(
        sch_module.subs_service, "create_or_extend",
        AsyncMock(side_effect=_fake_extend_noop),
    )
    await sch_module.auto_renew_job(mock_bot)
    async with get_conn() as conn:
        bal_after = await wallet_repo.balance(conn, user.id)
    assert bal_after == 120  # no second 80-Stars debit for the same period


async def test_e2e_wallet_autorenew_job_insufficient_balance_notifies(
    file_db, make_user, make_plan, make_subscription, mock_bot, monkeypatch
):
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo
    from app.db.repos import wallet as wallet_repo
    from app import scheduler as sch_module

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=600)
        plan = await make_plan(conn, price_stars=80, inbound_ids=[1])
        sub = await make_subscription(
            conn, user_id=user.id, plan_id=plan.id, xui_inbound_id=1,
            expires_at=datetime.now(UTC) + timedelta(hours=10),
        )
        await subs_repo.set_auto_renew(conn, sub.id, True)  # empty wallet

    xui = _fake_xui()
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=xui))

    await sch_module.auto_renew_job(mock_bot)

    async with get_conn() as conn:
        fresh = await subs_repo.get(conn, sub.id)
        bal = await wallet_repo.balance(conn, user.id)
    assert fresh.expires_at == sub.expires_at  # not extended
    assert bal == 0  # nothing charged
    mock_bot.send_message.assert_awaited()  # insufficient-balance DM
