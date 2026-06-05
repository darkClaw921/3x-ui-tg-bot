"""Tests for :mod:`app.services.billing` — price math, payload, send_invoice."""

from __future__ import annotations

import json

import pytest

from app.config import settings
from app.db.repos.plans import Plan
from app.db.repos.promos import Promo
from app.services import billing


def _plan(price=100, days=30, plan_id=1, active=True):
    return Plan(
        id=plan_id,
        title="t",
        days=days,
        price_stars=price,
        traffic_gb=0,
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


# ---------------------------------------------------------------------- #
# Payload — new 3-arg signature (plan_id, promo_id, inbound_id)
# ---------------------------------------------------------------------- #


def test_build_payload_encodes_correctly():
    out = billing.build_invoice_payload(1, 2, inbound_id=5)
    data = json.loads(out)
    # Compact form uses short keys 'p' / 'r' / 'i'.
    assert data["p"] == 1
    assert data["r"] == 2
    assert data["i"] == 5


def test_build_payload_no_promo():
    out = billing.build_invoice_payload(1, None, inbound_id=3)
    data = json.loads(out)
    assert data["r"] is None
    assert data["i"] == 3


def test_build_payload_promo_zero_treated_as_none():
    out = billing.build_invoice_payload(1, 0, inbound_id=3)
    data = json.loads(out)
    assert data["r"] is None


def test_parse_payload_basic():
    p = billing.build_invoice_payload(7, 9, inbound_id=4)
    plan_id, promo_id, inbound_id, _sub_id = billing.parse_invoice_payload(p)
    assert plan_id == 7
    assert promo_id == 9
    assert inbound_id == 4


def test_parse_payload_no_promo():
    p = billing.build_invoice_payload(7, None, inbound_id=4)
    plan_id, promo_id, inbound_id, _sub_id = billing.parse_invoice_payload(p)
    assert promo_id is None
    assert inbound_id == 4


def test_parse_payload_zero_promo_id_becomes_none():
    """An explicit ``r=0`` in the payload is normalised to None."""
    p = json.dumps({"p": 1, "r": 0, "i": 2})
    plan_id, promo_id, inbound_id, _sub_id = billing.parse_invoice_payload(p)
    assert plan_id == 1
    assert promo_id is None
    assert inbound_id == 2


def test_parse_payload_bad_json():
    with pytest.raises(ValueError):
        billing.parse_invoice_payload("not-json")


def test_parse_payload_not_object():
    with pytest.raises(ValueError):
        billing.parse_invoice_payload(json.dumps([1, 2]))


def test_parse_payload_missing_plan_id():
    with pytest.raises(ValueError):
        billing.parse_invoice_payload(json.dumps({"r": 1, "i": 2}))


def test_parse_payload_bad_promo_id_type():
    with pytest.raises(ValueError):
        billing.parse_invoice_payload(json.dumps({"p": 1, "r": "abc", "i": 2}))


def test_parse_payload_bad_inbound_id_type():
    """An explicit inbound_id that is not coercible to int raises ValueError."""
    with pytest.raises(ValueError):
        billing.parse_invoice_payload(json.dumps({"p": 1, "r": None, "i": "abc"}))


# --- Legacy payload fallback (pre-inbound-selection rollout) ---------- #


def test_parse_payload_legacy_long_keys():
    """Old payloads with ``plan_id``/``promo_id`` long keys still parse."""
    p = json.dumps({"plan_id": 7, "promo_id": 9})
    plan_id, promo_id, inbound_id, _sub_id = billing.parse_invoice_payload(p)
    assert plan_id == 7
    assert promo_id == 9
    # Missing ``i`` falls back to settings.XUI_INBOUND_ID.
    assert inbound_id == int(settings.XUI_INBOUND_ID)


def test_parse_payload_legacy_missing_inbound_falls_back():
    """Any payload missing ``i`` falls back to settings.XUI_INBOUND_ID."""
    p = json.dumps({"p": 1, "r": None})
    plan_id, promo_id, inbound_id, _sub_id = billing.parse_invoice_payload(p)
    assert plan_id == 1
    assert promo_id is None
    assert inbound_id == int(settings.XUI_INBOUND_ID)


def test_parse_payload_legacy_uses_patched_default(monkey_settings):
    """The fallback honours the *current* settings.XUI_INBOUND_ID value."""
    monkey_settings(XUI_INBOUND_ID=42)
    p = json.dumps({"p": 1, "r": None})
    _plan_id, _promo_id, inbound_id, _sub_id = billing.parse_invoice_payload(p)
    assert inbound_id == 42


# ---------------------------------------------------------------------- #
# Payload byte-limit guard
# ---------------------------------------------------------------------- #


def test_payload_byte_limit_guard(monkeypatch):
    """An impossibly large payload is rejected if it exceeds 128 bytes."""
    monkeypatch.setattr(billing, "_PAYLOAD_BYTE_LIMIT", 5)
    with pytest.raises(ValueError):
        billing.build_invoice_payload(123456, 78910, inbound_id=2)


def test_payload_fits_in_128_bytes_for_large_ids():
    """Realistic large ids (10 digits each) still fit in the 128-byte budget."""
    # 10-digit ids — comfortably larger than anything we'd realistically issue.
    out = billing.build_invoice_payload(9876543210, 1234567890, inbound_id=9999)
    assert len(out.encode("utf-8")) <= billing._PAYLOAD_BYTE_LIMIT


# ---------------------------------------------------------------------- #
# send_invoice — now requires ``inbound_id`` kwarg
# ---------------------------------------------------------------------- #


async def test_send_invoice_uses_xtr(mock_bot):
    """send_invoice fills currency='XTR' and Stars-min amount."""
    plan = _plan(price=100)
    await billing.send_invoice(
        mock_bot, chat_id=42, plan=plan, promo=None, inbound_id=3
    )
    args, kwargs = mock_bot.send_invoice.call_args
    assert kwargs["currency"] == "XTR"
    assert kwargs["chat_id"] == 42
    assert kwargs["provider_token"] == ""
    # prices list has at least one LabeledPrice with amount==100
    prices = kwargs["prices"]
    assert prices[0].amount == 100


async def test_send_invoice_embeds_inbound_id_in_payload(mock_bot):
    """The chosen inbound_id is threaded through into the invoice payload."""
    plan = _plan(price=100)
    await billing.send_invoice(
        mock_bot, chat_id=1, plan=plan, promo=None, inbound_id=7
    )
    payload = mock_bot.send_invoice.call_args.kwargs["payload"]
    data = json.loads(payload)
    assert data["i"] == 7
    assert data["p"] == plan.id
    assert data["r"] is None


async def test_send_invoice_with_percent_promo(mock_bot):
    plan = _plan(price=100)
    promo = _promo("percent", 30)
    await billing.send_invoice(
        mock_bot, chat_id=10, plan=plan, promo=promo, inbound_id=1
    )
    kwargs = mock_bot.send_invoice.call_args.kwargs
    # 30% off 100 → 70.
    assert kwargs["prices"][0].amount == 70


async def test_send_invoice_with_free_days(mock_bot):
    plan = _plan(price=50)
    promo = _promo("free_days", 7)
    await billing.send_invoice(
        mock_bot, chat_id=1, plan=plan, promo=promo, inbound_id=1
    )
    desc = mock_bot.send_invoice.call_args.kwargs["description"]
    assert "7" in desc


async def test_send_invoice_with_flat_stars(mock_bot):
    plan = _plan(price=100)
    promo = _promo("flat_stars", 30)
    await billing.send_invoice(
        mock_bot, chat_id=1, plan=plan, promo=promo, inbound_id=1
    )
    kwargs = mock_bot.send_invoice.call_args.kwargs
    assert "30" in kwargs["description"]


async def test_send_invoice_payload_includes_promo_id(mock_bot):
    """When a promo is attached its id appears in the payload as ``r``."""
    plan = _plan(price=100)
    promo = _promo("percent", 30, promo_id=42)
    await billing.send_invoice(
        mock_bot, chat_id=1, plan=plan, promo=promo, inbound_id=11
    )
    payload = mock_bot.send_invoice.call_args.kwargs["payload"]
    data = json.loads(payload)
    assert data["r"] == 42
    assert data["i"] == 11


# ---------------------------------------------------------------------- #
# Payload — sub_id (multiple subscriptions per user)
# ---------------------------------------------------------------------- #


def test_billing_payload_roundtrip_with_sub_id():
    """build → parse round-trips sub_id>0 and omits 's' when sub_id=0."""
    # With sub_id > 0: key 's' present, round-trip preserves the value.
    p = billing.build_invoice_payload(1, None, inbound_id=5, sub_id=42)
    data = json.loads(p)
    assert data["s"] == 42
    plan_id, promo_id, inbound_id, sub_id = billing.parse_invoice_payload(p)
    assert plan_id == 1
    assert promo_id is None
    assert inbound_id == 5
    assert sub_id == 42

    # With sub_id=0 (default): key 's' is omitted entirely for byte-budget
    # hygiene and legacy compatibility; parse returns sub_id=0.
    p0 = billing.build_invoice_payload(1, None, inbound_id=5, sub_id=0)
    assert '"s"' not in p0
    plan_id, promo_id, inbound_id, sub_id = billing.parse_invoice_payload(p0)
    assert plan_id == 1
    assert inbound_id == 5
    assert sub_id == 0


def test_billing_payload_legacy_without_s_returns_zero():
    """Hand-crafted legacy payloads with no 's' key parse as sub_id=0."""
    # New-style short keys, no 's'.
    p = json.dumps({"p": 1, "r": None, "i": 5})
    plan_id, promo_id, inbound_id, sub_id = billing.parse_invoice_payload(p)
    assert plan_id == 1
    assert promo_id is None
    assert inbound_id == 5
    assert sub_id == 0

    # Truly-legacy long-key payload (pre-inbound-selection rollout).
    p_legacy = json.dumps({"plan_id": 7, "promo_id": 9})
    plan_id, promo_id, inbound_id, sub_id = billing.parse_invoice_payload(p_legacy)
    assert plan_id == 7
    assert promo_id == 9
    assert sub_id == 0


# ---------------------------------------------------------------------- #
# InvoiceContext — structured payload + kind discriminator
# ---------------------------------------------------------------------- #


def test_parse_returns_invoice_context():
    """parse_invoice_payload returns an InvoiceContext, not a bare tuple."""
    ctx = billing.parse_invoice_payload(billing.build_invoice_payload(1, 2, inbound_id=3))
    assert isinstance(ctx, billing.InvoiceContext)
    assert ctx.plan_id == 1
    assert ctx.promo_id == 2
    assert ctx.inbound_id == 3
    assert ctx.sub_id == 0
    assert ctx.kind == "buy"
    assert ctx.gift == 0
    assert ctx.topup == 0


def test_invoice_context_is_frozen():
    """InvoiceContext is immutable (frozen dataclass)."""
    ctx = billing.InvoiceContext(plan_id=1, promo_id=None, inbound_id=2, sub_id=0)
    with pytest.raises((AttributeError, TypeError)):
        ctx.plan_id = 99  # type: ignore[misc]


def test_invoice_context_unpacks_as_legacy_4_tuple():
    """Old tuple-unpacking call sites keep working via __iter__."""
    ctx = billing.parse_invoice_payload(
        billing.build_invoice_payload(5, 6, inbound_id=7, sub_id=8)
    )
    plan_id, promo_id, inbound_id, sub_id = ctx
    assert (plan_id, promo_id, inbound_id, sub_id) == (5, 6, 7, 8)


def test_legacy_payload_decodes_as_kind_buy():
    """Any payload without a 'k' key is treated as a one-off purchase."""
    # New short-key payload, no 'k'.
    ctx = billing.parse_invoice_payload(json.dumps({"p": 1, "r": None, "i": 2}))
    assert ctx.kind == "buy"
    # Truly-legacy long-key payload.
    ctx_legacy = billing.parse_invoice_payload(json.dumps({"plan_id": 7, "promo_id": 9}))
    assert ctx_legacy.kind == "buy"
    assert ctx_legacy.plan_id == 7
    assert ctx_legacy.promo_id == 9


def test_parse_bad_kind_raises():
    """An unrecognised 'k' value is rejected."""
    with pytest.raises(ValueError):
        billing.parse_invoice_payload(json.dumps({"k": "bogus", "p": 1, "i": 2}))


# --- kind="topup" ----------------------------------------------------- #


def test_build_topup_payload_roundtrip():
    """build_topup_payload → parse round-trips kind/topup; no plan/inbound."""
    p = billing.build_topup_payload(150)
    data = json.loads(p)
    assert data["k"] == "topup"
    assert data["t"] == 150
    ctx = billing.parse_invoice_payload(p)
    assert ctx.kind == "topup"
    assert ctx.topup == 150
    assert ctx.plan_id == 0
    assert ctx.inbound_id == 0
    assert ctx.promo_id is None
    assert ctx.sub_id == 0


def test_build_topup_payload_rejects_below_minimum():
    """A top-up below the Stars minimum is rejected."""
    with pytest.raises(ValueError):
        billing.build_topup_payload(0)


def test_topup_payload_does_not_require_plan_id():
    """A top-up payload parses even though it carries no plan_id."""
    ctx = billing.parse_invoice_payload(json.dumps({"k": "topup", "t": 25}))
    assert ctx.kind == "topup"
    assert ctx.topup == 25


# --- kind="gift" ------------------------------------------------------ #


def test_build_gift_payload_roundtrip():
    """build_gift_payload → parse round-trips kind=gift, gift=1, plan/inbound."""
    p = billing.build_gift_payload(3, inbound_id=4, promo_id=5)
    data = json.loads(p)
    assert data["k"] == "gift"
    assert data["g"] == 1
    assert data["p"] == 3
    assert data["i"] == 4
    assert data["r"] == 5
    ctx = billing.parse_invoice_payload(p)
    assert ctx.kind == "gift"
    assert ctx.gift == 1
    assert ctx.plan_id == 3
    assert ctx.inbound_id == 4
    assert ctx.promo_id == 5


def test_build_gift_payload_no_promo():
    """gift payload without a promo encodes r=null and parses promo_id=None."""
    ctx = billing.parse_invoice_payload(billing.build_gift_payload(3, inbound_id=4))
    assert ctx.kind == "gift"
    assert ctx.promo_id is None


# --- kind="sub" ------------------------------------------------------- #


def test_build_subscription_payload_roundtrip():
    """build_subscription_payload → parse round-trips kind=sub, plan/inbound/sub_id."""
    p = billing.build_subscription_payload(7, inbound_id=8, sub_id=9)
    data = json.loads(p)
    assert data["k"] == "sub"
    assert data["p"] == 7
    assert data["i"] == 8
    assert data["s"] == 9
    ctx = billing.parse_invoice_payload(p)
    assert ctx.kind == "sub"
    assert ctx.plan_id == 7
    assert ctx.inbound_id == 8
    assert ctx.sub_id == 9


def test_build_subscription_payload_omits_s_when_new():
    """A new subscription (sub_id=0) omits the 's' key entirely."""
    p = billing.build_subscription_payload(7, inbound_id=8)
    assert '"s"' not in p
    ctx = billing.parse_invoice_payload(p)
    assert ctx.sub_id == 0


# ---------------------------------------------------------------------- #
# Byte-limit guard applies to every builder
# ---------------------------------------------------------------------- #


def test_topup_payload_byte_limit_guard(monkeypatch):
    monkeypatch.setattr(billing, "_PAYLOAD_BYTE_LIMIT", 5)
    with pytest.raises(ValueError):
        billing.build_topup_payload(123456789)


def test_gift_payload_byte_limit_guard(monkeypatch):
    monkeypatch.setattr(billing, "_PAYLOAD_BYTE_LIMIT", 5)
    with pytest.raises(ValueError):
        billing.build_gift_payload(123456, inbound_id=78910, promo_id=11121)


def test_subscription_payload_byte_limit_guard(monkeypatch):
    monkeypatch.setattr(billing, "_PAYLOAD_BYTE_LIMIT", 5)
    with pytest.raises(ValueError):
        billing.build_subscription_payload(123456, inbound_id=78910, sub_id=11121)


def test_new_kind_payloads_fit_in_128_bytes_for_large_ids():
    """Realistic large ids keep top-up / gift / sub payloads under the limit."""
    assert (
        len(billing.build_topup_payload(9999999).encode("utf-8"))
        <= billing._PAYLOAD_BYTE_LIMIT
    )
    assert (
        len(
            billing.build_gift_payload(
                9876543210, inbound_id=9999, promo_id=1234567890
            ).encode("utf-8")
        )
        <= billing._PAYLOAD_BYTE_LIMIT
    )
    assert (
        len(
            billing.build_subscription_payload(
                9876543210, inbound_id=9999, sub_id=1234567890
            ).encode("utf-8")
        )
        <= billing._PAYLOAD_BYTE_LIMIT
    )


# ---------------------------------------------------------------------- #
# create_subscription_invoice_link — native recurring Star subscription
# ---------------------------------------------------------------------- #


async def test_create_subscription_invoice_link_uses_subscription_period(mock_bot):
    """The link uses XTR + the exact 30-day subscription_period and a sub payload."""
    plan = _plan(price=100, plan_id=3)
    await billing.create_subscription_invoice_link(
        mock_bot, plan, inbound_id=7, sub_id=0
    )
    kwargs = mock_bot.create_invoice_link.call_args.kwargs
    assert kwargs["currency"] == "XTR"
    assert kwargs["provider_token"] == ""
    assert kwargs["subscription_period"] == billing.SUBSCRIPTION_PERIOD_SECONDS
    assert kwargs["subscription_period"] == 2592000
    assert kwargs["prices"][0].amount == 100
    data = json.loads(kwargs["payload"])
    assert data["k"] == "sub"
    assert data["p"] == plan.id
    assert data["i"] == 7
    # New subscription → no 's' key.
    assert "s" not in data


async def test_create_subscription_invoice_link_embeds_sub_id(mock_bot):
    """When extending an existing sub, sub_id is threaded into the payload."""
    plan = _plan(price=50, plan_id=4)
    await billing.create_subscription_invoice_link(
        mock_bot, plan, inbound_id=2, sub_id=99
    )
    payload = mock_bot.create_invoice_link.call_args.kwargs["payload"]
    data = json.loads(payload)
    assert data["k"] == "sub"
    assert data["s"] == 99


# --------------------------------------------------------------------------- #
# send_topup_invoice — wallet top-up
# --------------------------------------------------------------------------- #


async def test_send_topup_invoice_uses_xtr_and_topup_payload(mock_bot):
    """send_topup_invoice sends an XTR invoice carrying a kind='topup' payload."""
    await billing.send_topup_invoice(mock_bot, chat_id=42, stars=200, lang="en")
    kwargs = mock_bot.send_invoice.call_args.kwargs
    assert kwargs["currency"] == "XTR"
    assert kwargs["chat_id"] == 42
    assert kwargs["provider_token"] == ""
    assert kwargs["prices"][0].amount == 200
    data = json.loads(kwargs["payload"])
    assert data == {"k": "topup", "t": 200}


async def test_send_topup_invoice_floors_to_stars_min(mock_bot):
    """A 0-Stars top-up is floored to the Stars minimum (1)."""
    await billing.send_topup_invoice(mock_bot, chat_id=1, stars=0, lang="en")
    kwargs = mock_bot.send_invoice.call_args.kwargs
    assert kwargs["prices"][0].amount == 1
    assert json.loads(kwargs["payload"]) == {"k": "topup", "t": 1}
