"""Tests for :mod:`app.db.repos.promos`."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import aiosqlite
import pytest

from app.db.repos import promos as promos_repo


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat(sep=" ")


async def test_create_and_get(db_conn):
    p = await promos_repo.create(
        db_conn,
        code="ABC",
        type="percent",
        value=10,
        max_uses=0,
        expires_at=None,
        created_by=None,
    )
    assert p.code == "ABC"
    got = await promos_repo.get(db_conn, p.id)
    assert got is not None
    assert got.code == "ABC"


async def test_get_missing(db_conn):
    assert await promos_repo.get(db_conn, 999) is None


async def test_get_by_code_case_insensitive(db_conn):
    await promos_repo.create(
        db_conn,
        code="ABC123",
        type="percent",
        value=10,
        max_uses=0,
        expires_at=None,
        created_by=None,
    )
    found = await promos_repo.get_by_code(db_conn, "abc123")
    assert found is not None
    found2 = await promos_repo.get_by_code(db_conn, "AbC123")
    assert found2 is not None


async def test_get_by_code_missing(db_conn):
    assert await promos_repo.get_by_code(db_conn, "nope") is None


async def test_list_active_filters_expired_and_full(db_conn, make_user):
    user = await make_user(db_conn)
    now = datetime.now(UTC)

    p_active = await promos_repo.create(
        db_conn,
        code="OK",
        type="percent",
        value=10,
        max_uses=0,
        expires_at=None,
        created_by=user.id,
    )
    p_expired = await promos_repo.create(
        db_conn,
        code="OLD",
        type="percent",
        value=10,
        max_uses=0,
        expires_at=_iso(now - timedelta(days=1)),
        created_by=user.id,
    )
    p_full = await promos_repo.create(
        db_conn,
        code="FULL",
        type="percent",
        value=10,
        max_uses=1,
        expires_at=None,
        created_by=user.id,
    )
    # Bump used_count manually.
    await db_conn.execute(
        "UPDATE promos SET used_count=1 WHERE id=?", (p_full.id,)
    )
    await db_conn.commit()

    active = await promos_repo.list_active(db_conn)
    ids = {p.id for p in active}
    assert p_active.id in ids
    assert p_expired.id not in ids
    assert p_full.id not in ids


async def test_deactivate_sets_expires_in_past(db_conn):
    p = await promos_repo.create(
        db_conn,
        code="X",
        type="percent",
        value=10,
        max_uses=0,
        expires_at=None,
        created_by=None,
    )
    await promos_repo.deactivate(db_conn, p.id)
    fresh = await promos_repo.get(db_conn, p.id)
    assert fresh.expires_at is not None  # set to now


async def test_try_redeem_success(file_db, make_user, make_promo):
    """Happy-path: a capacity-1 promo can be redeemed once."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        promo = await make_promo(conn, code="A", max_uses=1)
        ok = await promos_repo.try_redeem(
            conn, promo_id=promo.id, user_id=user.id, subscription_id=None
        )
        assert ok is True
        # Counter incremented.
        refreshed = await promos_repo.get(conn, promo.id)
        assert refreshed.used_count == 1
        # Redemption recorded.
        redemptions = await promos_repo.list_redemptions(conn, promo.id)
        assert len(redemptions) == 1


async def test_try_redeem_capacity_reached(file_db, make_user, make_promo):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u1 = await make_user(conn, tg_id=1)
        u2 = await make_user(conn, tg_id=2)
        promo = await make_promo(conn, code="A", max_uses=1)

        ok1 = await promos_repo.try_redeem(
            conn, promo_id=promo.id, user_id=u1.id, subscription_id=None
        )
        assert ok1 is True

    # Second redemption hits capacity.
    async with get_conn() as conn:
        ok2 = await promos_repo.try_redeem(
            conn, promo_id=promo.id, user_id=u2.id, subscription_id=None
        )
    assert ok2 is False


async def test_try_redeem_expired(file_db, make_user, make_promo):
    from app.db.engine import get_conn

    past = _iso(datetime.now(UTC) - timedelta(days=1))
    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        promo = await make_promo(conn, code="A", expires_at=past)
        ok = await promos_repo.try_redeem(
            conn, promo_id=promo.id, user_id=u.id, subscription_id=None
        )
    assert ok is False


async def test_try_redeem_missing_promo(file_db, make_user):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        ok = await promos_repo.try_redeem(
            conn, promo_id=9999, user_id=u.id, subscription_id=None
        )
    assert ok is False


async def test_try_redeem_unlimited_max_uses(file_db, make_user, make_promo):
    """max_uses=0 means unlimited."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u1 = await make_user(conn, tg_id=1)
        u2 = await make_user(conn, tg_id=2)
        promo = await make_promo(conn, code="A", max_uses=0)

        ok1 = await promos_repo.try_redeem(
            conn, promo_id=promo.id, user_id=u1.id, subscription_id=None
        )
        ok2 = await promos_repo.try_redeem(
            conn, promo_id=promo.id, user_id=u2.id, subscription_id=None
        )
    assert ok1 is True and ok2 is True


async def test_try_redeem_race_on_capacity_one(file_db, make_user, make_promo):
    """Two concurrent redemptions on a max_uses=1 promo: only one wins."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u1 = await make_user(conn, tg_id=1)
        u2 = await make_user(conn, tg_id=2)
        promo = await make_promo(conn, code="RACE", max_uses=1)
        promo_id = promo.id
        u1_id, u2_id = u1.id, u2.id

    async def _redeem(uid):
        async with get_conn() as conn:
            return await promos_repo.try_redeem(
                conn, promo_id=promo_id, user_id=uid, subscription_id=None
            )

    results = await asyncio.gather(_redeem(u1_id), _redeem(u2_id))
    assert results.count(True) == 1
    assert results.count(False) == 1


async def test_list_redemptions_order(file_db, make_user, make_promo):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u1 = await make_user(conn, tg_id=1)
        u2 = await make_user(conn, tg_id=2)
        promo = await make_promo(conn, code="A", max_uses=0)
        await promos_repo.try_redeem(conn, promo_id=promo.id, user_id=u1.id, subscription_id=None)
        await promos_repo.try_redeem(conn, promo_id=promo.id, user_id=u2.id, subscription_id=None)
        rs = await promos_repo.list_redemptions(conn, promo.id)
    # Most recent first.
    assert rs[0].user_id == u2.id
    assert rs[1].user_id == u1.id
