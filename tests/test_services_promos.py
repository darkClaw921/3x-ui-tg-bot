"""Tests for :mod:`app.services.promos` — validate/apply/compute_discount."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.db.repos.plans import Plan
from app.services import promos as promos_service


def _plan(price=100, days=30, plan_id=1):
    return Plan(
        id=plan_id,
        title="t",
        days=days,
        price_stars=price,
        traffic_gb=0,
        is_active=True,
        created_at="2025",
    )


async def test_validate_empty_code(db_conn, make_user):
    user = await make_user(db_conn)
    result = await promos_service.validate(db_conn, "", user.id, _plan())
    assert result.is_valid is False
    assert "код" in (result.error or "").lower()


async def test_validate_unknown_code(db_conn, make_user):
    user = await make_user(db_conn)
    result = await promos_service.validate(db_conn, "MISSING", user.id, _plan())
    assert result.is_valid is False
    assert result.promo is None


async def test_validate_ok(db_conn, make_user, make_promo):
    user = await make_user(db_conn)
    await make_promo(db_conn, code="ABC")
    result = await promos_service.validate(db_conn, "abc", user.id, _plan())
    assert result.is_valid is True
    assert result.promo is not None


async def test_validate_expired(db_conn, make_user, make_promo):
    user = await make_user(db_conn)
    past = (datetime.now(UTC) - timedelta(days=1)).replace(microsecond=0).isoformat(sep=" ")
    await make_promo(db_conn, code="OLD", expires_at=past)
    result = await promos_service.validate(db_conn, "OLD", user.id, _plan())
    assert result.is_valid is False
    assert "истёк" in (result.error or "").lower() or "истек" in (result.error or "").lower()


async def test_validate_capacity_exhausted(db_conn, make_user, make_promo):
    user = await make_user(db_conn)
    p = await make_promo(db_conn, code="FULL", max_uses=1)
    await db_conn.execute("UPDATE promos SET used_count=1 WHERE id=?", (p.id,))
    await db_conn.commit()
    result = await promos_service.validate(db_conn, "FULL", user.id, _plan())
    assert result.is_valid is False


async def test_validate_already_redeemed(file_db, make_user, make_promo):
    from app.db.engine import get_conn
    from app.db.repos import promos as promos_repo

    async with get_conn() as conn:
        user = await make_user(conn)
        promo = await make_promo(conn, code="X", max_uses=0)
        await promos_repo.try_redeem(
            conn, promo_id=promo.id, user_id=user.id, subscription_id=None
        )
    async with get_conn() as conn:
        result = await promos_service.validate(conn, "X", user.id, _plan())
    assert result.is_valid is False
    assert result.promo is not None


async def test_validate_plan_none_accepts_any_type(db_conn, make_user, make_promo):
    user = await make_user(db_conn)
    await make_promo(db_conn, code="F", type="free_days", value=7)
    result = await promos_service.validate(db_conn, "F", user.id, None)
    assert result.is_valid is True


def test_compute_discount_no_promo():
    r = promos_service.compute_discount(_plan(100), None)
    assert r.final_price == 100
    assert r.extra_days == 0


def test_compute_discount_percent():
    from app.db.repos.promos import Promo

    promo = Promo(
        id=1,
        code="C",
        type="percent",
        value=25,
        max_uses=0,
        used_count=0,
        expires_at=None,
        created_at="2025",
        created_by=None,
    )
    r = promos_service.compute_discount(_plan(100), promo)
    assert r.final_price == 75


def test_compute_discount_unknown_type_fallback():
    from app.db.repos.promos import Promo

    promo = Promo(
        id=1,
        code="C",
        type="WEIRD",  # type: ignore[arg-type]
        value=10,
        max_uses=0,
        used_count=0,
        expires_at=None,
        created_at="2025",
        created_by=None,
    )
    r = promos_service.compute_discount(_plan(100), promo)
    assert r.final_price == 100


async def test_apply_atomic(file_db, make_user, make_promo, make_subscription):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn)
        promo = await make_promo(conn, code="A", max_uses=2)
        sub = await make_subscription(conn, user_id=user.id)
        ok = await promos_service.apply(
            conn, promo_id=promo.id, user_id=user.id, subscription_id=sub.id
        )
    assert ok is True


async def test_apply_race_capacity_one(file_db, make_user, make_promo):
    """Two parallel apply calls on capacity-1 promo: exactly one wins."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u1 = await make_user(conn, tg_id=1)
        u2 = await make_user(conn, tg_id=2)
        promo = await make_promo(conn, code="RACE", max_uses=1)
        promo_id = promo.id
        u1_id, u2_id = u1.id, u2.id

    async def _redeem(uid):
        async with get_conn() as conn:
            return await promos_service.apply(
                conn, promo_id=promo_id, user_id=uid, subscription_id=None
            )

    r1, r2 = await asyncio.gather(_redeem(u1_id), _redeem(u2_id))
    assert {r1, r2} == {True, False}
