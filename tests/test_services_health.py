"""Tests for :mod:`app.services.health` and :mod:`app.db.repos.health`."""

from __future__ import annotations

from unittest.mock import AsyncMock

from app.db.repos import health as health_repo
from app.services import health as health_service
from app.xui import XuiError


# --------------------------------------------------------------------------- #
# check_xui_health
# --------------------------------------------------------------------------- #


async def test_check_xui_health_ok(monkeypatch):
    """A successful list_inbounds → (True, None)."""
    monkeypatch.setattr(
        health_service, "list_inbounds", AsyncMock(return_value=[{"id": 1}])
    )
    ok, err = await health_service.check_xui_health(AsyncMock())
    assert ok is True
    assert err is None


async def test_check_xui_health_xui_error(monkeypatch):
    """An XuiError is caught and reported as (False, reason)."""
    monkeypatch.setattr(
        health_service,
        "list_inbounds",
        AsyncMock(side_effect=XuiError("panel boom")),
    )
    ok, err = await health_service.check_xui_health(AsyncMock())
    assert ok is False
    assert err is not None
    assert "boom" in err


async def test_check_xui_health_unexpected_error(monkeypatch):
    """Any unexpected exception is caught (probe must never raise)."""
    monkeypatch.setattr(
        health_service,
        "list_inbounds",
        AsyncMock(side_effect=RuntimeError("wat")),
    )
    ok, err = await health_service.check_xui_health(AsyncMock())
    assert ok is False
    assert err is not None


async def test_check_xui_health_timeout(monkeypatch):
    """A probe that exceeds the timeout → (False, 'timeout...')."""
    import asyncio

    async def _never(_client):
        await asyncio.sleep(10)

    monkeypatch.setattr(health_service, "list_inbounds", _never)
    monkeypatch.setattr(health_service, "_PROBE_TIMEOUT_SEC", 0.01)
    ok, err = await health_service.check_xui_health(AsyncMock())
    assert ok is False
    assert "timeout" in (err or "")


# --------------------------------------------------------------------------- #
# cached status snapshot
# --------------------------------------------------------------------------- #


def test_cached_status_roundtrip():
    health_service.set_cached_status(None)
    assert health_service.get_cached_status() is None
    health_service.set_cached_status("up")
    assert health_service.get_cached_status() == "up"
    health_service.set_cached_status("down")
    assert health_service.get_cached_status() == "down"
    health_service.set_cached_status(None)


# --------------------------------------------------------------------------- #
# health repo — record() transition semantics
# --------------------------------------------------------------------------- #


async def test_health_repo_first_probe_is_a_change(file_db):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        assert await health_repo.get(conn) is None
        row, changed = await health_repo.record(conn, status="up")
        assert changed is True  # first probe counts as a transition
        assert row.status == "up"
        assert row.last_error is None


async def test_health_repo_steady_state_not_changed(file_db):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        await health_repo.record(conn, status="up")
        row, changed = await health_repo.record(conn, status="up")
        assert changed is False
        assert row.status == "up"


async def test_health_repo_flip_reports_change_and_error(file_db):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        await health_repo.record(conn, status="up")
        row, changed = await health_repo.record(
            conn, status="down", last_error="unreachable"
        )
        assert changed is True
        assert row.status == "down"
        assert row.last_error == "unreachable"
        # recovery flips back
        row, changed = await health_repo.record(conn, status="up")
        assert changed is True
        assert row.status == "up"
        assert row.last_error is None


async def test_health_repo_changed_at_stable_in_steady_state(file_db):
    """changed_at only moves on a real flip, not every probe."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        first, _ = await health_repo.record(conn, status="down", last_error="a")
        # second steady probe with a different error message
        second, changed = await health_repo.record(
            conn, status="down", last_error="b"
        )
        assert changed is False
        assert second.changed_at == first.changed_at  # not bumped
        assert second.last_error == "b"  # but latest error is current
