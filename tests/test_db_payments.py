"""Tests for :mod:`app.db.repos.payments`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import aiosqlite
import pytest

from app.db.repos import payments as payments_repo
from app.db.repos.payments import _to_iso


async def test_to_iso_helpers():
    """The local _to_iso helper handles strings, naive and aware datetimes."""
    assert _to_iso("2025-01-01 00:00:00") == "2025-01-01 00:00:00"
    aware = datetime(2025, 1, 1, tzinfo=UTC)
    assert _to_iso(aware).startswith("2025-01-01")
    naive = datetime(2025, 1, 1)
    assert _to_iso(naive).startswith("2025-01-01")


async def test_create_and_get(db_conn, make_user):
    user = await make_user(db_conn)
    p = await payments_repo.create(
        db_conn,
        user_id=user.id,
        subscription_id=None,
        telegram_charge_id="ch1",
        stars_amount=100,
        plan_id=None,
        promo_id=None,
    )
    assert p.telegram_charge_id == "ch1"
    assert p.status == "paid"

    got = await payments_repo.get(db_conn, p.id)
    assert got is not None
    assert got.id == p.id


async def test_get_missing(db_conn):
    assert await payments_repo.get(db_conn, 999) is None


async def test_unique_charge_id(db_conn, make_user):
    user = await make_user(db_conn)
    await payments_repo.create(
        db_conn,
        user_id=user.id,
        subscription_id=None,
        telegram_charge_id="dup",
        stars_amount=10,
        plan_id=None,
        promo_id=None,
    )
    with pytest.raises(aiosqlite.IntegrityError):
        await payments_repo.create(
            db_conn,
            user_id=user.id,
            subscription_id=None,
            telegram_charge_id="dup",
            stars_amount=20,
            plan_id=None,
            promo_id=None,
        )


async def test_get_by_charge_id(db_conn, make_user):
    user = await make_user(db_conn)
    await payments_repo.create(
        db_conn,
        user_id=user.id,
        subscription_id=None,
        telegram_charge_id="abc",
        stars_amount=50,
        plan_id=None,
        promo_id=None,
    )
    p = await payments_repo.get_by_charge_id(db_conn, "abc")
    assert p is not None
    assert p.stars_amount == 50
    assert await payments_repo.get_by_charge_id(db_conn, "missing") is None


async def test_list_for_user_order(db_conn, make_user):
    user = await make_user(db_conn)
    a = await payments_repo.create(
        db_conn,
        user_id=user.id,
        subscription_id=None,
        telegram_charge_id="a",
        stars_amount=10,
        plan_id=None,
        promo_id=None,
    )
    b = await payments_repo.create(
        db_conn,
        user_id=user.id,
        subscription_id=None,
        telegram_charge_id="b",
        stars_amount=20,
        plan_id=None,
        promo_id=None,
    )
    listed = await payments_repo.list_for_user(db_conn, user.id)
    ids = [p.id for p in listed]
    # Newest first.
    assert ids == [b.id, a.id]


async def test_total_stars_period_excludes_refunded(db_conn, make_user):
    user = await make_user(db_conn)
    p1 = await payments_repo.create(
        db_conn,
        user_id=user.id,
        subscription_id=None,
        telegram_charge_id="p1",
        stars_amount=30,
        plan_id=None,
        promo_id=None,
    )
    p2 = await payments_repo.create(
        db_conn,
        user_id=user.id,
        subscription_id=None,
        telegram_charge_id="p2",
        stars_amount=70,
        plan_id=None,
        promo_id=None,
    )
    # Refund p2 — should not count.
    await payments_repo.set_status(db_conn, p2.id, "refunded")

    start = (datetime.now(UTC) - timedelta(days=1)).replace(microsecond=0)
    end = (datetime.now(UTC) + timedelta(days=1)).replace(microsecond=0)
    total = await payments_repo.total_stars_period(db_conn, start, end)
    assert total == 30


async def test_total_stars_period_accepts_iso_strings(db_conn, make_user):
    user = await make_user(db_conn)
    await payments_repo.create(
        db_conn,
        user_id=user.id,
        subscription_id=None,
        telegram_charge_id="p1",
        stars_amount=5,
        plan_id=None,
        promo_id=None,
    )
    total = await payments_repo.total_stars_period(
        db_conn, "2000-01-01 00:00:00", "2999-01-01 00:00:00"
    )
    assert total == 5


async def test_total_stars_period_empty(db_conn):
    """COALESCE returns 0 when there are no rows."""
    start = "2000-01-01 00:00:00"
    end = "2099-01-01 00:00:00"
    assert await payments_repo.total_stars_period(db_conn, start, end) == 0


async def test_set_status_paid_refunded_roundtrip(db_conn, make_user):
    user = await make_user(db_conn)
    p = await payments_repo.create(
        db_conn,
        user_id=user.id,
        subscription_id=None,
        telegram_charge_id="rs",
        stars_amount=10,
        plan_id=None,
        promo_id=None,
    )
    await payments_repo.set_status(db_conn, p.id, "refunded")
    fresh = await payments_repo.get(db_conn, p.id)
    assert fresh.status == "refunded"
