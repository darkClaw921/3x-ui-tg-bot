"""Tests for :mod:`app.services.referrals`."""

from __future__ import annotations

from unittest.mock import AsyncMock


from app.db.repos import referrals as referrals_repo
from app.db.repos import wallet as wallet_repo
from app.services import referrals as referrals_service


def test_parse_ref_arg():
    assert referrals_service.parse_ref_arg("ref_123") == 123
    assert referrals_service.parse_ref_arg("ref_0") is None
    assert referrals_service.parse_ref_arg("ref_abc") is None
    assert referrals_service.parse_ref_arg("gift_x") is None
    assert referrals_service.parse_ref_arg("") is None
    assert referrals_service.parse_ref_arg(None) is None
    assert referrals_service.parse_ref_arg(" ref_55 ") == 55


async def test_register_referral_binds(db_conn, make_user):
    inviter = await make_user(db_conn, tg_id=1)
    invitee = await make_user(db_conn, tg_id=2)
    ok = await referrals_service.register_referral(
        db_conn, referrer_tg_id=inviter.tg_id, referred=invitee
    )
    assert ok is True
    r = await referrals_repo.get_by_referred(db_conn, invitee.id)
    assert r is not None and r.referrer_id == inviter.id


async def test_register_referral_self_referral_rejected(db_conn, make_user):
    u = await make_user(db_conn, tg_id=1)
    ok = await referrals_service.register_referral(
        db_conn, referrer_tg_id=u.tg_id, referred=u
    )
    assert ok is False
    assert await referrals_repo.get_by_referred(db_conn, u.id) is None


async def test_register_referral_unknown_inviter_rejected(db_conn, make_user):
    invitee = await make_user(db_conn, tg_id=2)
    ok = await referrals_service.register_referral(
        db_conn, referrer_tg_id=999, referred=invitee
    )
    assert ok is False


async def test_register_referral_no_rebind(db_conn, make_user):
    a = await make_user(db_conn, tg_id=1)
    b = await make_user(db_conn, tg_id=2)
    c = await make_user(db_conn, tg_id=3)
    assert await referrals_service.register_referral(
        db_conn, referrer_tg_id=a.tg_id, referred=b
    )
    # Re-binding b to c is refused; a keeps the credit.
    assert not await referrals_service.register_referral(
        db_conn, referrer_tg_id=c.tg_id, referred=b
    )
    r = await referrals_repo.get_by_referred(db_conn, b.id)
    assert r.referrer_id == a.id


async def test_reward_disabled_when_bonus_zero(db_conn, make_user, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "REFERRAL_BONUS_STARS", 0, raising=False)
    a = await make_user(db_conn, tg_id=1)
    b = await make_user(db_conn, tg_id=2)
    await referrals_service.register_referral(
        db_conn, referrer_tg_id=a.tg_id, referred=b
    )
    bot = AsyncMock()
    paid = await referrals_service.reward_referrer_after_first_payment(
        db_conn, bot, referred=b
    )
    assert paid is False
    assert await wallet_repo.balance(db_conn, a.id) == 0


async def test_reward_credits_once_and_dms(db_conn, make_user, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "REFERRAL_BONUS_STARS", 50, raising=False)
    a = await make_user(db_conn, tg_id=1)
    b = await make_user(db_conn, tg_id=2)
    await referrals_service.register_referral(
        db_conn, referrer_tg_id=a.tg_id, referred=b
    )
    bot = AsyncMock()
    first = await referrals_service.reward_referrer_after_first_payment(
        db_conn, bot, referred=b
    )
    assert first is True
    assert await wallet_repo.balance(db_conn, a.id) == 50
    assert bot.send_message.await_count == 1

    # Second call is a no-op (already rewarded).
    second = await referrals_service.reward_referrer_after_first_payment(
        db_conn, bot, referred=b
    )
    assert second is False
    assert await wallet_repo.balance(db_conn, a.id) == 50


async def test_reward_noop_without_referral(db_conn, make_user, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "REFERRAL_BONUS_STARS", 50, raising=False)
    b = await make_user(db_conn, tg_id=2)
    bot = AsyncMock()
    paid = await referrals_service.reward_referrer_after_first_payment(
        db_conn, bot, referred=b
    )
    assert paid is False
