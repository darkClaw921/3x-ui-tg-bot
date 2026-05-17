"""Tests for :mod:`app.services.subscriptions`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.db.repos.plans import Plan
from app.db.repos.promos import Promo
from app.services import subscriptions as subs_service
from app.xui import XuiError


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


def _promo(promo_type="free_days", value=5, promo_id=1):
    return Promo(
        id=promo_id,
        code="C",
        type=promo_type,
        value=value,
        max_uses=0,
        used_count=0,
        expires_at=None,
        created_at="2025",
        created_by=None,
    )


def test_expiry_ms_naive_converted_to_utc():
    from app.services.subscriptions import _expiry_ms

    dt = datetime(2025, 1, 1)
    ms = _expiry_ms(dt)
    assert ms > 0


def test_parse_iso_t_separator():
    from app.services.subscriptions import _parse_iso

    dt = _parse_iso("2025-01-01T12:00:00")
    assert dt.year == 2025 and dt.hour == 12


def test_parse_iso_space_separator():
    from app.services.subscriptions import _parse_iso

    dt = _parse_iso("2025-01-01 12:00:00")
    assert dt.year == 2025


def test_parse_iso_with_microseconds_fallback():
    from app.services.subscriptions import _parse_iso

    # Should hit fallback strptime path
    dt = _parse_iso("2025-01-01 12:00:00 extra")
    assert dt.year == 2025


def test_bonus_days():
    from app.services.subscriptions import _bonus_days_from_promo

    assert _bonus_days_from_promo(None) == 0
    assert _bonus_days_from_promo(_promo("free_days", 5)) == 5
    assert _bonus_days_from_promo(_promo("percent", 50)) == 0


async def test_create_or_extend_creates_new(file_db, make_user, make_plan):
    """No existing subscription → add_client called, DB row inserted."""
    from app.db.engine import get_conn

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"id": "uuid", "email": "e"})

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        plan = await make_plan(conn, days=30, price_stars=100)
        sub = await subs_service.create_or_extend(
            conn=conn, xui=xui, user=user, plan=plan, promo=None, inbound_id=1,
        )

    assert sub.user_id == user.id
    assert sub.plan_id == plan.id
    # add_client was called.
    assert xui.request_json.await_count >= 1


async def test_provision_passes_username_to_make_client_email(
    file_db, make_user, make_plan, monkeypatch
):
    """Fresh provisioning must forward user.username to make_client_email
    so the panel-side email label includes the human-readable handle."""
    from app.db.engine import get_conn
    from app.services import subscriptions as svc

    captured: dict[str, object] = {}

    def fake_make_client_email(tg_id, username=None):
        captured["tg_id"] = tg_id
        captured["username"] = username
        return f"fake_tg_{tg_id}_xxxxxx"

    monkeypatch.setattr(svc, "make_client_email", fake_make_client_email)

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"id": "uuid", "email": "e"})

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=42, username="Alice")
        plan = await make_plan(conn, days=30, price_stars=100)
        await svc.create_or_extend(
            conn=conn, xui=xui, user=user, plan=plan, promo=None, inbound_id=1,
        )

    assert captured["tg_id"] == 42
    assert captured["username"] == "Alice"


async def test_provision_passes_none_username_when_user_has_no_handle(
    file_db, make_user, make_plan, monkeypatch
):
    """Users without a Telegram @handle get username=None passed through."""
    from app.db.engine import get_conn
    from app.services import subscriptions as svc

    captured: dict[str, object] = {}

    def fake_make_client_email(tg_id, username=None):
        captured["tg_id"] = tg_id
        captured["username"] = username
        return f"fake_tg_{tg_id}_xxxxxx"

    monkeypatch.setattr(svc, "make_client_email", fake_make_client_email)

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"id": "uuid", "email": "e"})

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=99, username=None)
        plan = await make_plan(conn, days=30, price_stars=100)
        await svc.create_or_extend(
            conn=conn, xui=xui, user=user, plan=plan, promo=None, inbound_id=1,
        )

    assert captured["tg_id"] == 99
    assert captured["username"] is None


async def test_provision_passes_plan_traffic_gb_to_add_client(
    file_db, make_user, make_plan, monkeypatch
):
    """create_or_extend with plan.traffic_gb=50 → add_client(total_gb=50)."""
    from app.db.engine import get_conn
    from app.services import subscriptions as svc

    captured: dict[str, object] = {}

    async def fake_add_client(client, **kwargs):
        captured.update(kwargs)
        return {"id": kwargs.get("client_uuid"), "email": kwargs.get("email")}

    monkeypatch.setattr(svc, "add_client", fake_add_client)

    xui = AsyncMock()

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=11)
        plan = await make_plan(conn, days=30, price_stars=100, traffic_gb=50)
        await svc.create_or_extend(
            conn=conn, xui=xui, user=user, plan=plan, promo=None, inbound_id=1,
        )

    assert captured.get("total_gb") == 50


async def test_provision_passes_zero_traffic_gb_to_add_client(
    file_db, make_user, make_plan, monkeypatch
):
    """create_or_extend with plan.traffic_gb=0 → add_client(total_gb=0)."""
    from app.db.engine import get_conn
    from app.services import subscriptions as svc

    captured: dict[str, object] = {}

    async def fake_add_client(client, **kwargs):
        captured.update(kwargs)
        return {"id": kwargs.get("client_uuid"), "email": kwargs.get("email")}

    monkeypatch.setattr(svc, "add_client", fake_add_client)

    xui = AsyncMock()

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=12)
        plan = await make_plan(conn, days=30, price_stars=100, traffic_gb=0)
        await svc.create_or_extend(
            conn=conn, xui=xui, user=user, plan=plan, promo=None, inbound_id=1,
        )

    assert captured.get("total_gb") == 0


async def test_activate_free_days_passes_zero_total_gb(
    file_db, make_user, monkeypatch
):
    """activate_free_days has no plan → add_client(total_gb=0)."""
    from app.db.engine import get_conn
    from app.services import subscriptions as svc

    captured: dict[str, object] = {}

    async def fake_add_client(client, **kwargs):
        captured.update(kwargs)
        return {"id": kwargs.get("client_uuid"), "email": kwargs.get("email")}

    monkeypatch.setattr(svc, "add_client", fake_add_client)

    xui = AsyncMock()

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=13)
        await svc.activate_free_days(
            conn=conn, xui=xui, user=user, promo=_promo("free_days", 14), inbound_id=1,
        )

    assert captured.get("total_gb") == 0


async def test_extend_does_not_send_total_gb_to_update_client(
    file_db, make_user, make_subscription, monkeypatch
):
    """When extending an existing sub, update_client must NOT receive totalGB
    in kwargs — we deliberately preserve the user's accumulated quota."""
    from app.db.engine import get_conn
    from app.services import subscriptions as svc

    captured_kwargs: list[dict[str, object]] = []

    async def fake_update_client(client, *, inbound_id, client_uuid, **kwargs):
        captured_kwargs.append(dict(kwargs))
        return {"id": client_uuid}

    monkeypatch.setattr(svc, "update_client", fake_update_client)

    xui = AsyncMock()

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=14)
        sub = await make_subscription(conn, user_id=user.id)
        await svc.create_or_extend(
            conn=conn,
            xui=xui,
            user=user,
            plan=_plan(days=30),
            promo=None,
            inbound_id=1,
            extend_sub_id=sub.id,
        )

    assert captured_kwargs, "update_client was not invoked on extend"
    for kw in captured_kwargs:
        assert "totalGB" not in kw, (
            f"update_client received totalGB={kw.get('totalGB')!r}; "
            "this would reset the user's traffic quota on renewal"
        )


async def test_create_or_extend_when_extend_sub_id_given(
    file_db, make_user, make_subscription
):
    """With explicit extend_sub_id, the specified sub is extended in place."""
    from app.db.engine import get_conn

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value=None)

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        sub = await make_subscription(conn, user_id=user.id)
        old_expires = sub.expires_at
        new_sub = await subs_service.create_or_extend(
            conn=conn,
            xui=xui,
            user=user,
            plan=_plan(days=30),
            promo=None,
            inbound_id=1,
            extend_sub_id=sub.id,
        )

    assert new_sub.id == sub.id
    assert new_sub.expires_at > old_expires
    # update_client was called (not add_client).
    call_paths = [c.args[1] for c in xui.request_json.call_args_list]
    assert any("updateClient" in p for p in call_paths)


async def test_create_or_extend_xui_failure_blocks_db_write(file_db, make_user):
    """If add_client raises XuiError, the DB write must not happen."""
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo

    xui = AsyncMock()
    xui.request_json = AsyncMock(side_effect=XuiError("panel down"))

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        with pytest.raises(XuiError):
            await subs_service.create_or_extend(
                conn=conn, xui=xui, user=user, plan=_plan(), promo=None, inbound_id=1,
            )
        # Verify no subscription was inserted.
        rows = await subs_repo.list_for_user(conn, user.id)
        assert rows == []


async def test_create_or_extend_with_free_days_promo_adds_days(file_db, make_user, make_plan):
    from app.db.engine import get_conn

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"id": "uuid"})

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        plan = await make_plan(conn, days=30, price_stars=100)
        sub = await subs_service.create_or_extend(
            conn=conn,
            xui=xui,
            user=user,
            plan=plan,
            promo=_promo("free_days", 7),
            inbound_id=1,
        )

    expires_dt = datetime.fromisoformat(sub.expires_at.replace(" ", "T"))
    delta = (expires_dt.replace(tzinfo=UTC) - datetime.now(UTC)).days
    # 37 ± 1 day tolerance
    assert 35 <= delta <= 38


async def test_activate_free_days_rejects_non_free_days(file_db, make_user):
    from app.db.engine import get_conn

    xui = AsyncMock()
    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        with pytest.raises(ValueError):
            await subs_service.activate_free_days(
                conn=conn, xui=xui, user=user, promo=_promo("percent", 10), inbound_id=1,
            )


async def test_activate_free_days_provisions(file_db, make_user):
    from app.db.engine import get_conn

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"id": "u"})

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        sub = await subs_service.activate_free_days(
            conn=conn, xui=xui, user=user, promo=_promo("free_days", 14), inbound_id=1,
        )
    assert sub.user_id == user.id
    assert sub.plan_id is None


async def test_revoke_calls_xui_and_updates_status(file_db, make_user, make_subscription):
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value=None)

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        sub = await make_subscription(conn, user_id=user.id)

    await subs_service.revoke(xui, sub)

    async with get_conn() as conn:
        fresh = await subs_repo.get(conn, sub.id)
    assert fresh.status == "revoked"
    # xui.update_client was called with enable=False inside body.
    paths = [c.args[1] for c in xui.request_json.call_args_list]
    assert any("updateClient" in p for p in paths)


async def test_revoke_xui_failure_still_marks_db(file_db, make_user, make_subscription):
    """Even when xui.update_client fails, status flips to revoked."""
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo

    xui = AsyncMock()
    xui.request_json = AsyncMock(side_effect=XuiError("down"))

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        sub = await make_subscription(conn, user_id=user.id)

    await subs_service.revoke(xui, sub)

    async with get_conn() as conn:
        fresh = await subs_repo.get(conn, sub.id)
    assert fresh.status == "revoked"


async def test_create_or_extend_anchors_past_expiry_to_now(file_db, make_user, make_plan):
    """When extending a stale active row, the delta anchors to now (not past)."""
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value=None)

    past = datetime.now(UTC) - timedelta(days=10)
    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        # Insert a status=active sub but with a past expires_at (this can
        # happen between the expire-checker runs).
        stale = await subs_repo.create(
            conn,
            user_id=user.id,
            xui_inbound_id=1,
            xui_client_uuid="uuid",
            xui_client_email="e",
            expires_at=past,
            plan_id=None,
            xui_sub_id="sub",
        )
        # Explicitly extend the stale sub — the service must anchor the
        # new expiry to `now`, not to the past expires_at, so the user
        # gets the full delta of plan.days.
        plan = await make_plan(conn, days=10, price_stars=50)
        new = await subs_service.create_or_extend(
            conn=conn,
            xui=xui,
            user=user,
            plan=plan,
            promo=None,
            inbound_id=1,
            extend_sub_id=stale.id,
        )
    # Should be in the future (~now + 10d), not past + 10d (which is still past).
    now_iso = datetime.now(UTC).isoformat(sep=" ")
    assert new.expires_at > now_iso
    # Same row (extend, not create-new).
    assert new.id == stale.id


# ---------------------------------------------------------------------- #
# extend_sub_id semantics — multiple subscriptions per user
# ---------------------------------------------------------------------- #


async def test_create_or_extend_creates_new_when_active_sub_exists_no_extend_id(
    file_db, make_user, make_subscription, make_plan, monkeypatch
):
    """extend_sub_id=None → fresh add_client + new row, even if user has an active sub."""
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo
    from app.services import subscriptions as svc

    add_called: list[dict[str, object]] = []
    update_called: list[dict[str, object]] = []

    async def fake_add_client(client, **kwargs):
        add_called.append(dict(kwargs))
        return {"id": kwargs.get("client_uuid"), "email": kwargs.get("email")}

    async def fake_update_client(client, **kwargs):
        update_called.append(dict(kwargs))
        return {"id": kwargs.get("client_uuid")}

    monkeypatch.setattr(svc, "add_client", fake_add_client)
    monkeypatch.setattr(svc, "update_client", fake_update_client)

    xui = AsyncMock()

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=21)
        existing = await make_subscription(conn, user_id=user.id)
        plan = await make_plan(conn, days=30, price_stars=100)

        new = await svc.create_or_extend(
            conn=conn,
            xui=xui,
            user=user,
            plan=plan,
            promo=None,
            inbound_id=1,
            # extend_sub_id intentionally not passed → default None
        )

        rows = await subs_repo.list_for_user(conn, user.id)

    assert len(add_called) == 1, "add_client must be called for fresh provisioning"
    assert update_called == [], "update_client must NOT be called when extend_sub_id is None"
    assert new.id != existing.id, "must be a brand-new subscription row"
    assert {r.id for r in rows} == {existing.id, new.id}


async def test_create_or_extend_rejects_extend_sub_id_of_other_user(
    file_db, make_user, make_subscription
):
    """ValueError if the requested sub belongs to a different user."""
    from app.db.engine import get_conn

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value=None)

    async with get_conn() as conn:
        owner = await make_user(conn, tg_id=31)
        intruder = await make_user(conn, tg_id=32)
        sub = await make_subscription(conn, user_id=owner.id)

        with pytest.raises(ValueError):
            await subs_service.create_or_extend(
                conn=conn,
                xui=xui,
                user=intruder,
                plan=_plan(days=30),
                promo=None,
                inbound_id=1,
                extend_sub_id=sub.id,
            )


async def test_create_or_extend_rejects_extend_sub_id_for_revoked(
    file_db, make_user, make_subscription
):
    """ValueError if the requested sub is not status='active'."""
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value=None)

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=41)
        revoked = await make_subscription(conn, user_id=user.id)
        await subs_repo.set_status(conn, revoked.id, "revoked")

        with pytest.raises(ValueError):
            await subs_service.create_or_extend(
                conn=conn,
                xui=xui,
                user=user,
                plan=_plan(days=30),
                promo=None,
                inbound_id=1,
                extend_sub_id=revoked.id,
            )

        expired = await make_subscription(
            conn,
            user_id=user.id,
            xui_client_uuid="uuid-2",
            xui_client_email="tg_100_bbb",
            xui_sub_id="subid2",
        )
        await subs_repo.set_status(conn, expired.id, "expired")

        with pytest.raises(ValueError):
            await subs_service.create_or_extend(
                conn=conn,
                xui=xui,
                user=user,
                plan=_plan(days=30),
                promo=None,
                inbound_id=1,
                extend_sub_id=expired.id,
            )


async def test_activate_free_days_with_extend_sub_id(
    file_db, make_user, make_subscription
):
    """activate_free_days extends a specific sub when extend_sub_id is given."""
    from app.db.engine import get_conn

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value=None)

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=51)
        sub = await make_subscription(conn, user_id=user.id)
        old_expires = sub.expires_at

        new = await subs_service.activate_free_days(
            conn=conn,
            xui=xui,
            user=user,
            promo=_promo("free_days", 7),
            inbound_id=1,
            extend_sub_id=sub.id,
        )

    assert new.id == sub.id
    assert new.expires_at > old_expires


async def test_list_active_for_user_returns_multiple(
    file_db, make_user, make_subscription
):
    """list_active_for_user returns all active subs, sorted by expires_at DESC."""
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=61)
        soon = await make_subscription(
            conn,
            user_id=user.id,
            xui_client_uuid="uuid-soon",
            xui_client_email="tg_100_soon",
            xui_sub_id="subid-soon",
            expires_at=datetime.now(UTC) + timedelta(days=5),
        )
        later = await make_subscription(
            conn,
            user_id=user.id,
            xui_client_uuid="uuid-later",
            xui_client_email="tg_100_later",
            xui_sub_id="subid-later",
            expires_at=datetime.now(UTC) + timedelta(days=60),
        )

        rows = await subs_repo.list_active_for_user(conn, user.id)

    assert [r.id for r in rows] == [later.id, soon.id]
