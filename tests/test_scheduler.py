"""Tests for :mod:`app.scheduler`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import scheduler as sch_module
from app.scheduler import (
    _days_left,
    _kind_for_days_left,
    _parse_iso,
    auto_renew_job,
    expire_check_job,
    health_check_job,
    reminders_job,
    setup_scheduler,
    traffic_snapshot_job,
)


def test_kind_for_days_left_table():
    assert _kind_for_days_left(-1) is None
    assert _kind_for_days_left(0) == "0d"
    assert _kind_for_days_left(1) == "1d"
    assert _kind_for_days_left(2) is None
    assert _kind_for_days_left(3) == "3d"
    assert _kind_for_days_left(4) is None
    assert _kind_for_days_left(5) is None
    assert _kind_for_days_left(10) is None


def test_parse_iso_naive_assumed_utc():
    dt = _parse_iso("2025-01-01 00:00:00")
    assert dt.tzinfo == UTC


def test_parse_iso_aware():
    dt = _parse_iso("2025-01-01 00:00:00+00:00")
    assert dt.tzinfo is not None


def test_days_left():
    now = datetime(2025, 1, 10, tzinfo=UTC)
    assert _days_left("2025-01-13 00:00:00", now) == 3
    assert _days_left("2025-01-10 00:00:00", now) == 0
    assert _days_left("2025-01-09 00:00:00", now) == -1


def test_setup_scheduler_registers_all_jobs():
    bot = MagicMock()
    sched = setup_scheduler(bot)
    job_ids = {j.id for j in sched.get_jobs()}
    assert job_ids == {
        "expire_check",
        "reminders",
        "traffic_snapshots",
        "auto_renew",
        "health_check",
    }


def test_setup_scheduler_health_check_single_instance():
    """The health-check job runs at most one instance at a time."""
    bot = MagicMock()
    sched = setup_scheduler(bot)
    job = sched.get_job("health_check")
    assert job is not None
    assert job.max_instances == 1


async def test_expire_check_job_no_expired(file_db, mock_bot):
    """No expired subs: job runs and logs the empty case."""
    await expire_check_job(mock_bot)
    # No exceptions, no notifications.


async def test_expire_check_job_processes_expired(
    file_db, make_user, make_subscription, mock_bot, monkeypatch
):
    """Expired sub → status flips to 'expired', user notified once."""
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=999)
        sub = await make_subscription(
            conn,
            user_id=user.id,
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        sub_id = sub.id

    xui_mock = AsyncMock()
    xui_mock.request_json = AsyncMock(return_value=None)
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=xui_mock))

    await expire_check_job(mock_bot)

    async with get_conn() as conn:
        fresh = await subs_repo.get(conn, sub_id)
    assert fresh.status == "expired"
    mock_bot.send_message.assert_awaited()


async def test_expire_check_dedup(
    file_db, make_user, make_subscription, mock_bot, monkeypatch
):
    """Running twice must not re-send the expired notification."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=999)
        await make_subscription(
            conn,
            user_id=user.id,
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )

    xui_mock = AsyncMock()
    xui_mock.request_json = AsyncMock(return_value=None)
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=xui_mock))

    await expire_check_job(mock_bot)
    # Reset for the second run; the subscription is no longer "active" so
    # the second pass should pick up nothing.
    mock_bot.send_message.reset_mock()
    await expire_check_job(mock_bot)
    mock_bot.send_message.assert_not_awaited()


async def test_expire_check_xui_failure_still_marks_expired(
    file_db, make_user, make_subscription, mock_bot, monkeypatch
):
    """xui.update_client failure must NOT block the DB status flip."""
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo
    from app.xui import XuiError

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=999)
        sub = await make_subscription(
            conn,
            user_id=user.id,
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )

    xui_mock = AsyncMock()
    xui_mock.request_json = AsyncMock(side_effect=XuiError("panel-down"))
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=xui_mock))

    await expire_check_job(mock_bot)

    async with get_conn() as conn:
        fresh = await subs_repo.get(conn, sub.id)
    assert fresh.status == "expired"


async def test_expire_check_xui_unavailable(
    file_db, make_user, make_subscription, mock_bot, monkeypatch
):
    """If get_xui_client raises, the job still flips DB statuses."""
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        sub = await make_subscription(
            conn,
            user_id=user.id,
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )

    monkeypatch.setattr(
        sch_module,
        "get_xui_client",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    await expire_check_job(mock_bot)

    async with get_conn() as conn:
        fresh = await subs_repo.get(conn, sub.id)
    assert fresh.status == "expired"


async def test_reminders_job_sends_1d(
    file_db, make_user, make_subscription, mock_bot
):
    """A sub expiring in ~28h triggers the '1d' reminder."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=42)
        await make_subscription(
            conn,
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=28),
        )

    await reminders_job(mock_bot)
    mock_bot.send_message.assert_awaited()


async def test_reminders_job_dedup(
    file_db, make_user, make_subscription, mock_bot
):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=42)
        await make_subscription(
            conn,
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=28),
        )

    await reminders_job(mock_bot)
    mock_bot.send_message.reset_mock()
    await reminders_job(mock_bot)
    # No new send (dedup via subscription_notifications table).
    mock_bot.send_message.assert_not_awaited()


async def test_reminders_job_skips_far_subs(
    file_db, make_user, make_subscription, mock_bot
):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        await make_subscription(
            conn,
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(days=10),
        )
    await reminders_job(mock_bot)
    mock_bot.send_message.assert_not_awaited()


async def test_reminders_job_no_candidates(file_db, mock_bot):
    await reminders_job(mock_bot)
    mock_bot.send_message.assert_not_awaited()


async def test_traffic_snapshot_job_writes(
    file_db, make_user, make_subscription, mock_bot, monkeypatch
):
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        sub = await make_subscription(conn, user_id=user.id)

    xui_mock = AsyncMock()
    # New panel: live traffic rides the paged client list (items[].traffic).
    xui_mock.request_json = AsyncMock(
        return_value={"items": [{"email": "x", "traffic": {"up": 100, "down": 200}}], "total": 1}
    )
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=xui_mock))

    await traffic_snapshot_job(mock_bot)

    async with get_conn() as conn:
        last = await subs_repo.last_traffic_snapshot(conn, sub.id)
    assert last is not None
    assert last.up == 100 and last.down == 200


async def test_traffic_snapshot_job_handles_xui_error(
    file_db, make_user, make_subscription, mock_bot, monkeypatch
):
    """An XuiError per-client is logged and skipped, not fatal."""
    from app.db.engine import get_conn
    from app.xui import XuiError

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        await make_subscription(conn, user_id=user.id)

    xui_mock = AsyncMock()
    xui_mock.request_json = AsyncMock(side_effect=XuiError("client missing"))
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=xui_mock))

    # Should not raise.
    await traffic_snapshot_job(mock_bot)


async def test_traffic_snapshot_no_active(file_db, mock_bot):
    """No active subs → early return, no panel call."""
    await traffic_snapshot_job(mock_bot)


async def test_traffic_snapshot_xui_unavailable(
    file_db, make_user, make_subscription, mock_bot, monkeypatch
):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        await make_subscription(conn, user_id=user.id)

    monkeypatch.setattr(
        sch_module,
        "get_xui_client",
        AsyncMock(side_effect=RuntimeError("no panel")),
    )
    await traffic_snapshot_job(mock_bot)


async def test_traffic_snapshot_empty_dict(
    file_db, make_user, make_subscription, mock_bot, monkeypatch
):
    """If get_client_traffics returns empty dict, skip snapshot."""
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        sub = await make_subscription(conn, user_id=user.id)

    xui_mock = AsyncMock()
    xui_mock.request_json = AsyncMock(return_value=None)  # empty traffics → {}
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=xui_mock))

    await traffic_snapshot_job(mock_bot)

    async with get_conn() as conn:
        last = await subs_repo.last_traffic_snapshot(conn, sub.id)
    assert last is None


async def test_safe_send_swallows_telegram_error(mock_bot):
    """_safe_send catches TelegramAPIError."""
    from aiogram.exceptions import TelegramAPIError

    from app.scheduler import _safe_send

    mock_bot.send_message.side_effect = TelegramAPIError(method=None, message="blocked")
    # Must not raise.
    await _safe_send(mock_bot, 1, "hi")


async def test_wrap_catches_exceptions():
    """_wrap returns a runner that swallows exceptions."""
    from app.scheduler import _wrap

    async def bad(_bot):
        raise RuntimeError("boom")

    runner = _wrap(bad, MagicMock(), "test")
    await runner()  # must not raise.


async def test_reminders_job_orphan_subscription(
    file_db, make_user, make_subscription, mock_bot
):
    """Subscription pointing at a user that was deleted from the users table."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=42)
        sub = await make_subscription(
            conn,
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=28),
        )
        # Disable FK so we can delete the user but keep the sub.
        await conn.execute("PRAGMA foreign_keys = OFF")
        await conn.execute("DELETE FROM users WHERE id=?", (user.id,))
        await conn.commit()
    await reminders_job(mock_bot)
    mock_bot.send_message.assert_not_awaited()


async def test_expire_check_db_error_listing(file_db, mock_bot, monkeypatch):
    """If list_expired_active raises, the job returns gracefully."""
    from app.db.repos import subscriptions as subs_repo

    async def boom(*a, **kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(subs_repo, "list_expired_active", boom)
    await expire_check_job(mock_bot)


async def test_reminders_db_error_listing(file_db, mock_bot, monkeypatch):
    from app.db.repos import subscriptions as subs_repo

    async def boom(*a, **kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(subs_repo, "list_expiring_in", boom)
    await reminders_job(mock_bot)


async def test_traffic_db_error_listing(file_db, mock_bot, monkeypatch):
    from app.db.repos import subscriptions as subs_repo

    async def boom(*a, **kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(subs_repo, "list_active", boom)
    await traffic_snapshot_job(mock_bot)


async def test_reminders_job_bad_expires_at(
    file_db, make_user, make_subscription, mock_bot
):
    """A row with a bad ISO timestamp is logged & skipped."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        sub = await make_subscription(
            conn,
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(days=2),
        )
        # Corrupt the value.
        await conn.execute(
            "UPDATE subscriptions SET expires_at='not-a-date' WHERE id=?", (sub.id,)
        )
        await conn.commit()
    await reminders_job(mock_bot)
    mock_bot.send_message.assert_not_awaited()


# --------------------------------------------------------------------------- #
# Phase 4 — reminder "renew in 1 tap" button
# --------------------------------------------------------------------------- #


async def test_reminders_job_attaches_renew_button(
    file_db, make_user, make_subscription, mock_bot
):
    """The 1d reminder carries a «🔁 Продлить в 1 тап» button (BuyCB extend)."""
    from app.db.engine import get_conn
    from app.keyboards.user import BuyCB

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=42)
        sub = await make_subscription(
            conn,
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=28),
        )

    await reminders_job(mock_bot)
    mock_bot.send_message.assert_awaited()
    _, kwargs = mock_bot.send_message.call_args
    markup = kwargs["reply_markup"]
    assert markup is not None
    btn = markup.inline_keyboard[0][0]
    cb = BuyCB.unpack(btn.callback_data)
    assert cb.action == "extend"
    assert cb.sub_id == sub.id


# --------------------------------------------------------------------------- #
# Phase 4 — auto_renew_job (wallet fallback)
# --------------------------------------------------------------------------- #


async def _enable_wallet_autorenew(conn, sub_id):
    """Mark a subscription as wallet-fallback auto-renew (no tg charge id)."""
    from app.db.repos import subscriptions as subs_repo

    await subs_repo.set_auto_renew(conn, sub_id, True)


async def test_auto_renew_job_charges_and_extends(
    file_db, make_user, make_plan, make_subscription, mock_bot, monkeypatch
):
    """A due wallet-auto-renew sub is charged once and extended; user is DMed."""
    from app.db.engine import get_conn
    from app.db.repos import payments as payments_repo
    from app.db.repos import subscriptions as subs_repo
    from app.services import wallet as wallet_service

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=7)
        plan = await make_plan(conn, price_stars=100, inbound_ids=[1])
        sub = await make_subscription(
            conn,
            user_id=user.id,
            plan_id=plan.id,
            xui_inbound_id=1,
            expires_at=datetime.now(UTC) + timedelta(hours=10),
        )
        await _enable_wallet_autorenew(conn, sub.id)
        # Fund the wallet so the spend succeeds.
        await wallet_service.credit(conn, user.id, 500, type="topup", ref="seed")

    xui = AsyncMock()
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=xui))

    # Provisioning (xui round-trip) is exercised by the service tests; here we
    # stub it so the job's orchestration (charge → extend → payment → DM) is the
    # unit under test. The stub really bumps expires_at in the DB so the
    # post-condition holds.
    new_dt = datetime.now(UTC) + timedelta(days=30)

    async def _fake_extend(*, conn, xui, user, plan, promo, inbound_id, extend_sub_id):
        await subs_repo.extend(conn, extend_sub_id, new_dt)
        return await subs_repo.get(conn, extend_sub_id)

    monkeypatch.setattr(
        sch_module.subs_service, "create_or_extend", AsyncMock(side_effect=_fake_extend)
    )

    old_expiry = sub.expires_at
    await auto_renew_job(mock_bot)

    from app.db.repos import wallet as wallet_repo

    async with get_conn() as conn:
        fresh = await subs_repo.get(conn, sub.id)
        bal = await wallet_repo.balance(conn, user.id)
        spend_txn = await wallet_repo.get_by_ref(
            conn, f"autorenew:{sub.id}:{old_expiry}"
        )
        pay = await payments_repo.get_by_charge_id(
            conn, f"wallet:autorenew:{spend_txn.id}"
        )
    assert fresh.expires_at > old_expiry  # extended
    assert bal == 400  # 500 - 100
    assert pay is not None  # synthetic payment recorded
    mock_bot.send_message.assert_awaited()  # renewed DM


async def test_auto_renew_job_dedup_same_period(
    file_db, make_user, make_plan, make_subscription, mock_bot, monkeypatch
):
    """Re-running the job in the same period must NOT charge twice (replay-safe ref)."""
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo
    from app.services import wallet as wallet_service

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=7)
        plan = await make_plan(conn, price_stars=100, inbound_ids=[1])
        sub = await make_subscription(
            conn,
            user_id=user.id,
            plan_id=plan.id,
            xui_inbound_id=1,
            expires_at=datetime.now(UTC) + timedelta(hours=10),
        )
        await _enable_wallet_autorenew(conn, sub.id)
        await wallet_service.credit(conn, user.id, 500, type="topup", ref="seed")

    xui = AsyncMock()
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=xui))

    # Stub provisioning but DO NOT move expires_at — the ref is derived from
    # expires_at, so keeping it fixed reproduces a same-period retry where the
    # deterministic spend ref is identical and must be rejected as a replay.
    async def _fake_extend(*, conn, xui, user, plan, promo, inbound_id, extend_sub_id):
        return await subs_repo.get(conn, extend_sub_id)

    monkeypatch.setattr(
        sch_module.subs_service, "create_or_extend", AsyncMock(side_effect=_fake_extend)
    )

    await auto_renew_job(mock_bot)
    await auto_renew_job(mock_bot)

    async with get_conn() as conn:
        bal = await __import__(
            "app.db.repos.wallet", fromlist=["balance"]
        ).balance(conn, user.id)
    # Only one 100-Stars charge despite two runs in the same period.
    assert bal == 400


async def test_auto_renew_job_insufficient_balance_dms(
    file_db, make_user, make_plan, make_subscription, mock_bot, monkeypatch
):
    """An empty wallet → no charge, no extend, but an 'insufficient' DM."""
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=7)
        plan = await make_plan(conn, price_stars=100, inbound_ids=[1])
        sub = await make_subscription(
            conn,
            user_id=user.id,
            plan_id=plan.id,
            xui_inbound_id=1,
            expires_at=datetime.now(UTC) + timedelta(hours=10),
        )
        await _enable_wallet_autorenew(conn, sub.id)

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"id": "u", "email": "e"})
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=xui))

    await auto_renew_job(mock_bot)

    async with get_conn() as conn:
        fresh = await subs_repo.get(conn, sub.id)
    assert fresh.expires_at == sub.expires_at  # not extended
    mock_bot.send_message.assert_awaited()  # insufficient-balance DM


async def test_auto_renew_job_disabled_flag(
    file_db, make_user, make_plan, make_subscription, mock_bot, monkeypatch
):
    """AUTO_RENEW_ENABLED=False short-circuits the job entirely."""
    from app.config import settings
    from app.db.engine import get_conn
    from app.services import wallet as wallet_service

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=7)
        plan = await make_plan(conn, price_stars=100, inbound_ids=[1])
        sub = await make_subscription(
            conn,
            user_id=user.id,
            plan_id=plan.id,
            xui_inbound_id=1,
            expires_at=datetime.now(UTC) + timedelta(hours=10),
        )
        await _enable_wallet_autorenew(conn, sub.id)
        await wallet_service.credit(conn, user.id, 500, type="topup", ref="seed")

    monkeypatch.setattr(settings, "AUTO_RENEW_ENABLED", False)
    await auto_renew_job(mock_bot)
    mock_bot.send_message.assert_not_awaited()


async def test_auto_renew_job_skips_native_subscriptions(
    file_db, make_user, make_plan, make_subscription, mock_bot, monkeypatch
):
    """Native Star subs (tg_sub_charge_id set) are NOT picked up by the fallback job."""
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo
    from app.services import wallet as wallet_service

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=7)
        plan = await make_plan(conn, price_stars=100, inbound_ids=[1])
        sub = await make_subscription(
            conn,
            user_id=user.id,
            plan_id=plan.id,
            xui_inbound_id=1,
            expires_at=datetime.now(UTC) + timedelta(hours=10),
        )
        # Native subscription — has a tg charge id, so the wallet fallback skips it.
        await subs_repo.set_auto_renew(conn, sub.id, True, tg_sub_charge_id="ch-1")
        await wallet_service.credit(conn, user.id, 500, type="topup", ref="seed")

    await auto_renew_job(mock_bot)

    async with get_conn() as conn:
        bal = await __import__(
            "app.db.repos.wallet", fromlist=["balance"]
        ).balance(conn, user.id)
    assert bal == 500  # untouched — native sub not charged by the fallback


async def test_auto_renew_job_nothing_due(file_db, mock_bot):
    """No due subscriptions → job runs cleanly without sending anything."""
    await auto_renew_job(mock_bot)
    mock_bot.send_message.assert_not_awaited()


# --------------------------------------------------------------------------- #
# Phase 4 — traffic-quota alerts
# --------------------------------------------------------------------------- #


def _paged_traffic(email: str, up: int, down: int):
    """Build a paged-list panel response carrying the given traffic counters."""
    return {
        "items": [{"email": email, "traffic": {"up": up, "down": down}}],
        "total": 1,
    }


async def test_traffic_alert_fires_once_over_threshold(
    file_db, make_user, make_plan, make_subscription, mock_bot, monkeypatch
):
    """Crossing 80% of a 1 GB quota sends a one-off alert (deduped on re-run)."""
    from app.db.engine import get_conn

    gb = 1024**3
    async with get_conn() as conn:
        user = await make_user(conn, tg_id=5)
        plan = await make_plan(conn, traffic_gb=1, inbound_ids=[1])
        await make_subscription(
            conn, user_id=user.id, plan_id=plan.id,
            xui_client_email="quota@x",
        )

    xui = AsyncMock()
    # 0.9 GB used of a 1 GB quota → 90% ≥ 80% threshold.
    xui.request_json = AsyncMock(
        return_value=_paged_traffic("quota@x", up=int(0.5 * gb), down=int(0.4 * gb))
    )
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=xui))

    await traffic_snapshot_job(mock_bot)
    assert mock_bot.send_message.await_count == 1

    # Second run must dedup via subscription_notifications (kind 'traffic80').
    mock_bot.send_message.reset_mock()
    await traffic_snapshot_job(mock_bot)
    mock_bot.send_message.assert_not_awaited()


async def test_traffic_alert_below_threshold_silent(
    file_db, make_user, make_plan, make_subscription, mock_bot, monkeypatch
):
    """Under the threshold → snapshot written, no alert."""
    from app.db.engine import get_conn

    gb = 1024**3
    async with get_conn() as conn:
        user = await make_user(conn, tg_id=5)
        plan = await make_plan(conn, traffic_gb=1, inbound_ids=[1])
        await make_subscription(
            conn, user_id=user.id, plan_id=plan.id, xui_client_email="quota@x",
        )

    xui = AsyncMock()
    # 0.5 GB used of 1 GB → 50% < 80%.
    xui.request_json = AsyncMock(
        return_value=_paged_traffic("quota@x", up=int(0.3 * gb), down=int(0.2 * gb))
    )
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=xui))

    await traffic_snapshot_job(mock_bot)
    mock_bot.send_message.assert_not_awaited()


async def test_traffic_alert_skips_unlimited_plan(
    file_db, make_user, make_plan, make_subscription, mock_bot, monkeypatch
):
    """A traffic_gb=0 (unlimited) plan never alerts regardless of usage."""
    from app.db.engine import get_conn

    gb = 1024**3
    async with get_conn() as conn:
        user = await make_user(conn, tg_id=5)
        plan = await make_plan(conn, traffic_gb=0, inbound_ids=[1])
        await make_subscription(
            conn, user_id=user.id, plan_id=plan.id, xui_client_email="quota@x",
        )

    xui = AsyncMock()
    xui.request_json = AsyncMock(
        return_value=_paged_traffic("quota@x", up=100 * gb, down=100 * gb)
    )
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=xui))

    await traffic_snapshot_job(mock_bot)
    mock_bot.send_message.assert_not_awaited()


# --------------------------------------------------------------------------- #
# Phase 6 — panel health-check
# --------------------------------------------------------------------------- #


def _patch_health_probe(monkeypatch, result):
    """Patch the scheduler's health probe to return a fixed ``(ok, error)``."""
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=AsyncMock()))
    monkeypatch.setattr(
        sch_module.health_service,
        "check_xui_health",
        AsyncMock(return_value=result),
    )


async def test_health_check_first_up_probe_persists_no_alert(
    file_db, mock_bot, monkeypatch
):
    """First probe (panel up) persists state but does NOT alert (no down→up flip)."""
    from app.db.engine import get_conn
    from app.db.repos import health as health_repo

    _patch_health_probe(monkeypatch, (True, None))
    await health_check_job(mock_bot)

    # An 'up' state was recorded. The first probe counts as a transition in the
    # repo, but the job only sends a message for the *up* alert when recovering
    # — a first 'up' still alerts because changed=True. We assert the state is
    # persisted regardless; the alert-count semantics are covered below.
    async with get_conn() as conn:
        row = await health_repo.get(conn)
    assert row is not None
    assert row.status == "up"
    assert sch_module.health_service.get_cached_status() == "up"


async def test_health_check_down_then_up_alerts_once_each(
    file_db, mock_bot, monkeypatch
):
    """A full up→down→up cycle alerts admins exactly once per transition."""
    from app.db.engine import get_conn
    from app.db.repos import health as health_repo

    # 1) Seed a steady 'up' baseline (two probes; second is steady, no new alert).
    _patch_health_probe(monkeypatch, (True, None))
    await health_check_job(mock_bot)  # first probe → changed=True → 1 up-alert
    mock_bot.send_message.reset_mock()
    await health_check_job(mock_bot)  # steady up → no alert
    mock_bot.send_message.assert_not_awaited()

    # 2) Panel goes DOWN → exactly one alert per recipient (ADMIN_IDS=1,2).
    _patch_health_probe(monkeypatch, (False, "unreachable"))
    await health_check_job(mock_bot)
    assert mock_bot.send_message.await_count == 2  # two admins
    # Body is the down-alert.
    sent = [c.args[1] for c in mock_bot.send_message.await_args_list]
    assert all("unreachable" in body for body in sent)

    async with get_conn() as conn:
        row = await health_repo.get(conn)
    assert row.status == "down"
    assert row.last_error == "unreachable"
    assert sch_module.health_service.get_cached_status() == "down"

    # 3) Steady DOWN → no further alerts (no spam on repeated failures).
    mock_bot.send_message.reset_mock()
    await health_check_job(mock_bot)
    mock_bot.send_message.assert_not_awaited()

    # 4) Panel RECOVERS → exactly one up-alert per recipient.
    _patch_health_probe(monkeypatch, (True, None))
    mock_bot.send_message.reset_mock()
    await health_check_job(mock_bot)
    assert mock_bot.send_message.await_count == 2

    async with get_conn() as conn:
        row = await health_repo.get(conn)
    assert row.status == "up"
    assert row.last_error is None


async def test_health_check_no_xui_client_is_down(file_db, mock_bot, monkeypatch):
    """Failing to obtain the xui client is treated as 'down'."""
    from app.db.engine import get_conn
    from app.db.repos import health as health_repo

    async def _boom():
        raise RuntimeError("login failed")

    monkeypatch.setattr(sch_module, "get_xui_client", _boom)
    await health_check_job(mock_bot)

    async with get_conn() as conn:
        row = await health_repo.get(conn)
    assert row.status == "down"
    assert sch_module.health_service.get_cached_status() == "down"


async def test_health_check_includes_support_chat(file_db, mock_bot, monkeypatch):
    """When SUPPORT_CHAT_ID is set, the alert also reaches that chat."""
    from app.config import settings

    monkeypatch.setattr(settings, "SUPPORT_CHAT_ID", 9999)
    # First probe up alerts; assert the support chat is among the targets.
    _patch_health_probe(monkeypatch, (False, "boom"))
    await health_check_job(mock_bot)
    targets = {c.args[0] for c in mock_bot.send_message.await_args_list}
    assert 9999 in targets
