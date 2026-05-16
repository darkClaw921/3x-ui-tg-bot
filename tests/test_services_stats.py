"""Tests for :mod:`app.services.stats`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db.repos import payments as payments_repo
from app.services import stats as stats_service


async def test_revenue_stars_period(db_conn, make_user):
    user = await make_user(db_conn)
    await payments_repo.create(
        db_conn,
        user_id=user.id,
        subscription_id=None,
        telegram_charge_id="c1",
        stars_amount=10,
        plan_id=None,
        promo_id=None,
    )
    total = await stats_service.revenue_stars(db_conn, timedelta(days=30))
    assert total == 10


async def test_total_stars_period_passthrough(db_conn, make_user):
    user = await make_user(db_conn)
    await payments_repo.create(
        db_conn,
        user_id=user.id,
        subscription_id=None,
        telegram_charge_id="c1",
        stars_amount=20,
        plan_id=None,
        promo_id=None,
    )
    total = await stats_service.total_stars_period(
        db_conn,
        datetime(2000, 1, 1, tzinfo=UTC),
        datetime(2999, 1, 1, tzinfo=UTC),
    )
    assert total == 20


async def test_active_subscriptions_count(db_conn, make_user, make_subscription):
    user = await make_user(db_conn)
    past = datetime.now(UTC) - timedelta(days=1)
    future = datetime.now(UTC) + timedelta(days=1)
    await make_subscription(db_conn, user_id=user.id, expires_at=past)
    await make_subscription(
        db_conn,
        user_id=user.id,
        xui_client_uuid="u2",
        xui_client_email="e2",
        expires_at=future,
    )
    n = await stats_service.active_subscriptions_count(db_conn)
    assert n == 1


async def test_expiring_in_days(db_conn, make_user, make_subscription):
    user = await make_user(db_conn)
    soon = datetime.now(UTC) + timedelta(days=2)
    far = datetime.now(UTC) + timedelta(days=20)
    await make_subscription(db_conn, user_id=user.id, expires_at=soon)
    await make_subscription(
        db_conn,
        user_id=user.id,
        xui_client_uuid="u2",
        xui_client_email="e2",
        expires_at=far,
    )
    result = await stats_service.expiring_in_days(db_conn, 3)
    assert len(result) == 1


async def test_expiring_in_alias(db_conn, make_user, make_subscription):
    """expiring_in and expiring_in_days return identical results."""
    user = await make_user(db_conn)
    soon = datetime.now(UTC) + timedelta(days=2)
    await make_subscription(db_conn, user_id=user.id, expires_at=soon)
    a = await stats_service.expiring_in(db_conn, 3)
    b = await stats_service.expiring_in_days(db_conn, 3)
    assert [x.id for x in a] == [x.id for x in b]


async def test_top_promos_order_and_limit(db_conn, make_promo, make_user):
    user = await make_user(db_conn)
    p1 = await make_promo(db_conn, code="A")
    p2 = await make_promo(db_conn, code="B")
    p3 = await make_promo(db_conn, code="C")
    # Manually set used_count.
    await db_conn.execute("UPDATE promos SET used_count=10 WHERE id=?", (p1.id,))
    await db_conn.execute("UPDATE promos SET used_count=20 WHERE id=?", (p2.id,))
    await db_conn.execute("UPDATE promos SET used_count=5 WHERE id=?", (p3.id,))
    await db_conn.commit()
    top = await stats_service.top_promos(db_conn, limit=2)
    assert [p.id for p in top] == [p2.id, p1.id]


async def test_top_promos_empty(db_conn):
    top = await stats_service.top_promos(db_conn)
    assert top == []


async def test_users_count(db_conn, make_user):
    await make_user(db_conn, tg_id=1)
    await make_user(db_conn, tg_id=2)
    assert await stats_service.users_count(db_conn) == 2
    assert await stats_service.users_count_total(db_conn) == 2


async def test_payments_count_period_iso(db_conn, make_user):
    user = await make_user(db_conn)
    await payments_repo.create(
        db_conn,
        user_id=user.id,
        subscription_id=None,
        telegram_charge_id="c1",
        stars_amount=10,
        plan_id=None,
        promo_id=None,
    )
    n = await stats_service.payments_count_period(
        db_conn, "2000-01-01 00:00:00", "2999-01-01 00:00:00"
    )
    assert n == 1


async def test_payments_count_period_datetime(db_conn, make_user):
    user = await make_user(db_conn)
    await payments_repo.create(
        db_conn,
        user_id=user.id,
        subscription_id=None,
        telegram_charge_id="c1",
        stars_amount=5,
        plan_id=None,
        promo_id=None,
    )
    n = await stats_service.payments_count_period(
        db_conn,
        datetime(2000, 1, 1, tzinfo=UTC),
        datetime(2999, 1, 1, tzinfo=UTC),
    )
    assert n == 1


async def test_payments_count_excludes_refunded(db_conn, make_user):
    user = await make_user(db_conn)
    p = await payments_repo.create(
        db_conn,
        user_id=user.id,
        subscription_id=None,
        telegram_charge_id="c1",
        stars_amount=5,
        plan_id=None,
        promo_id=None,
    )
    await payments_repo.set_status(db_conn, p.id, "refunded")
    n = await stats_service.payments_count_period(
        db_conn, "2000-01-01 00:00:00", "2999-01-01 00:00:00"
    )
    assert n == 0
