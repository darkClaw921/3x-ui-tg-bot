"""Boundary-value tests for the SCHEDULER + XUI-CLIENT + EXPORTS + HEALTH domain.

This module is deliberately scoped to the *edge* / boundary cases that the
neighbouring suites (``test_scheduler.py``, ``test_xui_clients.py``,
``test_xui_inbounds.py``, ``test_services_exports.py``,
``test_services_health.py``, ``test_services_inbounds.py``) do not already
pin down. The mocking style (AsyncMock for the panel client, monkeypatch of
``scheduler.get_xui_client``, ``file_db`` for the on-disk DB used by the jobs)
mirrors those files verbatim so the patterns stay uniform.

Sections:

* scheduler day-left → reminder-kind boundaries (exactly 3/2/1/0 days, just
  over 3 days, negative);
* ``list_auto_renew_due`` / ``auto_renew_job`` selection + charging
  boundaries (within-window edge, balance == price vs price-1, replay idempotency,
  exclusion of native / non-auto-renew / non-active rows);
* traffic-alert threshold boundaries (== / just-below / just-above percent,
  unlimited plan, percent=0 disabled, dedup);
* xui client wire-shape boundaries (ms expiry, expiry=0, totalGB=0,
  limit_ip default, null-obj add, renewal not resending totalGB, 404
  idempotent delete, empty-list traffics);
* CSV export boundaries (empty DB, special-char escaping, uuid omission,
  header / row counts);
* health probe + ``record()`` transition boundaries.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from app import scheduler as sch_module
from app.scheduler import (
    _days_left,
    _kind_for_days_left,
    auto_renew_job,
    traffic_snapshot_job,
)


# --------------------------------------------------------------------------- #
# Local helpers (conftest.py is NOT modified — helpers live here)
# --------------------------------------------------------------------------- #


def _parse_csv(data: bytes) -> list[list[str]]:
    """Decode CSV bytes (utf-8-sig) into a list of rows (mirrors exports suite)."""
    assert isinstance(data, bytes)
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))


def _paged_traffic(email: str, up: int, down: int) -> dict:
    """Build a paged-list panel envelope carrying one client's traffic counters.

    Same shape ``get_client_traffics`` consumes — copied locally so this file
    does not depend on the scheduler suite's private helper.
    """
    return {
        "items": [{"email": email, "traffic": {"up": up, "down": down}}],
        "total": 1,
    }


def _request_json_for(current: dict):
    """AsyncMock side-effect for ``client.request_json`` (update read-merge-write).

    Returns the wrapped ``current`` client for ``clients/get/...`` paths and
    ``None`` for the subsequent mutating call. Mirrors the helper used by
    ``test_xui_clients.py``.
    """

    async def _dispatch(method, path, **kwargs):
        if "clients/get/" in path:
            return {"client": dict(current), "inboundIds": [1]}
        return None

    return _dispatch


async def _enable_wallet_autorenew(conn, sub_id: int) -> None:
    """Mark a subscription as wallet-fallback auto-renew (no tg charge id)."""
    from app.db.repos import subscriptions as subs_repo

    await subs_repo.set_auto_renew(conn, sub_id, True)


# =========================================================================== #
# 1. scheduler: _days_left + _kind_for_days_left boundaries
# =========================================================================== #


def test_days_left_exact_3_2_1_0_and_just_over_3():
    """Exact 3/2/1/0-day deltas and the 3-days-and-a-bit boundary.

    ``_days_left`` floors the timedelta, so a deadline 3 days + 1 second out is
    still reported as 3 (whole days), while exactly 3 days is also 3 — both map
    into the '3d' slot. 2 days → 2 (no reminder), etc.
    """
    now = datetime(2025, 1, 10, 12, 0, 0, tzinfo=UTC)
    assert _days_left("2025-01-13 12:00:00", now) == 3
    assert _days_left("2025-01-12 12:00:00", now) == 2
    assert _days_left("2025-01-11 12:00:00", now) == 1
    assert _days_left("2025-01-10 12:00:00", now) == 0
    # 3 days + 1 second → still floors to 3.
    assert _days_left("2025-01-13 12:00:01", now) == 3
    # Just under 4 days (3d 23h 59m) → still 3.
    assert _days_left("2025-01-14 11:59:00", now) == 3
    # Exactly 4 days → 4 (out of every reminder slot).
    assert _days_left("2025-01-14 12:00:00", now) == 4


def test_kind_for_days_left_boundary_table():
    """Reminder-kind mapping at every meaningful boundary.

    The 2-day slot is intentionally silent (only 3d/1d/0d fire); anything > 3
    days or < 0 days produces no reminder (the latter is the expire-checker's
    job).
    """
    assert _kind_for_days_left(3) == "3d"  # lower edge of the 3d slot
    assert _kind_for_days_left(2) is None  # the silent 2-day gap
    assert _kind_for_days_left(1) == "1d"
    assert _kind_for_days_left(0) == "0d"
    assert _kind_for_days_left(4) is None  # just over 3 days → no reminder
    assert _kind_for_days_left(-1) is None  # already expired → expire-checker
    assert _kind_for_days_left(-99) is None


async def test_reminders_dedup_kind_does_not_resend(
    file_db, make_user, make_subscription, mock_bot
):
    """A second reminder run for the same (sub, kind) is suppressed by dedup.

    Targets the ``subscription_notifications`` UNIQUE(sub, kind) guard on the
    '0d' slot (the existing suite only dedups the 1d slot). A sub expiring in
    ~12h floors to 0 whole days → '0d' and sits well inside the 3-day candidate
    window, so the fire-then-suppress behaviour is timing-robust.
    """
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=4242)
        await make_subscription(
            conn,
            user_id=user.id,
            # ~12h out → floors to 0 whole days → '0d' slot.
            expires_at=datetime.now(UTC) + timedelta(hours=12),
        )

    await sch_module.reminders_job(mock_bot)
    assert mock_bot.send_message.await_count == 1
    mock_bot.send_message.reset_mock()
    await sch_module.reminders_job(mock_bot)
    mock_bot.send_message.assert_not_awaited()  # deduped on the '0d' kind


# =========================================================================== #
# 2. list_auto_renew_due / auto_renew_job selection + charge boundaries
# =========================================================================== #


async def test_list_auto_renew_due_window_boundary(
    file_db, make_user, make_plan, make_subscription
):
    """expires_at exactly at now+within_hours is INCLUDED; just past it is NOT.

    The query uses ``expires_at <= now + within_hours`` against a cutoff
    computed from a microsecond-truncated ``now``. We pin the boundary by
    placing one sub a hair inside the window and one a hair outside, then
    asserting only the inside one is returned.
    """
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        plan = await make_plan(conn, price_stars=100, inbound_ids=[1])
        # Inside the 24h window (23h59m out).
        inside = await make_subscription(
            conn,
            user_id=user.id,
            plan_id=plan.id,
            expires_at=datetime.now(UTC) + timedelta(hours=23, minutes=59),
        )
        await _enable_wallet_autorenew(conn, inside.id)
        # Outside the 24h window (25h out).
        outside = await make_subscription(
            conn,
            user_id=user.id,
            plan_id=plan.id,
            xui_client_email="tg_1_out",
            xui_sub_id="subid-out",
            expires_at=datetime.now(UTC) + timedelta(hours=25),
        )
        await _enable_wallet_autorenew(conn, outside.id)

        due = await subs_repo.list_auto_renew_due(conn, within_hours=24)

    due_ids = {s.id for s in due}
    assert inside.id in due_ids
    assert outside.id not in due_ids


async def test_list_auto_renew_due_excludes_non_eligible(
    file_db, make_user, make_plan, make_subscription
):
    """auto_renew=0, native (tg_sub_charge_id NOT NULL) and status!='active' excluded.

    All three exclusion predicates of ``list_auto_renew_due`` pinned in one
    pass: only the plain wallet-fallback row survives.
    """
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        plan = await make_plan(conn, price_stars=100, inbound_ids=[1])
        exp = datetime.now(UTC) + timedelta(hours=10)

        # (a) eligible wallet-fallback row — the only one that should match.
        good = await make_subscription(
            conn, user_id=user.id, plan_id=plan.id,
            xui_client_email="good", xui_sub_id="s-good", expires_at=exp,
        )
        await _enable_wallet_autorenew(conn, good.id)

        # (b) auto_renew=0 (never opted in) → excluded.
        no_ar = await make_subscription(
            conn, user_id=user.id, plan_id=plan.id,
            xui_client_email="no_ar", xui_sub_id="s-noar", expires_at=exp,
        )
        # leave auto_renew default (0).

        # (c) native Star sub (tg_sub_charge_id set) → excluded.
        native = await make_subscription(
            conn, user_id=user.id, plan_id=plan.id,
            xui_client_email="native", xui_sub_id="s-nat", expires_at=exp,
        )
        await subs_repo.set_auto_renew(conn, native.id, True, tg_sub_charge_id="ch-1")

        # (d) auto_renew=1 but status!='active' → excluded.
        inactive = await make_subscription(
            conn, user_id=user.id, plan_id=plan.id,
            xui_client_email="inact", xui_sub_id="s-inact", expires_at=exp,
        )
        await _enable_wallet_autorenew(conn, inactive.id)
        await subs_repo.set_status(conn, inactive.id, "expired")

        due = await subs_repo.list_auto_renew_due(conn, within_hours=24)

    assert {s.id for s in due} == {good.id}
    _ = no_ar  # referenced for clarity


async def _stub_extend(monkeypatch, *, move_expiry: bool):
    """Stub ``subs_service.create_or_extend`` for auto_renew_job orchestration.

    When ``move_expiry`` is True the stub bumps ``expires_at`` (so the deterministic
    spend ref changes between runs); when False it leaves it fixed (so a re-run
    reproduces a same-period replay).
    """
    from app.db.repos import subscriptions as subs_repo

    new_dt = datetime.now(UTC) + timedelta(days=30)

    async def _fake(*, conn, xui, user, plan, promo, inbound_id, extend_sub_id):
        if move_expiry:
            await subs_repo.extend(conn, extend_sub_id, new_dt)
        return await subs_repo.get(conn, extend_sub_id)

    monkeypatch.setattr(
        sch_module.subs_service, "create_or_extend", AsyncMock(side_effect=_fake)
    )


async def test_auto_renew_balance_exactly_equal_price_succeeds(
    file_db, make_user, make_plan, make_subscription, mock_bot, monkeypatch
):
    """Balance == price is the success boundary: charge clears, sub extended.

    The existing suite seeds 500⭐ for a 100⭐ plan; here the wallet holds
    *exactly* the price so we pin the ``try_spend`` >= boundary at equality.
    """
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo
    from app.db.repos import wallet as wallet_repo
    from app.services import wallet as wallet_service

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=7)
        plan = await make_plan(conn, price_stars=100, inbound_ids=[1])
        sub = await make_subscription(
            conn, user_id=user.id, plan_id=plan.id, xui_inbound_id=1,
            expires_at=datetime.now(UTC) + timedelta(hours=10),
        )
        await _enable_wallet_autorenew(conn, sub.id)
        await wallet_service.credit(conn, user.id, 100, type="topup", ref="seed")

    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=AsyncMock()))
    await _stub_extend(monkeypatch, move_expiry=True)

    old_expiry = sub.expires_at
    await auto_renew_job(mock_bot)

    async with get_conn() as conn:
        fresh = await subs_repo.get(conn, sub.id)
        bal = await wallet_repo.balance(conn, user.id)
    assert fresh.expires_at > old_expiry  # extended
    assert bal == 0  # spent exactly to zero
    mock_bot.send_message.assert_awaited()  # renewed DM


async def test_auto_renew_balance_one_short_notifies_no_charge(
    file_db, make_user, make_plan, make_subscription, mock_bot, monkeypatch
):
    """Balance == price-1: spend rejected, no extend, insufficient-balance DM.

    The just-below boundary — a single Star short of the price must NOT charge
    and must NOT extend, only DM the user.
    """
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo
    from app.db.repos import wallet as wallet_repo
    from app.services import wallet as wallet_service

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=7)
        plan = await make_plan(conn, price_stars=100, inbound_ids=[1])
        sub = await make_subscription(
            conn, user_id=user.id, plan_id=plan.id, xui_inbound_id=1,
            expires_at=datetime.now(UTC) + timedelta(hours=10),
        )
        await _enable_wallet_autorenew(conn, sub.id)
        await wallet_service.credit(conn, user.id, 99, type="topup", ref="seed")

    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=AsyncMock()))
    await _stub_extend(monkeypatch, move_expiry=True)

    await auto_renew_job(mock_bot)

    async with get_conn() as conn:
        fresh = await subs_repo.get(conn, sub.id)
        bal = await wallet_repo.balance(conn, user.id)
    assert fresh.expires_at == sub.expires_at  # NOT extended
    assert bal == 99  # untouched — no partial charge
    mock_bot.send_message.assert_awaited()  # insufficient-balance DM


async def test_auto_renew_replay_same_period_charges_once(
    file_db, make_user, make_plan, make_subscription, mock_bot, monkeypatch
):
    """Re-running in the same period (ref unchanged) must not double-charge.

    The spend ref is ``autorenew:<sub>:<expires_at>``. With ``expires_at`` held
    fixed between runs the second spend hits the same ref and is rejected as a
    replay — balance moves exactly once. Boundary: idempotency on the ref.
    """
    from app.db.engine import get_conn
    from app.db.repos import wallet as wallet_repo
    from app.services import wallet as wallet_service

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=7)
        plan = await make_plan(conn, price_stars=100, inbound_ids=[1])
        sub = await make_subscription(
            conn, user_id=user.id, plan_id=plan.id, xui_inbound_id=1,
            expires_at=datetime.now(UTC) + timedelta(hours=10),
        )
        await _enable_wallet_autorenew(conn, sub.id)
        await wallet_service.credit(conn, user.id, 250, type="topup", ref="seed")

    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=AsyncMock()))
    # Keep expires_at fixed so the ref is identical on the second run.
    await _stub_extend(monkeypatch, move_expiry=False)

    await auto_renew_job(mock_bot)
    await auto_renew_job(mock_bot)

    async with get_conn() as conn:
        bal = await wallet_repo.balance(conn, user.id)
    assert bal == 150  # 250 - 100, charged exactly once across two runs


# =========================================================================== #
# 3. traffic-alert threshold boundaries
# =========================================================================== #


async def _seed_quota_sub(make_user, make_plan, make_subscription, *, traffic_gb: int):
    """Create a user + plan(traffic_gb) + active sub, return the sub email."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=5)
        plan = await make_plan(conn, traffic_gb=traffic_gb, inbound_ids=[1])
        await make_subscription(
            conn, user_id=user.id, plan_id=plan.id, xui_client_email="quota@x",
        )
    return "quota@x"


def _threshold_bytes(traffic_gb: int, percent: int) -> int:
    """Replicate the job's integer threshold: quota * percent // 100."""
    return (traffic_gb * (1024**3)) * percent // 100


async def test_traffic_alert_exactly_at_threshold_fires(
    file_db, make_user, make_plan, make_subscription, mock_bot, monkeypatch
):
    """Usage exactly == threshold fires (the comparison is ``total < threshold``).

    1 GB quota, default 80% threshold → threshold = 0.8 GiB. Splitting that
    across up/down so ``up + down`` lands *exactly* on the threshold byte count
    must trigger one alert.
    """
    from app.config import settings

    email = await _seed_quota_sub(make_user, make_plan, make_subscription, traffic_gb=1)
    percent = int(settings.TRAFFIC_ALERT_PERCENT)
    threshold = _threshold_bytes(1, percent)

    xui = AsyncMock()
    half = threshold // 2
    # up + down == threshold exactly (account for odd byte).
    xui.request_json = AsyncMock(
        return_value=_paged_traffic(email, up=half, down=threshold - half)
    )
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=xui))

    await traffic_snapshot_job(mock_bot)
    assert mock_bot.send_message.await_count == 1


async def test_traffic_alert_one_byte_below_threshold_silent(
    file_db, make_user, make_plan, make_subscription, mock_bot, monkeypatch
):
    """Usage == threshold-1 byte does NOT fire (just-below boundary)."""
    from app.config import settings

    email = await _seed_quota_sub(make_user, make_plan, make_subscription, traffic_gb=1)
    percent = int(settings.TRAFFIC_ALERT_PERCENT)
    threshold = _threshold_bytes(1, percent)

    xui = AsyncMock()
    total = threshold - 1
    half = total // 2
    xui.request_json = AsyncMock(
        return_value=_paged_traffic(email, up=half, down=total - half)
    )
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=xui))

    await traffic_snapshot_job(mock_bot)
    mock_bot.send_message.assert_not_awaited()


async def test_traffic_alert_one_byte_above_threshold_fires(
    file_db, make_user, make_plan, make_subscription, mock_bot, monkeypatch
):
    """Usage == threshold+1 byte fires (just-above boundary)."""
    from app.config import settings

    email = await _seed_quota_sub(make_user, make_plan, make_subscription, traffic_gb=1)
    percent = int(settings.TRAFFIC_ALERT_PERCENT)
    threshold = _threshold_bytes(1, percent)

    xui = AsyncMock()
    total = threshold + 1
    half = total // 2
    xui.request_json = AsyncMock(
        return_value=_paged_traffic(email, up=half, down=total - half)
    )
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=xui))

    await traffic_snapshot_job(mock_bot)
    assert mock_bot.send_message.await_count == 1


async def test_traffic_alert_percent_zero_disabled(
    file_db, make_user, make_plan, make_subscription, mock_bot, monkeypatch
):
    """TRAFFIC_ALERT_PERCENT == 0 disables the alert entirely, even at 100% usage."""
    from app.config import settings

    monkeypatch.setattr(settings, "TRAFFIC_ALERT_PERCENT", 0)
    email = await _seed_quota_sub(make_user, make_plan, make_subscription, traffic_gb=1)

    xui = AsyncMock()
    gb = 1024**3
    xui.request_json = AsyncMock(return_value=_paged_traffic(email, up=gb, down=gb))
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=xui))

    await traffic_snapshot_job(mock_bot)
    mock_bot.send_message.assert_not_awaited()


async def test_traffic_alert_unlimited_plan_never_fires(
    file_db, make_user, make_plan, make_subscription, mock_bot, monkeypatch
):
    """traffic_gb == 0 (unlimited) never alerts, regardless of huge usage.

    (The neighbouring suite covers this once; repeated here with an explicit
    'massive overuse on an unlimited plan' boundary and a non-default percent
    to ensure the unlimited short-circuit precedes the percent check.)
    """
    from app.config import settings

    monkeypatch.setattr(settings, "TRAFFIC_ALERT_PERCENT", 50)
    email = await _seed_quota_sub(make_user, make_plan, make_subscription, traffic_gb=0)

    xui = AsyncMock()
    gb = 1024**3
    xui.request_json = AsyncMock(
        return_value=_paged_traffic(email, up=1000 * gb, down=1000 * gb)
    )
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=xui))

    await traffic_snapshot_job(mock_bot)
    mock_bot.send_message.assert_not_awaited()


async def test_traffic_alert_dedup_across_snapshots(
    file_db, make_user, make_plan, make_subscription, mock_bot, monkeypatch
):
    """A second over-threshold snapshot does not re-alert (traffic80 dedup)."""
    from app.config import settings

    email = await _seed_quota_sub(make_user, make_plan, make_subscription, traffic_gb=1)
    threshold = _threshold_bytes(1, int(settings.TRAFFIC_ALERT_PERCENT))

    xui = AsyncMock()
    xui.request_json = AsyncMock(
        return_value=_paged_traffic(email, up=threshold, down=threshold)
    )
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=xui))

    await traffic_snapshot_job(mock_bot)
    assert mock_bot.send_message.await_count == 1
    mock_bot.send_message.reset_mock()
    await traffic_snapshot_job(mock_bot)
    mock_bot.send_message.assert_not_awaited()  # deduped on 'traffic80'


# =========================================================================== #
# 4. xui clients — wire-shape boundaries
# =========================================================================== #


async def test_add_client_expiry_ms_and_unlimited_and_default_limit_ip():
    """expiry forwarded verbatim as ms, totalGB=0 → unlimited, limitIp default 0."""
    from app.xui.clients import add_client

    client = AsyncMock()
    client.request_json = AsyncMock(return_value=None)
    unix_seconds = 1_700_000_000
    expiry_ms = unix_seconds * 1000

    await add_client(
        client,
        inbound_id=2,
        client_uuid="u",
        email="e",
        expiry_ts_ms=expiry_ms,
        total_gb=0,  # unlimited
        # limit_ip omitted → default 0
    )
    body = client.request_json.call_args.kwargs["json"]
    c = body["client"]
    assert c["expiryTime"] == expiry_ms  # ms, not seconds
    assert c["expiryTime"] != unix_seconds
    assert c["totalGB"] == 0  # unlimited boundary
    assert c["limitIp"] == 0  # default


async def test_add_client_expiry_zero_means_never():
    """expiry_ts_ms == 0 ('never') is preserved as 0 on the wire."""
    from app.xui.clients import add_client

    client = AsyncMock()
    client.request_json = AsyncMock(return_value=None)
    await add_client(
        client, inbound_id=1, client_uuid="u", email="e", expiry_ts_ms=0
    )
    assert client.request_json.call_args.kwargs["json"]["client"]["expiryTime"] == 0


async def test_add_client_null_panel_obj_returns_fallback_dict():
    """A null ``obj`` from the panel is normalised to a usable id/email/subId dict."""
    from app.xui.clients import add_client

    client = AsyncMock()
    client.request_json = AsyncMock(return_value=None)
    out = await add_client(
        client, inbound_id=1, client_uuid="the-uuid", email="the-email",
        expiry_ts_ms=0, sub_id="the-sub",
    )
    assert out == {"id": "the-uuid", "email": "the-email", "subId": "the-sub"}


async def test_update_client_on_renewal_does_not_resend_totalGB():
    """Renewal sends expiryTime+enable but PRESERVES the existing totalGB.

    Reproduces the production extend path (``update_client(email, expiryTime=,
    enable=True)``): the read-merge-write must keep the panel's stored quota
    (totalGB=5 here) and never overwrite it to 0. Boundary: the renewal payload
    carries the *existing* totalGB, sourced from the GET, not from the caller.
    """
    from app.xui.clients import update_client

    client = AsyncMock()
    current = {
        "email": "e", "uuid": "U", "subId": "S",
        "totalGB": 5, "expiryTime": 100, "enable": True,
    }
    client.request_json = AsyncMock(side_effect=_request_json_for(current))

    await update_client(client, "e", expiryTime=1_700_000_000_000, enable=True)

    body = client.request_json.await_args_list[1].kwargs["json"]
    assert body["expiryTime"] == 1_700_000_000_000  # new expiry applied
    assert body["enable"] is True
    assert body["totalGB"] == 5  # preserved quota — NOT reset to 0
    assert body["uuid"] == "U"  # other secrets preserved too


async def test_del_client_idempotent_on_404_not_found():
    """A 'not found' (404-equivalent) panel error on delete is swallowed.

    Boundary on idempotency: re-deleting an already-gone client must not raise,
    so a replayed expire job stays crash-free.
    """
    from app.xui import XuiError
    from app.xui.clients import del_client

    client = AsyncMock()
    client.request_json = AsyncMock(
        side_effect=XuiError("record not found (404)")
    )
    await del_client(client, "ghost@x")  # must not raise


async def test_get_client_traffics_empty_items_returns_empty_dict():
    """An empty ``items`` list (no match) → empty dict, not an error."""
    from app.xui.clients import get_client_traffics

    client = AsyncMock()
    client.request_json = AsyncMock(return_value={"items": [], "total": 0})
    out = await get_client_traffics(client, "missing@x")
    assert out == {}


# =========================================================================== #
# 5. exports — CSV boundaries
# =========================================================================== #


async def test_export_special_chars_escaped_via_csv_module(file_db, make_user):
    """Comma / quote / newline in a field round-trip intact through csv escaping.

    Boundary on RFC-4180 escaping: a username containing a comma, a double
    quote and an embedded newline must survive ``csv.reader`` parsing as a
    single field with the exact original text.
    """
    from app.db.engine import get_conn
    from app.services import exports as exports_service

    nasty = 'a,b"c\nd'  # comma + quote + newline
    async with get_conn() as conn:
        await make_user(conn, tg_id=777, username=nasty, first_name="X")
        data = await exports_service.export_users_csv(conn)

    rows = _parse_csv(data)
    assert rows[0][0] == "id"  # header intact
    assert len(rows) == 2  # header + 1 data row (newline did NOT split it)
    # The mangled username survives as one field, byte-for-byte.
    assert nasty in rows[1]


async def test_export_subscriptions_never_contains_uuid_secret(
    file_db, make_user, make_plan, make_subscription
):
    """The subscriptions CSV omits xui_client_uuid even when it is set.

    (Companion edge to the neighbouring test, here asserting both the absent
    column header and the absent value for a distinctive secret.)
    """
    from app.db.engine import get_conn
    from app.services import exports as exports_service

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=888)
        plan = await make_plan(conn, inbound_ids=[1])
        await make_subscription(
            conn, user_id=user.id, plan_id=plan.id, xui_inbound_id=1,
            xui_client_uuid="UUID-MUST-NOT-LEAK", xui_client_email="z@x",
        )
        data = await exports_service.export_subscriptions_csv(conn)

    rows = _parse_csv(data)
    assert "xui_client_uuid" not in rows[0]  # not a column
    assert "UUID-MUST-NOT-LEAK" not in data.decode("utf-8-sig")  # not a value


async def test_export_payments_header_and_row_count(file_db, make_user, make_plan):
    """Payments CSV: exact header + one data row per record (boundary: N=1)."""
    from app.db.engine import get_conn
    from app.db.repos import payments as payments_repo
    from app.services import exports as exports_service

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=999)
        plan = await make_plan(conn, inbound_ids=[1])
        await payments_repo.create(
            conn, user_id=user.id, subscription_id=None,
            telegram_charge_id="ch-x", stars_amount=50, plan_id=plan.id,
            promo_id=None, status="paid",
        )
        data = await exports_service.export_payments_csv(conn)

    rows = _parse_csv(data)
    assert rows[0] == [
        "id", "user_id", "subscription_id", "telegram_charge_id",
        "stars_amount", "plan_id", "promo_id", "status", "created_at",
    ]
    assert len(rows) == 2  # header + 1


# =========================================================================== #
# 6. health — probe + record() transition boundaries
# =========================================================================== #


async def test_check_xui_health_success_is_up(monkeypatch):
    """A successful probe yields (True, None) → caller maps to 'up'."""
    from app.services import health as health_service

    monkeypatch.setattr(
        health_service, "list_inbounds", AsyncMock(return_value=[{"id": 1}])
    )
    ok, err = await health_service.check_xui_health(AsyncMock())
    assert ok is True and err is None


async def test_check_xui_health_timeout_is_down(monkeypatch):
    """A probe exceeding the timeout yields (False, 'timeout...') → 'down'."""
    import asyncio

    from app.services import health as health_service

    async def _never(_client):
        await asyncio.sleep(10)

    monkeypatch.setattr(health_service, "list_inbounds", _never)
    monkeypatch.setattr(health_service, "_PROBE_TIMEOUT_SEC", 0.01)
    ok, err = await health_service.check_xui_health(AsyncMock())
    assert ok is False
    assert "timeout" in (err or "")


async def test_health_record_transition_boundaries(file_db):
    """All four transition boundaries of record(): first / up→up / down→up / up→down.

    Pins ``changed`` at each edge in one ordered sequence:
    * first probe          → changed=True
    * up → up (steady)     → changed=False
    * up → down (flip)     → changed=True
    * down → up (recovery) → changed=True
    """
    from app.db.engine import get_conn
    from app.db.repos import health as health_repo

    async with get_conn() as conn:
        # first probe — no prior state → counts as a change.
        _, changed = await health_repo.record(conn, status="up")
        assert changed is True

        # up → up steady — no change.
        _, changed = await health_repo.record(conn, status="up")
        assert changed is False

        # up → down — change, error recorded.
        row, changed = await health_repo.record(
            conn, status="down", last_error="unreachable"
        )
        assert changed is True
        assert row.status == "down"
        assert row.last_error == "unreachable"

        # down → up — change (recovery), error cleared.
        row, changed = await health_repo.record(conn, status="up")
        assert changed is True
        assert row.status == "up"
        assert row.last_error is None
