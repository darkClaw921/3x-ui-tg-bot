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
    expire_check_job,
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


def test_setup_scheduler_registers_three_jobs():
    bot = MagicMock()
    sched = setup_scheduler(bot)
    job_ids = {j.id for j in sched.get_jobs()}
    assert job_ids == {"expire_check", "reminders", "traffic_snapshots"}


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
    xui_mock.request_json = AsyncMock(return_value={"up": 100, "down": 200})
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
