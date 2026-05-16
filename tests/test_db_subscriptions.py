"""Tests for :mod:`app.db.repos.subscriptions`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db.repos import subscriptions as subs_repo
from app.db.repos.subscriptions import _to_iso


async def test_to_iso_naive_assumed_utc():
    dt = datetime(2025, 1, 1, 12, 0, 0)
    assert _to_iso(dt) == "2025-01-01 12:00:00+00:00"


async def test_to_iso_passes_str_through():
    assert _to_iso("2025-01-01 00:00:00") == "2025-01-01 00:00:00"


async def test_to_iso_aware_dt():
    dt = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert _to_iso(dt).startswith("2025-01-01 12:00:00")


async def test_create_and_get(db_conn, make_user):
    user = await make_user(db_conn)
    expires = datetime.now(UTC) + timedelta(days=30)
    sub = await subs_repo.create(
        db_conn,
        user_id=user.id,
        xui_inbound_id=1,
        xui_client_uuid="u1",
        xui_client_email="email1",
        expires_at=expires,
        plan_id=None,
        xui_sub_id="sid",
    )
    assert sub.xui_sub_id == "sid"
    assert sub.status == "active"

    got = await subs_repo.get(db_conn, sub.id)
    assert got is not None
    assert got.user_id == user.id


async def test_get_missing(db_conn):
    assert await subs_repo.get(db_conn, 999) is None


async def test_get_active_for_user_picks_latest(db_conn, make_user):
    user = await make_user(db_conn)
    now = datetime.now(UTC)
    s1 = await subs_repo.create(
        db_conn,
        user_id=user.id,
        xui_inbound_id=1,
        xui_client_uuid="u1",
        xui_client_email="e1",
        expires_at=now + timedelta(days=1),
        plan_id=None,
    )
    s2 = await subs_repo.create(
        db_conn,
        user_id=user.id,
        xui_inbound_id=1,
        xui_client_uuid="u2",
        xui_client_email="e2",
        expires_at=now + timedelta(days=10),
        plan_id=None,
    )
    active = await subs_repo.get_active_for_user(db_conn, user.id)
    assert active is not None
    assert active.id == s2.id


async def test_get_active_for_user_none(db_conn, make_user):
    user = await make_user(db_conn)
    assert await subs_repo.get_active_for_user(db_conn, user.id) is None


async def test_get_active_skips_expired(db_conn, make_user):
    user = await make_user(db_conn)
    past = datetime.now(UTC) - timedelta(days=1)
    await subs_repo.create(
        db_conn,
        user_id=user.id,
        xui_inbound_id=1,
        xui_client_uuid="u1",
        xui_client_email="e1",
        expires_at=past,
        plan_id=None,
    )
    assert await subs_repo.get_active_for_user(db_conn, user.id) is None


async def test_extend(db_conn, make_user, make_subscription):
    user = await make_user(db_conn)
    sub = await make_subscription(db_conn, user_id=user.id)
    new_exp = datetime.now(UTC) + timedelta(days=60)
    await subs_repo.extend(db_conn, sub.id, new_exp)
    fresh = await subs_repo.get(db_conn, sub.id)
    assert fresh.expires_at.startswith(new_exp.strftime("%Y-%m-%d"))


async def test_set_status(db_conn, make_user, make_subscription):
    user = await make_user(db_conn)
    sub = await make_subscription(db_conn, user_id=user.id)
    await subs_repo.set_status(db_conn, sub.id, "revoked")
    fresh = await subs_repo.get(db_conn, sub.id)
    assert fresh.status == "revoked"


async def test_list_expired_active(db_conn, make_user, make_subscription):
    user = await make_user(db_conn)
    past = datetime.now(UTC) - timedelta(days=1)
    future = datetime.now(UTC) + timedelta(days=1)
    s_past = await make_subscription(db_conn, user_id=user.id, expires_at=past)
    await make_subscription(
        db_conn,
        user_id=user.id,
        xui_client_uuid="u2",
        xui_client_email="e2",
        expires_at=future,
    )
    expired = await subs_repo.list_expired_active(db_conn)
    assert [s.id for s in expired] == [s_past.id]


async def test_list_expired_active_with_explicit_now(db_conn, make_user, make_subscription):
    user = await make_user(db_conn)
    far_future = datetime.now(UTC) + timedelta(days=100)
    s = await make_subscription(db_conn, user_id=user.id, expires_at=far_future)
    expired = await subs_repo.list_expired_active(
        db_conn, now=datetime.now(UTC) + timedelta(days=200)
    )
    assert [x.id for x in expired] == [s.id]


async def test_list_expired_active_with_iso_string(db_conn, make_user, make_subscription):
    user = await make_user(db_conn)
    far = datetime.now(UTC) + timedelta(days=100)
    s = await make_subscription(db_conn, user_id=user.id, expires_at=far)
    iso = "2999-01-01 00:00:00"
    expired = await subs_repo.list_expired_active(db_conn, now=iso)
    assert [x.id for x in expired] == [s.id]


async def test_list_expiring_in(db_conn, make_user, make_subscription):
    user = await make_user(db_conn)
    soon = datetime.now(UTC) + timedelta(days=2)
    far = datetime.now(UTC) + timedelta(days=20)
    s_soon = await make_subscription(db_conn, user_id=user.id, expires_at=soon)
    await make_subscription(
        db_conn,
        user_id=user.id,
        xui_client_uuid="u2",
        xui_client_email="e2",
        expires_at=far,
    )
    result = await subs_repo.list_expiring_in(db_conn, days=3)
    assert [s.id for s in result] == [s_soon.id]


async def test_list_active(db_conn, make_user, make_subscription):
    user = await make_user(db_conn)
    s = await make_subscription(db_conn, user_id=user.id)
    actives = await subs_repo.list_active(db_conn)
    assert s.id in {x.id for x in actives}


async def test_list_for_user_order(db_conn, make_user, make_subscription):
    user = await make_user(db_conn)
    s1 = await make_subscription(db_conn, user_id=user.id)
    s2 = await make_subscription(
        db_conn, user_id=user.id, xui_client_uuid="u2", xui_client_email="e2"
    )
    listed = await subs_repo.list_for_user(db_conn, user.id)
    ids = [s.id for s in listed]
    # Newest first → s2 then s1
    assert ids == [s2.id, s1.id]


async def test_add_and_last_traffic_snapshot(db_conn, make_user, make_subscription):
    user = await make_user(db_conn)
    sub = await make_subscription(db_conn, user_id=user.id)

    assert await subs_repo.last_traffic_snapshot(db_conn, sub.id) is None
    snap = await subs_repo.add_traffic_snapshot(db_conn, sub.id, up=10, down=20)
    assert snap.up == 10 and snap.down == 20

    last = await subs_repo.last_traffic_snapshot(db_conn, sub.id)
    assert last.id == snap.id


async def test_try_mark_notification_sent_dedup(db_conn, make_user, make_subscription):
    user = await make_user(db_conn)
    sub = await make_subscription(db_conn, user_id=user.id)

    first = await subs_repo.try_mark_notification_sent(db_conn, sub.id, "3d")
    assert first is True
    second = await subs_repo.try_mark_notification_sent(db_conn, sub.id, "3d")
    assert second is False


async def test_try_mark_notification_sent_different_kinds(db_conn, make_user, make_subscription):
    user = await make_user(db_conn)
    sub = await make_subscription(db_conn, user_id=user.id)
    assert await subs_repo.try_mark_notification_sent(db_conn, sub.id, "3d") is True
    assert await subs_repo.try_mark_notification_sent(db_conn, sub.id, "1d") is True
    assert await subs_repo.try_mark_notification_sent(db_conn, sub.id, "expired") is True
