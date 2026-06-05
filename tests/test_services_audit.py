"""Tests for :mod:`app.services.audit` — log_action wrapper."""

from __future__ import annotations

from unittest.mock import AsyncMock

from app.db.repos import audit as audit_repo
from app.services import audit as audit_service
from app.services.audit import _serialise_details


async def test_log_action_persists(db_conn, make_user):
    admin = await make_user(db_conn, tg_id=1, is_admin=True)
    entry = await audit_service.log_action(
        db_conn,
        admin.id,
        "user.block",
        target_type="user",
        target_id=admin.id,
        details={"is_blocked": True},
    )
    assert entry is not None
    rows = await audit_repo.list_recent(db_conn, limit=10)
    assert rows[0].action == "user.block"
    assert '"is_blocked":true' in rows[0].details


async def test_log_action_no_details(db_conn, make_user):
    admin = await make_user(db_conn, tg_id=1, is_admin=True)
    entry = await audit_service.log_action(db_conn, admin.id, "broadcast.send")
    assert entry is not None and entry.details is None


async def test_log_action_is_crash_safe(monkeypatch):
    """A repo failure is swallowed and ``None`` is returned, never raised."""
    boom = AsyncMock(side_effect=RuntimeError("db down"))
    monkeypatch.setattr(audit_repo, "add", boom)
    result = await audit_service.log_action(
        AsyncMock(), 1, "plan.create", target_type="plan", target_id=1
    )
    assert result is None


def test_serialise_details_none():
    assert _serialise_details(None) is None


def test_serialise_details_json():
    out = _serialise_details({"a": 1, "b": "x"})
    assert out == '{"a":1,"b":"x"}'


def test_serialise_details_non_json_falls_back():
    class NotJSON:
        def __repr__(self) -> str:
            return "NJ"

    out = _serialise_details({"obj": NotJSON()})
    # json.dumps raises TypeError on the object → falls back to str(details)
    assert "NJ" in out
