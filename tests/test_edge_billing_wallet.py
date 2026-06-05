"""Boundary-value (edge) tests for the BILLING + WALLET + PAYMENTS domain.

This module intentionally covers **only** the craggy boundary cases that the
broader-coverage suites (``test_services_billing.py``, ``test_db_wallet.py``,
``test_services_wallet.py``, ``test_db_payments.py``,
``test_handlers_user_wallet.py``) do not already exercise:

* payload byte-budget *exactly* on the 128-byte limit (and one byte over);
* the ``calc_price`` Stars-minimum floor at its precise trigger points;
* ``try_spend`` / ``credit`` ledger boundaries (amount == balance, == balance+1,
  zero balance, idempotent refs, partial-unique NULL refs);
* ``payments`` period sums at the inclusive ``[start, end]`` boundaries, with
  refunded rows and synthetic ``wallet:`` charge ids.

Object-construction patterns (``_plan`` / ``_promo``) mirror the helpers in
``test_services_billing.py`` so the boundary tests build the same shapes the
existing suite does.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import aiosqlite
import pytest

from app.config import settings
from app.db.repos import payments as payments_repo
from app.db.repos import wallet as wallet_repo
from app.db.repos.plans import Plan
from app.db.repos.promos import Promo
from app.services import billing
from app.services import wallet as wallet_service

# --------------------------------------------------------------------------- #
# Local builders — kept in this file (conftest.py is not modified). They match
# the shapes used by tests/test_services_billing.py.
# --------------------------------------------------------------------------- #


def _plan(price: int = 100, days: int = 30, plan_id: int = 1) -> Plan:
    return Plan(
        id=plan_id,
        title="t",
        days=days,
        price_stars=price,
        traffic_gb=0,
        is_active=True,
        created_at="2025",
    )


def _promo(
    promo_type: str,
    value: int,
    *,
    promo_id: int = 1,
) -> Promo:
    return Promo(
        id=promo_id,
        code="C",
        type=promo_type,  # type: ignore[arg-type]
        value=value,
        max_uses=0,
        used_count=0,
        expires_at=None,
        created_at="2025",
        created_by=None,
    )


def _byte_len(payload: str) -> int:
    return len(payload.encode("utf-8"))


def _plan_id_at_byte_limit() -> int:
    """Return the largest ``plan_id`` whose buy-payload is exactly 128 bytes.

    Grows a 9-repunit ``plan_id`` until the encoded ``build_invoice_payload``
    reaches the limit, then steps back one digit if it overshot — landing on a
    value whose payload is *exactly* :data:`billing._PAYLOAD_BYTE_LIMIT` bytes.
    """
    n = 1
    while _byte_len(billing.build_invoice_payload(n, 1, inbound_id=1, sub_id=1)) < (
        billing._PAYLOAD_BYTE_LIMIT
    ):
        n = n * 10 + 9
    if _byte_len(billing.build_invoice_payload(n, 1, inbound_id=1, sub_id=1)) > (
        billing._PAYLOAD_BYTE_LIMIT
    ):
        n = (n - 9) // 10
    return n


# ============================================================================ #
# 1. Payload byte budget — EXACTLY at the 128-byte boundary
# ============================================================================ #


def test_payload_exactly_at_128_byte_limit_is_accepted():
    """A buy-payload sized exactly to the limit is accepted (<= not <)."""
    plan_id = _plan_id_at_byte_limit()
    payload = billing.build_invoice_payload(plan_id, 1, inbound_id=1, sub_id=1)
    assert _byte_len(payload) == billing._PAYLOAD_BYTE_LIMIT
    # Round-trips losslessly even at the exact budget edge.
    ctx = billing.parse_invoice_payload(payload)
    assert ctx.plan_id == plan_id
    assert ctx.sub_id == 1
    assert ctx.inbound_id == 1


def test_payload_one_byte_over_limit_raises():
    """One digit past the at-limit plan_id pushes to 129 bytes → ValueError."""
    over = _plan_id_at_byte_limit() * 10 + 9
    over_payload_size = _byte_len(
        json.dumps(
            {"p": over, "r": 1, "i": 1, "s": 1}, separators=(",", ":")
        )
    )
    assert over_payload_size == billing._PAYLOAD_BYTE_LIMIT + 1
    with pytest.raises(ValueError):
        billing.build_invoice_payload(over, 1, inbound_id=1, sub_id=1)


def test_topup_payload_just_under_then_over_limit(monkeypatch):
    """With a tight limit, a value that fits passes and +1 byte fails."""
    # {"k":"topup","t":9} is 19 bytes; {"k":"topup","t":99} is 20 bytes.
    monkeypatch.setattr(billing, "_PAYLOAD_BYTE_LIMIT", 19)
    ok = billing.build_topup_payload(9)
    assert _byte_len(ok) == 19  # exactly at the (patched) limit → accepted
    with pytest.raises(ValueError):
        billing.build_topup_payload(99)  # 20 bytes → over


# ============================================================================ #
# 2. Payload kind / sub_id / legacy boundaries
# ============================================================================ #


def test_parse_empty_string_raises():
    """An empty payload string is malformed JSON → ValueError."""
    with pytest.raises(ValueError):
        billing.parse_invoice_payload("")


def test_parse_whitespace_only_raises():
    """A whitespace-only payload is malformed JSON → ValueError."""
    with pytest.raises(ValueError):
        billing.parse_invoice_payload("   ")


def test_parse_truncated_json_raises():
    """A half-written JSON object is rejected."""
    with pytest.raises(ValueError):
        billing.parse_invoice_payload('{"p":1,"i":')


def test_legacy_payload_without_k_key_decodes_as_buy():
    """A bare ``{"p":..}`` (no ``k``) is the legacy buy kind."""
    ctx = billing.parse_invoice_payload(json.dumps({"p": 5, "i": 2}))
    assert ctx.kind == "buy"
    assert ctx.gift == 0
    assert ctx.topup == 0


def test_build_invoice_payload_sub_id_zero_omits_s_key():
    """sub_id == 0 → the ``s`` key is absent entirely (byte hygiene)."""
    payload = billing.build_invoice_payload(1, None, inbound_id=2, sub_id=0)
    assert "s" not in json.loads(payload)


def test_build_invoice_payload_sub_id_one_present():
    """The smallest non-zero sub_id (1) is the boundary where ``s`` appears."""
    payload = billing.build_invoice_payload(1, None, inbound_id=2, sub_id=1)
    assert json.loads(payload)["s"] == 1
    assert billing.parse_invoice_payload(payload).sub_id == 1


def test_subscription_payload_sub_id_one_present():
    """build_subscription_payload includes ``s`` at the sub_id=1 boundary."""
    payload = billing.build_subscription_payload(1, inbound_id=2, sub_id=1)
    assert json.loads(payload)["s"] == 1


def test_large_ids_roundtrip_under_budget():
    """Very large plan/promo/inbound ids still round-trip and fit the budget."""
    big_plan = 9_999_999_999_999
    big_promo = 8_888_888_888_888
    big_inbound = 7_777_777
    payload = billing.build_invoice_payload(
        big_plan, big_promo, inbound_id=big_inbound, sub_id=6_666_666
    )
    assert _byte_len(payload) <= billing._PAYLOAD_BYTE_LIMIT
    ctx = billing.parse_invoice_payload(payload)
    assert ctx.plan_id == big_plan
    assert ctx.promo_id == big_promo
    assert ctx.inbound_id == big_inbound
    assert ctx.sub_id == 6_666_666


def test_gift_payload_large_ids_roundtrip():
    """Gift payload with large plan/inbound/promo ids round-trips intact."""
    payload = billing.build_gift_payload(
        9_999_999_999, inbound_id=8_888_888, promo_id=7_777_777_777
    )
    assert _byte_len(payload) <= billing._PAYLOAD_BYTE_LIMIT
    ctx = billing.parse_invoice_payload(payload)
    assert ctx.kind == "gift"
    assert ctx.gift == 1
    assert ctx.plan_id == 9_999_999_999
    assert ctx.inbound_id == 8_888_888
    assert ctx.promo_id == 7_777_777_777


def test_topup_payload_at_minimum_one_star():
    """A top-up of exactly the Stars-minimum (1) is the lowest valid value."""
    payload = billing.build_topup_payload(billing._STARS_MIN)
    ctx = billing.parse_invoice_payload(payload)
    assert ctx.kind == "topup"
    assert ctx.topup == billing._STARS_MIN == 1


def test_topup_payload_below_minimum_rejected():
    """A top-up one Star below the minimum (0) is rejected at build time."""
    with pytest.raises(ValueError):
        billing.build_topup_payload(billing._STARS_MIN - 1)


# ============================================================================ #
# 3. calc_price — Stars-minimum floor at its precise trigger points
# ============================================================================ #


def test_calc_price_percent_100_clamps_zero_to_one():
    """percent=100 → raw 0 → floored to the Stars minimum (1)."""
    out = billing.calc_price(_plan(price=100), _promo("percent", 100))
    assert out.raw_discount.final_price == 0  # raw is unfloored
    assert out.stars == 1  # floored by calc_price


def test_calc_price_flat_stars_equal_to_price_floors_to_one():
    """flat_stars == price → raw 0 → floored to 1 (exact equality boundary)."""
    out = billing.calc_price(_plan(price=100), _promo("flat_stars", 100))
    assert out.raw_discount.final_price == 0
    assert out.stars == 1


def test_calc_price_flat_stars_one_below_price_is_one_star():
    """flat_stars == price-1 → raw 1 → stays 1 (just above the floor edge)."""
    out = billing.calc_price(_plan(price=100), _promo("flat_stars", 99))
    assert out.raw_discount.final_price == 1
    assert out.stars == 1


def test_calc_price_percent_zero_is_unchanged():
    """percent=0 is a no-op discount — price equals the plan price."""
    out = billing.calc_price(_plan(price=77), _promo("percent", 0))
    assert out.stars == 77
    assert out.extra_days == 0


def test_calc_price_zero_priced_plan_floors_to_one():
    """A 0-Star plan with no promo is floored up to the Stars minimum."""
    out = billing.calc_price(_plan(price=0), None)
    assert out.raw_discount.final_price == 0
    assert out.stars == 1


def test_calc_price_free_days_passes_extra_days_through():
    """free_days leaves price untouched but surfaces extra_days for the UI."""
    out = billing.calc_price(_plan(price=50, days=30), _promo("free_days", 14))
    assert out.stars == 50
    assert out.extra_days == 14


# ============================================================================ #
# 4. Invoice senders — XTR / provider_token / subscription_period boundaries
# ============================================================================ #


async def test_create_subscription_invoice_link_constants(mock_bot):
    """The recurring link uses XTR, empty provider_token, exact 30-day period."""
    plan = _plan(price=120, plan_id=9)
    await billing.create_subscription_invoice_link(
        mock_bot, plan, inbound_id=3, sub_id=0
    )
    kwargs = mock_bot.create_invoice_link.call_args.kwargs
    assert kwargs["currency"] == "XTR"
    assert kwargs["provider_token"] == ""
    assert kwargs["subscription_period"] == 2_592_000
    assert kwargs["subscription_period"] == billing.SUBSCRIPTION_PERIOD_SECONDS


async def test_create_subscription_invoice_link_floors_zero_price_plan(mock_bot):
    """A 0-Star plan's recurring link is charged at the Stars minimum (1)."""
    plan = _plan(price=0, plan_id=10)
    await billing.create_subscription_invoice_link(
        mock_bot, plan, inbound_id=1, sub_id=0
    )
    kwargs = mock_bot.create_invoice_link.call_args.kwargs
    assert kwargs["prices"][0].amount == 1


async def test_send_topup_invoice_at_one_star(mock_bot):
    """A 1-Star top-up is the minimum valid amount and is charged as-is."""
    await billing.send_topup_invoice(mock_bot, chat_id=7, stars=1, lang="en")
    kwargs = mock_bot.send_invoice.call_args.kwargs
    assert kwargs["currency"] == "XTR"
    assert kwargs["provider_token"] == ""
    assert kwargs["prices"][0].amount == 1
    assert json.loads(kwargs["payload"]) == {"k": "topup", "t": 1}


async def test_send_topup_invoice_large_amount(mock_bot):
    """A large top-up amount is carried verbatim into prices + payload."""
    await billing.send_topup_invoice(mock_bot, chat_id=7, stars=2_500_000, lang="en")
    kwargs = mock_bot.send_invoice.call_args.kwargs
    assert kwargs["prices"][0].amount == 2_500_000
    assert json.loads(kwargs["payload"]) == {"k": "topup", "t": 2_500_000}


# ============================================================================ #
# 5. wallet.try_spend — amount vs balance boundaries
# ============================================================================ #


async def test_try_spend_amount_equals_balance_plus_one_rejected(db_conn, make_user):
    """amount == balance + 1 is the first rejecting value above the funds line."""
    user = await make_user(db_conn)
    await wallet_service.credit(db_conn, user.id, 50, type="topup", ref="t:1")
    assert await wallet_service.try_spend(db_conn, user.id, 51, ref="b:1") is False
    # Ledger untouched after a rejected overdraw.
    assert await wallet_repo.balance(db_conn, user.id) == 50


async def test_try_spend_on_zero_balance_rejected(db_conn, make_user):
    """Any positive spend against a 0 balance is rejected."""
    user = await make_user(db_conn)
    assert await wallet_repo.balance(db_conn, user.id) == 0
    assert await wallet_service.try_spend(db_conn, user.id, 1, ref="b:1") is False
    assert await wallet_repo.balance(db_conn, user.id) == 0


async def test_try_spend_zero_amount_raises(db_conn, make_user):
    """amount == 0 is the boundary of the positive-amount guard → ValueError."""
    user = await make_user(db_conn)
    await wallet_service.credit(db_conn, user.id, 10, type="topup", ref="t:1")
    with pytest.raises(ValueError):
        await wallet_service.try_spend(db_conn, user.id, 0, ref="b:1")
    # The guard fired before any ledger write.
    assert await wallet_repo.balance(db_conn, user.id) == 10


async def test_try_spend_exact_balance_drains_to_zero(db_conn, make_user):
    """amount == balance succeeds and leaves the wallet at exactly 0."""
    user = await make_user(db_conn)
    await wallet_service.credit(db_conn, user.id, 33, type="topup", ref="t:1")
    assert await wallet_service.try_spend(db_conn, user.id, 33, ref="b:1") is True
    assert await wallet_repo.balance(db_conn, user.id) == 0
    # A subsequent 1-Star spend on the now-empty wallet is rejected.
    assert await wallet_service.try_spend(db_conn, user.id, 1, ref="b:2") is False


async def test_try_spend_replay_same_ref_no_second_debit(db_conn, make_user):
    """A replayed spend (same ref) is rejected and does not debit twice."""
    user = await make_user(db_conn)
    await wallet_service.credit(db_conn, user.id, 100, type="topup", ref="t:1")
    assert await wallet_service.try_spend(db_conn, user.id, 40, ref="b:dup") is True
    assert await wallet_repo.balance(db_conn, user.id) == 60
    # Replay — even though funds would cover a second debit, ref is reused.
    assert await wallet_service.try_spend(db_conn, user.id, 40, ref="b:dup") is False
    assert await wallet_repo.balance(db_conn, user.id) == 60


async def test_try_spend_mixed_credits_and_debits_sum_correctly(db_conn, make_user):
    """A sequence of credits + spends nets to the arithmetic sum."""
    user = await make_user(db_conn)
    await wallet_service.credit(db_conn, user.id, 100, type="topup", ref="t:1")
    await wallet_service.credit(db_conn, user.id, 50, type="referral_bonus", ref="t:2")
    assert await wallet_service.try_spend(db_conn, user.id, 70, ref="b:1") is True
    assert await wallet_service.try_spend(db_conn, user.id, 30, ref="b:2") is True
    # 100 + 50 - 70 - 30 = 50.
    assert await wallet_repo.balance(db_conn, user.id) == 50


# ============================================================================ #
# 6. wallet.credit / repo.add — idempotency + amount boundaries
# ============================================================================ #


async def test_credit_amount_one_is_minimum_positive(db_conn, make_user):
    """amount == 1 is the smallest accepted credit (the positive boundary)."""
    user = await make_user(db_conn)
    assert await wallet_service.credit(db_conn, user.id, 1, type="topup", ref="t:1") is True
    assert await wallet_repo.balance(db_conn, user.id) == 1


async def test_credit_duplicate_ref_returns_false_once(db_conn, make_user):
    """A duplicate ref is idempotent: second credit returns False, no double-add."""
    user = await make_user(db_conn)
    assert await wallet_service.credit(db_conn, user.id, 80, type="topup", ref="dup") is True
    assert (
        await wallet_service.credit(db_conn, user.id, 80, type="topup", ref="dup") is False
    )
    assert await wallet_repo.balance(db_conn, user.id) == 80


async def test_repo_add_null_ref_allows_many_rows(db_conn, make_user):
    """ref is None bypasses the partial-unique index → multiple rows allowed."""
    user = await make_user(db_conn)
    a = await wallet_repo.add(db_conn, user_id=user.id, type="refund", amount=5, ref=None)
    b = await wallet_repo.add(db_conn, user_id=user.id, type="refund", amount=5, ref=None)
    c = await wallet_repo.add(db_conn, user_id=user.id, type="refund", amount=5, ref=None)
    assert a is not None and b is not None and c is not None
    assert len({a.id, b.id, c.id}) == 3
    assert await wallet_repo.balance(db_conn, user.id) == 15


async def test_repo_add_duplicate_ref_returns_none(db_conn, make_user):
    """A duplicate non-NULL ref returns None (caught IntegrityError)."""
    user = await make_user(db_conn)
    first = await wallet_repo.add(
        db_conn, user_id=user.id, type="topup", amount=10, ref="x"
    )
    assert first is not None
    assert await wallet_repo.add(db_conn, user_id=user.id, type="topup", amount=10, ref="x") is None


async def test_credit_zero_and_negative_amounts_rejected(db_conn, make_user):
    """The credit guard rejects both the zero boundary and negative amounts."""
    user = await make_user(db_conn)
    with pytest.raises(ValueError):
        await wallet_service.credit(db_conn, user.id, 0, type="topup")
    with pytest.raises(ValueError):
        await wallet_service.credit(db_conn, user.id, -1, type="topup")
    # Neither attempt touched the ledger.
    assert await wallet_repo.balance(db_conn, user.id) == 0


# ============================================================================ #
# 7. payments repo — UNIQUE charge_id + period-sum boundaries
# ============================================================================ #


async def _mk_payment(
    conn: aiosqlite.Connection,
    user_id: int,
    charge_id: str,
    stars: int,
    *,
    created_at: str | None = None,
    status: str = "paid",
):
    """Insert a payment row with an optional explicit ``created_at``.

    ``payments_repo.create`` always uses the DB default timestamp, so for the
    period-boundary tests we insert directly to pin ``created_at`` to an exact
    value (the only way to test the inclusive ``[start, end]`` edges).
    """
    if created_at is None:
        return await payments_repo.create(
            conn,
            user_id=user_id,
            subscription_id=None,
            telegram_charge_id=charge_id,
            stars_amount=stars,
            plan_id=None,
            promo_id=None,
            status=status,  # type: ignore[arg-type]
        )
    await conn.execute(
        "INSERT INTO payments "
        "(user_id, subscription_id, telegram_charge_id, stars_amount, "
        " plan_id, promo_id, status, created_at) "
        "VALUES (?, NULL, ?, ?, NULL, NULL, ?, ?)",
        (user_id, charge_id, stars, status, created_at),
    )
    await conn.commit()
    return await payments_repo.get_by_charge_id(conn, charge_id)


async def test_duplicate_charge_id_raises_integrity_error(db_conn, make_user):
    """A second payment with the same telegram_charge_id violates UNIQUE."""
    user = await make_user(db_conn)
    await _mk_payment(db_conn, user.id, "charge-1", 10)
    with pytest.raises(aiosqlite.IntegrityError):
        await _mk_payment(db_conn, user.id, "charge-1", 99)


async def test_total_stars_period_inclusive_at_both_bounds(db_conn, make_user):
    """A payment created at start (and one at end) is INCLUDED (inclusive range)."""
    user = await make_user(db_conn)
    start_iso = "2025-06-01 00:00:00"
    end_iso = "2025-06-30 23:59:59"
    # Exactly on the start boundary.
    await _mk_payment(db_conn, user.id, "at-start", 11, created_at=start_iso)
    # Exactly on the end boundary.
    await _mk_payment(db_conn, user.id, "at-end", 22, created_at=end_iso)
    total = await payments_repo.total_stars_period(db_conn, start_iso, end_iso)
    assert total == 33


async def test_total_stars_period_excludes_just_outside_bounds(db_conn, make_user):
    """Rows one second before start / after end are EXCLUDED."""
    user = await make_user(db_conn)
    start_iso = "2025-06-01 00:00:00"
    end_iso = "2025-06-30 23:59:59"
    await _mk_payment(db_conn, user.id, "before", 5, created_at="2025-05-31 23:59:59")
    await _mk_payment(db_conn, user.id, "after", 7, created_at="2025-07-01 00:00:00")
    await _mk_payment(db_conn, user.id, "inside", 13, created_at="2025-06-15 12:00:00")
    total = await payments_repo.total_stars_period(db_conn, start_iso, end_iso)
    assert total == 13


async def test_total_stars_period_excludes_refunded_within_range(db_conn, make_user):
    """A refunded row inside the range is excluded from the sum."""
    user = await make_user(db_conn)
    start_iso = "2025-06-01 00:00:00"
    end_iso = "2025-06-30 23:59:59"
    await _mk_payment(db_conn, user.id, "paid", 40, created_at="2025-06-10 00:00:00")
    await _mk_payment(
        db_conn, user.id, "refunded", 60, created_at="2025-06-11 00:00:00",
        status="refunded",
    )
    total = await payments_repo.total_stars_period(db_conn, start_iso, end_iso)
    assert total == 40


async def test_total_stars_period_empty_range_is_zero(db_conn, make_user):
    """A range with no matching rows returns 0 (COALESCE), not None."""
    user = await make_user(db_conn)
    await _mk_payment(db_conn, user.id, "far", 99, created_at="2020-01-01 00:00:00")
    total = await payments_repo.total_stars_period(
        db_conn, "2025-06-01 00:00:00", "2025-06-30 23:59:59"
    )
    assert total == 0


async def test_total_stars_period_counts_synthetic_wallet_charge_id(db_conn, make_user):
    """A pay-from-balance row (charge_id ``wallet:<id>``) is counted like any paid row."""
    user = await make_user(db_conn)
    await _mk_payment(
        db_conn, user.id, "wallet:123", 25, created_at="2025-06-15 09:00:00"
    )
    total = await payments_repo.total_stars_period(
        db_conn, "2025-06-01 00:00:00", "2025-06-30 23:59:59"
    )
    assert total == 25
    # And the synthetic charge id is retrievable by lookup.
    found = await payments_repo.get_by_charge_id(db_conn, "wallet:123")
    assert found is not None
    assert found.stars_amount == 25


async def test_total_stars_period_accepts_datetime_bounds(db_conn, make_user):
    """Period bounds may be aware datetimes (normalized to UTC ISO)."""
    user = await make_user(db_conn)
    now = datetime.now(UTC).replace(microsecond=0)
    await _mk_payment(db_conn, user.id, "now", 17)  # DB default ~ now
    start = now - timedelta(minutes=5)
    end = now + timedelta(minutes=5)
    total = await payments_repo.total_stars_period(db_conn, start, end)
    assert total == 17


# Sanity: the local helper actually targets the byte limit the suite references.
def test_settings_xui_inbound_id_is_an_int_like_value():
    """Guards the legacy-fallback assumptions used elsewhere in the domain."""
    assert int(settings.XUI_INBOUND_ID) >= 1
