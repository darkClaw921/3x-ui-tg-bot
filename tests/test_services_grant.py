"""Tests for :func:`app.services.subscriptions.grant_subscription`."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from app.db.repos import subscriptions as subs_repo
from app.services import subscriptions as subs_service


async def test_grant_default_days_uses_plan_days(db_conn, make_user, make_plan):
    user = await make_user(db_conn, tg_id=10)
    plan = await make_plan(db_conn, days=30, traffic_gb=5, inbound_ids=[7])
    xui = AsyncMock()
    sub = await subs_service.grant_subscription(
        db_conn, xui, user, plan=plan, inbound_id=7, days=None
    )
    assert sub.plan_id == plan.id
    assert sub.xui_inbound_id == 7
    expires = datetime.fromisoformat(sub.expires_at.replace(" ", "T")).replace(
        tzinfo=UTC
    )
    delta_days = (expires - datetime.now(UTC)).days
    assert 28 <= delta_days <= 30


async def test_grant_explicit_days_override(db_conn, make_user, make_plan):
    user = await make_user(db_conn, tg_id=10)
    plan = await make_plan(db_conn, days=30, inbound_ids=[7])
    xui = AsyncMock()
    sub = await subs_service.grant_subscription(
        db_conn, xui, user, plan=plan, inbound_id=7, days=3
    )
    expires = datetime.fromisoformat(sub.expires_at.replace(" ", "T")).replace(
        tzinfo=UTC
    )
    delta_days = (expires - datetime.now(UTC)).days
    assert delta_days <= 3


async def test_grant_creates_fresh_subscription(db_conn, make_user, make_plan):
    """Two grants always create two distinct subscriptions (no extend)."""
    user = await make_user(db_conn, tg_id=10)
    plan = await make_plan(db_conn, days=30, inbound_ids=[7])
    xui = AsyncMock()
    s1 = await subs_service.grant_subscription(
        db_conn, xui, user, plan=plan, inbound_id=7
    )
    s2 = await subs_service.grant_subscription(
        db_conn, xui, user, plan=plan, inbound_id=7
    )
    assert s1.id != s2.id
    all_subs = await subs_repo.list_for_user(db_conn, user.id)
    assert {s1.id, s2.id} <= {s.id for s in all_subs}


async def test_grant_calls_xui_add_client(db_conn, make_user, make_plan):
    user = await make_user(db_conn, tg_id=10)
    plan = await make_plan(db_conn, days=30, inbound_ids=[7])
    xui = AsyncMock()
    await subs_service.grant_subscription(
        db_conn, xui, user, plan=plan, inbound_id=7
    )
    # add_client issues a panel request — verify the xui client was used.
    assert xui.request_json.await_count >= 1 or xui.request.await_count >= 1
