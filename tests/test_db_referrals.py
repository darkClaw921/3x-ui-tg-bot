"""Tests for :mod:`app.db.repos.referrals` — the invite-a-friend ledger."""

from __future__ import annotations

from app.db.repos import referrals as referrals_repo


async def test_create_pending_inserts_and_returns_row(db_conn, make_user):
    referrer = await make_user(db_conn, tg_id=1)
    referred = await make_user(db_conn, tg_id=2)
    r = await referrals_repo.create_pending(
        db_conn, referrer_id=referrer.id, referred_id=referred.id
    )
    assert r is not None
    assert r.referrer_id == referrer.id
    assert r.referred_id == referred.id
    assert r.status == "pending"
    assert r.rewarded_at is None


async def test_create_pending_is_idempotent_per_referred(db_conn, make_user):
    a = await make_user(db_conn, tg_id=1)
    b = await make_user(db_conn, tg_id=2)
    c = await make_user(db_conn, tg_id=3)
    first = await referrals_repo.create_pending(
        db_conn, referrer_id=a.id, referred_id=b.id
    )
    assert first is not None
    # Re-binding the same referred user to a different referrer is a no-op.
    second = await referrals_repo.create_pending(
        db_conn, referrer_id=c.id, referred_id=b.id
    )
    assert second is None
    bound = await referrals_repo.get_by_referred(db_conn, b.id)
    assert bound is not None
    assert bound.referrer_id == a.id  # first inviter keeps the credit


async def test_get_by_referred_none_when_absent(db_conn, make_user):
    u = await make_user(db_conn, tg_id=1)
    assert await referrals_repo.get_by_referred(db_conn, u.id) is None


async def test_try_mark_rewarded_flips_once(db_conn, make_user):
    a = await make_user(db_conn, tg_id=1)
    b = await make_user(db_conn, tg_id=2)
    await referrals_repo.create_pending(db_conn, referrer_id=a.id, referred_id=b.id)

    first = await referrals_repo.try_mark_rewarded(db_conn, b.id)
    assert first is not None
    assert first.status == "rewarded"
    assert first.rewarded_at is not None

    # Second attempt is a no-op (already rewarded).
    second = await referrals_repo.try_mark_rewarded(db_conn, b.id)
    assert second is None


async def test_try_mark_rewarded_none_for_unknown(db_conn, make_user):
    assert await referrals_repo.try_mark_rewarded(db_conn, 999) is None


async def test_count_for_referrer(db_conn, make_user):
    a = await make_user(db_conn, tg_id=1)
    b = await make_user(db_conn, tg_id=2)
    c = await make_user(db_conn, tg_id=3)
    assert await referrals_repo.count_for_referrer(db_conn, a.id) == 0
    await referrals_repo.create_pending(db_conn, referrer_id=a.id, referred_id=b.id)
    await referrals_repo.create_pending(db_conn, referrer_id=a.id, referred_id=c.id)
    assert await referrals_repo.count_for_referrer(db_conn, a.id) == 2
    # rewarded rows still count.
    await referrals_repo.try_mark_rewarded(db_conn, b.id)
    assert await referrals_repo.count_for_referrer(db_conn, a.id) == 2


async def test_get_by_id_round_trip(db_conn, make_user):
    a = await make_user(db_conn, tg_id=1)
    b = await make_user(db_conn, tg_id=2)
    created = await referrals_repo.create_pending(
        db_conn, referrer_id=a.id, referred_id=b.id
    )
    assert created is not None
    fetched = await referrals_repo.get(db_conn, created.id)
    assert fetched is not None
    assert fetched.id == created.id
