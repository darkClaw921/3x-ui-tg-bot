"""Tests for :mod:`app.services.billing` — price math, payload, send_invoice."""

from __future__ import annotations

import json

import pytest

from app.db.repos.plans import Plan
from app.db.repos.promos import Promo
from app.services import billing


def _plan(price=100, days=30, plan_id=1, active=True):
    return Plan(
        id=plan_id,
        title="t",
        days=days,
        price_stars=price,
        is_active=active,
        created_at="2025",
    )


def _promo(promo_type, value, max_uses=0, expires_at=None, used_count=0, promo_id=1):
    return Promo(
        id=promo_id,
        code="C",
        type=promo_type,
        value=value,
        max_uses=max_uses,
        used_count=used_count,
        expires_at=expires_at,
        created_at="2025",
        created_by=None,
    )


def test_calc_price_no_promo():
    p = billing.calc_price(_plan(100), None)
    assert p.stars == 100
    assert p.extra_days == 0


def test_calc_price_percent_basic():
    p = billing.calc_price(_plan(100), _promo("percent", 50))
    assert p.stars == 50
    assert p.extra_days == 0


def test_calc_price_percent_ceiling():
    """33% off 99 = 66.33 → ceil → 67."""
    # discount of 33% leaves 67% → ceil(99 * 0.67) = ceil(66.33) = 67
    p = billing.calc_price(_plan(99), _promo("percent", 33))
    assert p.stars == 67


def test_calc_price_percent_100_floors_to_one():
    p = billing.calc_price(_plan(50), _promo("percent", 100))
    assert p.stars == 1  # floor at Stars min


def test_calc_price_percent_clamped_high():
    """value>100 is clamped to 100."""
    p = billing.calc_price(_plan(50), _promo("percent", 150))
    assert p.stars == 1


def test_calc_price_percent_clamped_low():
    p = billing.calc_price(_plan(50), _promo("percent", -10))
    assert p.stars == 50


def test_calc_price_flat_stars():
    p = billing.calc_price(_plan(100), _promo("flat_stars", 30))
    assert p.stars == 70


def test_calc_price_flat_stars_exceeds_floor():
    p = billing.calc_price(_plan(100), _promo("flat_stars", 999))
    assert p.stars == 1


def test_calc_price_free_days_keeps_price():
    p = billing.calc_price(_plan(50), _promo("free_days", 7))
    assert p.stars == 50
    assert p.extra_days == 7


def test_calc_price_free_days_negative_clamped():
    p = billing.calc_price(_plan(50), _promo("free_days", -3))
    assert p.extra_days == 0


def test_calc_price_unknown_type_fallback():
    """Promo with bogus type defaults to the plan price."""
    p = billing.calc_price(_plan(100), _promo("WEIRD", 50))  # type: ignore[arg-type]
    assert p.stars == 100


def test_calc_price_min_one_zero_priced_plan():
    """A free plan with no promo also yields 1 (Stars min)."""
    p = billing.calc_price(_plan(0), None)
    assert p.stars == 1


def test_build_payload_encodes_correctly():
    out = billing.build_invoice_payload(1, 2)
    data = json.loads(out)
    assert data["plan_id"] == 1
    assert data["promo_id"] == 2


def test_build_payload_no_promo():
    out = billing.build_invoice_payload(1, None)
    data = json.loads(out)
    assert data["promo_id"] is None


def test_build_payload_promo_zero_treated_as_none():
    out = billing.build_invoice_payload(1, 0)
    data = json.loads(out)
    assert data["promo_id"] is None


def test_parse_payload_basic():
    p = billing.build_invoice_payload(7, 9)
    plan_id, promo_id = billing.parse_invoice_payload(p)
    assert plan_id == 7 and promo_id == 9


def test_parse_payload_no_promo():
    p = billing.build_invoice_payload(7, None)
    plan_id, promo_id = billing.parse_invoice_payload(p)
    assert promo_id is None


def test_parse_payload_zero_promo_id_becomes_none():
    # Manually construct a payload where promo_id=0.
    p = json.dumps({"plan_id": 1, "promo_id": 0})
    plan_id, promo_id = billing.parse_invoice_payload(p)
    assert plan_id == 1
    assert promo_id is None


def test_parse_payload_bad_json():
    with pytest.raises(ValueError):
        billing.parse_invoice_payload("not-json")


def test_parse_payload_not_object():
    with pytest.raises(ValueError):
        billing.parse_invoice_payload(json.dumps([1, 2]))


def test_parse_payload_missing_plan_id():
    with pytest.raises(ValueError):
        billing.parse_invoice_payload(json.dumps({"promo_id": 1}))


def test_parse_payload_bad_promo_id_type():
    with pytest.raises(ValueError):
        billing.parse_invoice_payload(json.dumps({"plan_id": 1, "promo_id": "abc"}))


def test_payload_byte_limit_guard(monkeypatch):
    """An impossibly large plan_id is rejected if payload exceeds 128 bytes."""
    big = 10 ** 200  # not really json-encodable as int; force a manual oversize.
    # Force the limit check.
    monkeypatch.setattr(billing, "_PAYLOAD_BYTE_LIMIT", 5)
    with pytest.raises(ValueError):
        billing.build_invoice_payload(123456, 78910)


async def test_send_invoice_uses_xtr(mock_bot):
    """send_invoice fills currency='XTR' and Stars-min amount."""
    plan = _plan(price=100)
    await billing.send_invoice(mock_bot, chat_id=42, plan=plan, promo=None)
    args, kwargs = mock_bot.send_invoice.call_args
    assert kwargs["currency"] == "XTR"
    assert kwargs["chat_id"] == 42
    assert kwargs["provider_token"] == ""
    # prices list has at least one LabeledPrice with amount==100
    prices = kwargs["prices"]
    assert prices[0].amount == 100


async def test_send_invoice_with_percent_promo(mock_bot):
    plan = _plan(price=100)
    promo = _promo("percent", 30)
    await billing.send_invoice(mock_bot, chat_id=10, plan=plan, promo=promo)
    kwargs = mock_bot.send_invoice.call_args.kwargs
    # 30% off 100 → 70.
    assert kwargs["prices"][0].amount == 70


async def test_send_invoice_with_free_days(mock_bot):
    plan = _plan(price=50)
    promo = _promo("free_days", 7)
    await billing.send_invoice(mock_bot, chat_id=1, plan=plan, promo=promo)
    desc = mock_bot.send_invoice.call_args.kwargs["description"]
    assert "7" in desc


async def test_send_invoice_with_flat_stars(mock_bot):
    plan = _plan(price=100)
    promo = _promo("flat_stars", 30)
    await billing.send_invoice(mock_bot, chat_id=1, plan=plan, promo=promo)
    kwargs = mock_bot.send_invoice.call_args.kwargs
    assert "30" in kwargs["description"]
