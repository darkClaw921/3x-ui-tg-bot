"""Tests for :mod:`app.db.repos.gift_codes` — purchasable gift codes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import aiosqlite
import pytest

from app.db.repos import gift_codes as gift_repo


async def test_create_returns_active_row(db_conn, make_user):
    buyer = await make_user(db_conn, tg_id=1)
    g = await gift_repo.create(
        db_conn, code="GIFT-AAAA1111", plan_id=None, inbound_id=5, buyer_id=buyer.id
    )
    assert g.code == "GIFT-AAAA1111"
    assert g.status == "active"
    assert g.inbound_id == 5
    assert g.buyer_id == buyer.id
    assert g.redeemed_by is None
    assert g.subscription_id is None


async def test_create_duplicate_code_raises(db_conn, make_user):
    buyer = await make_user(db_conn, tg_id=1)
    await gift_repo.create(
        db_conn, code="GIFT-DUP", plan_id=None, inbound_id=1, buyer_id=buyer.id
    )
    with pytest.raises(aiosqlite.IntegrityError):
        await gift_repo.create(
            db_conn, code="GIFT-DUP", plan_id=None, inbound_id=1, buyer_id=buyer.id
        )


async def test_get_by_code_is_case_insensitive(db_conn, make_user):
    buyer = await make_user(db_conn, tg_id=1)
    await gift_repo.create(
        db_conn, code="GIFT-ABCDEF01", plan_id=None, inbound_id=1, buyer_id=buyer.id
    )
    found = await gift_repo.get_by_code(db_conn, "gift-abcdef01")
    assert found is not None
    assert found.code == "GIFT-ABCDEF01"
    assert await gift_repo.get_by_code(db_conn, "nope") is None


async def _make_sub(db_conn, user_id, inbound_id=5):
    from app.db.repos import subscriptions as subs_repo

    return await subs_repo.create(
        db_conn,
        user_id=user_id,
        xui_inbound_id=inbound_id,
        xui_client_uuid="u",
        xui_client_email="e",
        expires_at=datetime.now(UTC) + timedelta(days=30),
        plan_id=None,
        xui_sub_id="sid",
    )


async def test_try_redeem_claims_once(db_conn, make_user):
    buyer = await make_user(db_conn, tg_id=1)
    redeemer = await make_user(db_conn, tg_id=2)
    g = await gift_repo.create(
        db_conn, code="GIFT-CLAIM", plan_id=None, inbound_id=5, buyer_id=buyer.id
    )
    sub = await _make_sub(db_conn, redeemer.id)

    first = await gift_repo.try_redeem(
        db_conn, code="gift-claim", redeemed_by=redeemer.id, subscription_id=sub.id
    )
    assert first is True
    second = await gift_repo.try_redeem(
        db_conn, code="GIFT-CLAIM", redeemed_by=redeemer.id, subscription_id=sub.id
    )
    assert second is False

    after = await gift_repo.get(db_conn, g.id)
    assert after is not None
    assert after.status == "redeemed"
    assert after.redeemed_by == redeemer.id
    assert after.subscription_id == sub.id
    assert after.redeemed_at is not None


async def test_try_redeem_unknown_code_false(db_conn, make_user):
    redeemer = await make_user(db_conn, tg_id=2)
    sub = await _make_sub(db_conn, redeemer.id)
    ok = await gift_repo.try_redeem(
        db_conn, code="GIFT-MISSING", redeemed_by=redeemer.id, subscription_id=sub.id
    )
    assert ok is False


async def test_try_claim_then_link(db_conn, make_user):
    buyer = await make_user(db_conn, tg_id=1)
    redeemer = await make_user(db_conn, tg_id=2)
    g = await gift_repo.create(
        db_conn, code="GIFT-CL2", plan_id=None, inbound_id=5, buyer_id=buyer.id
    )
    claimed = await gift_repo.try_claim(
        db_conn, code="gift-cl2", redeemed_by=redeemer.id
    )
    assert claimed is not None
    assert claimed.status == "redeemed"
    assert claimed.subscription_id is None  # not linked yet
    # second claim fails
    assert await gift_repo.try_claim(db_conn, code="GIFT-CL2", redeemed_by=redeemer.id) is None

    sub = await _make_sub(db_conn, redeemer.id)
    await gift_repo.link_subscription(db_conn, g.id, sub.id)
    linked = await gift_repo.get(db_conn, g.id)
    assert linked is not None
    assert linked.subscription_id == sub.id


async def test_set_status_compensation(db_conn, make_user):
    buyer = await make_user(db_conn, tg_id=1)
    redeemer = await make_user(db_conn, tg_id=2)
    g = await gift_repo.create(
        db_conn, code="GIFT-COMP", plan_id=None, inbound_id=5, buyer_id=buyer.id
    )
    await gift_repo.try_claim(db_conn, code="GIFT-COMP", redeemed_by=redeemer.id)
    await gift_repo.set_status(db_conn, g.id, "active")
    reverted = await gift_repo.get(db_conn, g.id)
    assert reverted is not None
    assert reverted.status == "active"


async def test_list_for_buyer(db_conn, make_user):
    buyer = await make_user(db_conn, tg_id=1)
    other = await make_user(db_conn, tg_id=2)
    await gift_repo.create(
        db_conn, code="GIFT-B1", plan_id=None, inbound_id=1, buyer_id=buyer.id
    )
    await gift_repo.create(
        db_conn, code="GIFT-B2", plan_id=None, inbound_id=1, buyer_id=buyer.id
    )
    await gift_repo.create(
        db_conn, code="GIFT-O1", plan_id=None, inbound_id=1, buyer_id=other.id
    )
    mine = await gift_repo.list_for_buyer(db_conn, buyer.id)
    assert len(mine) == 2
    assert {g.code for g in mine} == {"GIFT-B1", "GIFT-B2"}
