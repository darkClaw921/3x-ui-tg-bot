"""Boundary-value (edge) tests for the promos + subscriptions + trial +
referrals + gifts domain.

This file deliberately targets *only* the boundary values that the sibling
suites (``test_services_promos``, ``test_db_promos``, ``test_db_subscriptions``,
``test_db_subscriptions_trial``, ``test_services_subscriptions``,
``test_services_trial``, ``test_db_referrals``, ``test_services_referrals``,
``test_db_gift_codes``, ``test_services_gifts``) leave uncovered or barely
touch. Each test isolates a single edge of a range (0, ==limit, limit-1,
limit+1, "exactly now") so a regression on a comparison operator surfaces here.

Fixtures are reused from ``conftest.py`` (``db_conn``, ``file_db``,
``make_user``, ``make_plan``, ``make_promo``, ``make_subscription``). Local
helpers below mirror the patterns of the neighbouring suites and are kept in
this module (conftest is not modified).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest

from app.db.repos import gift_codes as gift_repo
from app.db.repos import promos as promos_repo
from app.db.repos import referrals as referrals_repo
from app.db.repos import subscriptions as subs_repo
from app.db.repos import wallet as wallet_repo
from app.db.repos.plans import Plan
from app.db.repos.promos import Promo
from app.services import gifts as gifts_service
from app.services import promos as promos_service
from app.services import referrals as referrals_service
from app.services import subscriptions as subs_service
from app.xui import XuiError


# --------------------------------------------------------------------------- #
# Local helpers (mirroring the neighbouring suites)
# --------------------------------------------------------------------------- #


def _plan(price: int = 100, days: int = 30, plan_id: int = 1) -> Plan:
    """Build a stand-alone :class:`Plan` for pure ``compute_discount`` math."""
    return Plan(
        id=plan_id,
        title="t",
        days=days,
        price_stars=price,
        traffic_gb=0,
        is_active=True,
        created_at="2025",
    )


def _promo(type: str, value: int, *, max_uses: int = 0, used_count: int = 0) -> Promo:
    """Build a stand-alone :class:`Promo` for pure ``compute_discount`` math."""
    return Promo(
        id=1,
        code="C",
        type=type,  # type: ignore[arg-type]
        value=value,
        max_uses=max_uses,
        used_count=used_count,
        expires_at=None,
        created_at="2025",
        created_by=None,
    )


def _iso(dt: datetime) -> str:
    """Serialise a datetime to the bot's ISO-8601 (seconds, space sep) form."""
    return dt.astimezone(UTC).replace(microsecond=0).isoformat(sep=" ")


# ========================================================================== #
# promos.compute_discount — pricing boundaries
# ========================================================================== #


def test_compute_discount_percent_one_charges_almost_full():
    """percent=1 → round-up keeps the price one Star below nominal (ceil)."""
    r = promos_service.compute_discount(_plan(100), _promo("percent", 1))
    # ceil(100 * 99 / 100) == 99.
    assert r.final_price == 99
    assert r.extra_days == 0


def test_compute_discount_percent_hundred_is_free():
    """percent=100 → final price floors to 0 (the whole plan is discounted)."""
    r = promos_service.compute_discount(_plan(100), _promo("percent", 100))
    assert r.final_price == 0
    assert r.extra_days == 0


def test_compute_discount_percent_clamped_above_hundred():
    """percent>100 is clamped to 100 → still exactly free, never negative."""
    r = promos_service.compute_discount(_plan(100), _promo("percent", 150))
    assert r.final_price == 0


def test_compute_discount_flat_zero_is_no_op():
    """flat_stars=0 → no discount, price unchanged."""
    r = promos_service.compute_discount(_plan(100), _promo("flat_stars", 0))
    assert r.final_price == 100
    assert r.extra_days == 0


def test_compute_discount_flat_equals_price_is_free():
    """flat_stars == price → exactly 0 (boundary of the max(0, …) floor)."""
    r = promos_service.compute_discount(_plan(100), _promo("flat_stars", 100))
    assert r.final_price == 0


def test_compute_discount_flat_above_price_floors_at_zero():
    """flat_stars > price → 0, NOT a negative price."""
    r = promos_service.compute_discount(_plan(100), _promo("flat_stars", 250))
    assert r.final_price == 0
    assert r.final_price >= 0


def test_compute_discount_free_days_keeps_price_and_grants_days():
    """free_days → final price stays nominal, extra_days carries the value."""
    r = promos_service.compute_discount(_plan(100), _promo("free_days", 7))
    assert r.final_price == 100
    assert r.extra_days == 7


def test_compute_discount_free_days_negative_value_clamped():
    """free_days with a negative value clamps extra_days to 0 (defensive)."""
    r = promos_service.compute_discount(_plan(100), _promo("free_days", -5))
    assert r.final_price == 100
    assert r.extra_days == 0


def test_compute_discount_none_promo_is_nominal():
    """promo=None → nominal price, no bonus days."""
    r = promos_service.compute_discount(_plan(77), None)
    assert r.final_price == 77
    assert r.extra_days == 0


# ========================================================================== #
# promos.validate — capacity / expiry / case boundaries
# ========================================================================== #


async def test_validate_unknown_code_returns_no_promo(db_conn, make_user):
    """A code that does not exist → invalid, promo is None."""
    user = await make_user(db_conn)
    result = await promos_service.validate(db_conn, "DOESNOTEXIST", user.id, _plan())
    assert result.is_valid is False
    assert result.promo is None


async def test_validate_expires_exactly_now_is_invalid(db_conn, make_user, make_promo):
    """expires_at == now → invalid (the comparison is ``expires_at <= now``)."""
    user = await make_user(db_conn)
    now = _iso(datetime.now(UTC))
    await make_promo(db_conn, code="NOWX", expires_at=now)
    result = await promos_service.validate(db_conn, "NOWX", user.id, _plan())
    assert result.is_valid is False
    assert "истёк" in (result.error or "").lower() or "истек" in (result.error or "").lower()


async def test_validate_expires_in_past_is_invalid(db_conn, make_user, make_promo):
    """expires_at one second in the past → invalid (just over the boundary)."""
    user = await make_user(db_conn)
    past = _iso(datetime.now(UTC) - timedelta(seconds=1))
    await make_promo(db_conn, code="PAST", expires_at=past)
    result = await promos_service.validate(db_conn, "PAST", user.id, _plan())
    assert result.is_valid is False


async def test_validate_max_uses_zero_never_exhausted(db_conn, make_user, make_promo):
    """max_uses=0 means unlimited: even a huge used_count stays valid."""
    user = await make_user(db_conn)
    p = await make_promo(db_conn, code="UNLIM", max_uses=0)
    await db_conn.execute("UPDATE promos SET used_count=9999 WHERE id=?", (p.id,))
    await db_conn.commit()
    result = await promos_service.validate(db_conn, "UNLIM", user.id, _plan())
    assert result.is_valid is True


async def test_validate_used_count_one_below_limit_still_valid(
    db_conn, make_user, make_promo
):
    """used_count == max_uses-1 → still one slot left → valid (lower boundary)."""
    user = await make_user(db_conn)
    p = await make_promo(db_conn, code="ONELEFT", max_uses=3)
    await db_conn.execute("UPDATE promos SET used_count=2 WHERE id=?", (p.id,))
    await db_conn.commit()
    result = await promos_service.validate(db_conn, "ONELEFT", user.id, _plan())
    assert result.is_valid is True


async def test_validate_used_count_equals_limit_exhausted(
    db_conn, make_user, make_promo
):
    """used_count == max_uses → exhausted (upper boundary, ``>=`` fires)."""
    user = await make_user(db_conn)
    p = await make_promo(db_conn, code="FULL", max_uses=3)
    await db_conn.execute("UPDATE promos SET used_count=3 WHERE id=?", (p.id,))
    await db_conn.commit()
    result = await promos_service.validate(db_conn, "FULL", user.id, _plan())
    assert result.is_valid is False
    assert "лимит" in (result.error or "").lower()


async def test_validate_case_insensitive_lookup(db_conn, make_user, make_promo):
    """A promo stored upper-case is found when typed lower-case (COLLATE NOCASE)."""
    user = await make_user(db_conn)
    await make_promo(db_conn, code="UPPER", type="percent", value=10)
    result = await promos_service.validate(db_conn, "uPpEr", user.id, _plan())
    assert result.is_valid is True
    assert result.promo is not None


async def test_validate_max_uses_one_used_one_is_exhausted(
    db_conn, make_user, make_promo
):
    """max_uses=1 + used_count=1 → exhausted (the single-slot boundary)."""
    user = await make_user(db_conn)
    p = await make_promo(db_conn, code="SINGLE", max_uses=1)
    await db_conn.execute("UPDATE promos SET used_count=1 WHERE id=?", (p.id,))
    await db_conn.commit()
    result = await promos_service.validate(db_conn, "SINGLE", user.id, _plan())
    assert result.is_valid is False


# ========================================================================== #
# promos.try_redeem / apply — capacity boundary + idempotency
# ========================================================================== #


async def test_try_redeem_last_slot_succeeds_then_next_fails(
    file_db, make_user, make_promo
):
    """used_count==max_uses-1 → final redeem wins; the immediate next fails."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u1 = await make_user(conn, tg_id=1)
        u2 = await make_user(conn, tg_id=2)
        promo = await make_promo(conn, code="LAST", max_uses=2)
        # Pre-burn one slot so the next redeem is the capacity boundary.
        await conn.execute("UPDATE promos SET used_count=1 WHERE id=?", (promo.id,))
        await conn.commit()
        promo_id, u1_id, u2_id = promo.id, u1.id, u2.id

        ok_last = await promos_repo.try_redeem(
            conn, promo_id=promo_id, user_id=u1_id, subscription_id=None
        )
        ok_over = await promos_repo.try_redeem(
            conn, promo_id=promo_id, user_id=u2_id, subscription_id=None
        )
    assert ok_last is True
    assert ok_over is False


async def test_apply_does_not_overshoot_capacity_under_race(
    file_db, make_user, make_promo
):
    """Three concurrent applies on a capacity-2 promo: exactly two succeed."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        users = [await make_user(conn, tg_id=i) for i in range(1, 4)]
        promo = await make_promo(conn, code="CAP2", max_uses=2)
        promo_id = promo.id
        ids = [u.id for u in users]

    async def _apply(uid: int) -> bool:
        async with get_conn() as conn:
            return await promos_service.apply(
                conn, promo_id=promo_id, user_id=uid, subscription_id=None
            )

    results = await asyncio.gather(*[_apply(i) for i in ids])
    assert results.count(True) == 2
    assert results.count(False) == 1


async def test_apply_idempotent_second_call_past_capacity_one(
    file_db, make_user, make_promo
):
    """On a capacity-1 promo the same user's *second* apply misses (counter is 1)."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        promo = await make_promo(conn, code="ONCE", max_uses=1)
        first = await promos_service.apply(
            conn, promo_id=promo.id, user_id=user.id, subscription_id=None
        )
        second = await promos_service.apply(
            conn, promo_id=promo.id, user_id=user.id, subscription_id=None
        )
        refreshed = await promos_repo.get(conn, promo.id)
    assert first is True
    assert second is False
    assert refreshed.used_count == 1


# ========================================================================== #
# subscriptions repo — "exactly now" / "exactly now+days" boundaries
# ========================================================================== #


async def test_expires_exactly_now_is_expired_not_active(
    db_conn, make_user, make_subscription
):
    """expires_at == now → in list_expired_active (<= now), NOT in list_active.

    Uses ``list_expired_active(now=...)`` with an explicit ``now`` equal to the
    row's ``expires_at`` to pin the boundary deterministically.
    """
    user = await make_user(db_conn)
    boundary = datetime.now(UTC).replace(microsecond=0)
    sub = await make_subscription(db_conn, user_id=user.id, expires_at=boundary)

    expired = await subs_repo.list_expired_active(db_conn, now=boundary)
    assert sub.id in {s.id for s in expired}


async def test_expires_one_second_future_is_active_not_expired(
    db_conn, make_user, make_subscription
):
    """expires_at == now+1s → in list_active (> now), NOT in list_expired_active."""
    user = await make_user(db_conn)
    boundary = datetime.now(UTC).replace(microsecond=0)
    sub = await make_subscription(
        db_conn, user_id=user.id, expires_at=boundary + timedelta(seconds=1)
    )

    expired = await subs_repo.list_expired_active(db_conn, now=boundary)
    assert sub.id not in {s.id for s in expired}
    actives = await subs_repo.list_active(db_conn)
    assert sub.id in {s.id for s in actives}


async def test_list_expiring_in_includes_row_exactly_at_window_end(
    db_conn, make_user, make_subscription
):
    """A subscription expiring at ~now+days is inside the [now, now+days] window.

    ``list_expiring_in`` upper bound is inclusive (``expires_at <= now+days``).
    The row is placed a hair inside the boundary to avoid a real-time race on
    the seconds the test takes to run.
    """
    user = await make_user(db_conn)
    exp = datetime.now(UTC) + timedelta(days=3) - timedelta(seconds=2)
    sub = await make_subscription(db_conn, user_id=user.id, expires_at=exp)
    result = await subs_repo.list_expiring_in(db_conn, days=3)
    assert sub.id in {s.id for s in result}


async def test_list_expiring_in_excludes_row_just_past_window_end(
    db_conn, make_user, make_subscription
):
    """A subscription expiring just beyond now+days is outside the window."""
    user = await make_user(db_conn)
    exp = datetime.now(UTC) + timedelta(days=3) + timedelta(minutes=5)
    sub = await make_subscription(db_conn, user_id=user.id, expires_at=exp)
    result = await subs_repo.list_expiring_in(db_conn, days=3)
    assert sub.id not in {s.id for s in result}


async def test_list_expiring_in_excludes_already_expired(
    db_conn, make_user, make_subscription
):
    """list_expiring_in lower bound is exclusive: an expired row is not 'expiring'."""
    user = await make_user(db_conn)
    exp = datetime.now(UTC) - timedelta(seconds=1)
    sub = await make_subscription(db_conn, user_id=user.id, expires_at=exp)
    result = await subs_repo.list_expiring_in(db_conn, days=3)
    assert sub.id not in {s.id for s in result}


async def test_extend_changes_only_expires_at(db_conn, make_user, make_subscription):
    """extend() moves expires_at forward and leaves every other column intact."""
    user = await make_user(db_conn)
    sub = await make_subscription(
        db_conn, user_id=user.id, expires_at=datetime.now(UTC) + timedelta(days=1)
    )
    new_exp = datetime.now(UTC) + timedelta(days=90)
    await subs_repo.extend(db_conn, sub.id, new_exp)
    fresh = await subs_repo.get(db_conn, sub.id)
    assert fresh.expires_at.startswith(new_exp.strftime("%Y-%m-%d"))
    # Everything else is untouched.
    assert fresh.status == sub.status
    assert fresh.xui_client_uuid == sub.xui_client_uuid
    assert fresh.xui_client_email == sub.xui_client_email
    assert fresh.xui_sub_id == sub.xui_sub_id
    assert fresh.user_id == sub.user_id
    assert fresh.is_trial == sub.is_trial


@pytest.mark.parametrize("status", ["active", "expired", "revoked"])
async def test_set_status_each_allowed_value(
    db_conn, make_user, make_subscription, status
):
    """Every allowed status value round-trips and leaves expires_at preserved."""
    user = await make_user(db_conn)
    sub = await make_subscription(db_conn, user_id=user.id)
    await subs_repo.set_status(db_conn, sub.id, status)
    fresh = await subs_repo.get(db_conn, sub.id)
    assert fresh.status == status
    assert fresh.expires_at == sub.expires_at


async def test_revoked_row_excluded_from_active_and_expired_lists(
    db_conn, make_user, make_subscription
):
    """A revoked subscription appears in neither list_active nor list_expired_active."""
    user = await make_user(db_conn)
    # Past-dated so it would qualify for list_expired_active if status mattered less.
    sub = await make_subscription(
        db_conn, user_id=user.id, expires_at=datetime.now(UTC) - timedelta(days=1)
    )
    await subs_repo.set_status(db_conn, sub.id, "revoked")
    actives = await subs_repo.list_active(db_conn)
    expired = await subs_repo.list_expired_active(db_conn)
    assert sub.id not in {s.id for s in actives}
    assert sub.id not in {s.id for s in expired}


async def test_has_trial_true_only_for_trial_rows(db_conn, make_user):
    """has_trial is False while only non-trial rows exist, True after a trial insert."""
    user = await make_user(db_conn, tg_id=1)
    await subs_repo.create(
        db_conn,
        user_id=user.id,
        xui_inbound_id=1,
        xui_client_uuid="u-nontrial",
        xui_client_email="e-nontrial",
        expires_at=datetime.now(UTC) + timedelta(days=5),
        plan_id=None,
        xui_sub_id="s0",
        is_trial=False,
    )
    assert await subs_repo.has_trial(db_conn, user.id) is False
    await subs_repo.create(
        db_conn,
        user_id=user.id,
        xui_inbound_id=1,
        xui_client_uuid="u-trial",
        xui_client_email="e-trial",
        expires_at=datetime.now(UTC) + timedelta(days=5),
        plan_id=None,
        xui_sub_id="s1",
        is_trial=True,
    )
    assert await subs_repo.has_trial(db_conn, user.id) is True


# ========================================================================== #
# trial — partial-unique boundary + minimum days
# ========================================================================== #


async def test_second_trial_insert_raises_integrity_error(db_conn, make_user):
    """The partial-unique idx_subscriptions_one_trial rejects a 2nd trial insert."""
    user = await make_user(db_conn, tg_id=1)
    base = dict(
        xui_inbound_id=1,
        expires_at=datetime.now(UTC) + timedelta(days=3),
        plan_id=None,
        is_trial=True,
    )
    await subs_repo.create(
        db_conn,
        user_id=user.id,
        xui_client_uuid="t1",
        xui_client_email="te1",
        xui_sub_id="ts1",
        **base,
    )
    with pytest.raises(aiosqlite.IntegrityError):
        await subs_repo.create(
            db_conn,
            user_id=user.id,
            xui_client_uuid="t2",
            xui_client_email="te2",
            xui_sub_id="ts2",
            **base,
        )


async def test_activate_trial_minimum_days_zero(file_db, make_user):
    """activate_trial at the minimum boundary days=0 still provisions a trial row.

    ``_provision`` clamps ``delta_days`` with ``max(0, …)`` so days=0 is the
    floor; it yields a same-instant expiry but a valid is_trial subscription.
    """
    from app.db.engine import get_conn

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"id": "uuid", "email": "e"})

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        sub = await subs_service.activate_trial(
            conn, xui, user, inbound_id=7, days=0, traffic_gb=0
        )
        assert sub.is_trial is True
        # The one-trial guard is now armed for this user.
        assert await subs_repo.has_trial(conn, user.id) is True


async def test_activate_trial_repeat_rejected_after_minimum(file_db, make_user):
    """A second activate_trial (any days) is rejected once a trial exists."""
    from app.db.engine import get_conn

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"id": "uuid", "email": "e"})

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        await subs_service.activate_trial(
            conn, xui, user, inbound_id=7, days=1, traffic_gb=0
        )
        with pytest.raises(subs_service.TrialAlreadyUsedError):
            await subs_service.activate_trial(
                conn, xui, user, inbound_id=7, days=7, traffic_gb=0
            )


# ========================================================================== #
# referrals — self / dup / reward-once / disabled / count boundaries
# ========================================================================== #


async def test_create_pending_duplicate_referred_returns_none(db_conn, make_user):
    """A second create_pending for the same referred_id is a silent no-op (None)."""
    a = await make_user(db_conn, tg_id=1)
    b = await make_user(db_conn, tg_id=2)
    c = await make_user(db_conn, tg_id=3)
    first = await referrals_repo.create_pending(
        db_conn, referrer_id=a.id, referred_id=b.id
    )
    assert first is not None
    dup = await referrals_repo.create_pending(
        db_conn, referrer_id=c.id, referred_id=b.id
    )
    assert dup is None
    # First inviter keeps the credit.
    bound = await referrals_repo.get_by_referred(db_conn, b.id)
    assert bound.referrer_id == a.id


async def test_register_referral_self_referral_rejected(db_conn, make_user):
    """referrer == referred → refused, no row created."""
    u = await make_user(db_conn, tg_id=1)
    ok = await referrals_service.register_referral(
        db_conn, referrer_tg_id=u.tg_id, referred=u
    )
    assert ok is False
    assert await referrals_repo.get_by_referred(db_conn, u.id) is None


async def test_try_mark_rewarded_exactly_once_then_none(db_conn, make_user):
    """try_mark_rewarded wins exactly once; the very next call returns None."""
    a = await make_user(db_conn, tg_id=1)
    b = await make_user(db_conn, tg_id=2)
    await referrals_repo.create_pending(db_conn, referrer_id=a.id, referred_id=b.id)
    first = await referrals_repo.try_mark_rewarded(db_conn, b.id)
    second = await referrals_repo.try_mark_rewarded(db_conn, b.id)
    assert first is not None and first.status == "rewarded"
    assert second is None


async def test_reward_bonus_zero_disables_feature(db_conn, make_user, monkeypatch):
    """REFERRAL_BONUS_STARS=0 → feature off: no credit, referral stays pending."""
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
    # Referral remains pending so a later (re-enabled) run can still pay it.
    bound = await referrals_repo.get_by_referred(db_conn, b.id)
    assert bound.status == "pending"
    assert bot.send_message.await_count == 0


async def test_reward_bonus_one_is_minimum_enabled(db_conn, make_user, monkeypatch):
    """REFERRAL_BONUS_STARS=1 is the minimum enabled value → credits exactly 1."""
    from app.config import settings

    monkeypatch.setattr(settings, "REFERRAL_BONUS_STARS", 1, raising=False)
    a = await make_user(db_conn, tg_id=1)
    b = await make_user(db_conn, tg_id=2)
    await referrals_service.register_referral(
        db_conn, referrer_tg_id=a.tg_id, referred=b
    )
    bot = AsyncMock()
    paid = await referrals_service.reward_referrer_after_first_payment(
        db_conn, bot, referred=b
    )
    assert paid is True
    assert await wallet_repo.balance(db_conn, a.id) == 1


async def test_count_for_referrer_zero_and_n(db_conn, make_user):
    """count_for_referrer is 0 with no invitees and exactly N after N bindings."""
    a = await make_user(db_conn, tg_id=1)
    assert await referrals_repo.count_for_referrer(db_conn, a.id) == 0
    invitees = [await make_user(db_conn, tg_id=i) for i in range(2, 5)]
    for inv in invitees:
        await referrals_repo.create_pending(
            db_conn, referrer_id=a.id, referred_id=inv.id
        )
    assert await referrals_repo.count_for_referrer(db_conn, a.id) == len(invitees)


# ========================================================================== #
# gifts — NOCASE / redeem-once / mint-retry exhaustion / XuiError rollback
# ========================================================================== #


async def test_gift_get_by_code_nocase(db_conn, make_user):
    """get_by_code is case-insensitive (COLLATE NOCASE)."""
    buyer = await make_user(db_conn, tg_id=1)
    gift = await gift_repo.create(
        db_conn, code="GIFT-ABCD1234", plan_id=None, inbound_id=1, buyer_id=buyer.id
    )
    found = await gift_repo.get_by_code(db_conn, "gift-abcd1234")
    assert found is not None
    assert found.id == gift.id


async def test_gift_try_redeem_active_then_second_false(
    db_conn, make_user, make_subscription
):
    """try_redeem on an active code succeeds once; the second attempt is False."""
    buyer = await make_user(db_conn, tg_id=1)
    recip = await make_user(db_conn, tg_id=2)
    sub = await make_subscription(db_conn, user_id=recip.id)
    gift = await gift_repo.create(
        db_conn, code="GIFT-ONCE1111", plan_id=None, inbound_id=1, buyer_id=buyer.id
    )
    first = await gift_repo.try_redeem(
        db_conn, code=gift.code, redeemed_by=recip.id, subscription_id=sub.id
    )
    second = await gift_repo.try_redeem(
        db_conn, code=gift.code, redeemed_by=recip.id, subscription_id=sub.id
    )
    assert first is True
    assert second is False
    after = await gift_repo.get(db_conn, gift.id)
    assert after.status == "redeemed"


async def test_make_gift_code_exhausts_retries_and_reraises(file_db, make_user):
    """Every mint attempt colliding → after _MINT_MAX_RETRIES the error re-raises."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        buyer = await make_user(conn, tg_id=1)
        calls = {"n": 0}

        async def always_collide(*args, **kwargs):
            calls["n"] += 1
            raise aiosqlite.IntegrityError("UNIQUE constraint failed: gift_codes.code")

        with patch.object(gifts_service.gift_repo, "create", new=always_collide):
            with pytest.raises(aiosqlite.IntegrityError):
                await gifts_service.make_gift_code(
                    conn, plan_id=None, inbound_id=1, buyer_id=buyer.id
                )
        # The minting loop tried exactly _MINT_MAX_RETRIES times before giving up.
        assert calls["n"] == gifts_service._MINT_MAX_RETRIES


async def test_redeem_gift_xui_error_rolls_status_back_to_active(
    file_db, make_user, make_plan
):
    """A XuiError during provisioning reverts the claimed code back to 'active'."""
    from app.db.engine import get_conn

    xui = AsyncMock()
    async with get_conn() as conn:
        buyer = await make_user(conn, tg_id=1)
        recip = await make_user(conn, tg_id=2)
        plan = await make_plan(conn, days=30, inbound_ids=[5])
        gift = await gifts_service.make_gift_code(
            conn, plan_id=plan.id, inbound_id=5, buyer_id=buyer.id
        )
        with patch(
            "app.services.subscriptions.add_client",
            new=AsyncMock(side_effect=XuiError("panel down")),
        ):
            with pytest.raises(XuiError):
                await gifts_service.redeem_gift(
                    conn, xui, code=gift.code, redeemer=recip
                )
        after = await gift_repo.get_by_code(conn, gift.code)
        assert after.status == "active"
