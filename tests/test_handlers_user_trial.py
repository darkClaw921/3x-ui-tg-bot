"""Tests for :mod:`app.handlers.user.trial` — the free-trial flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.handlers.user import trial as trial_handler
from app.services.inbounds import InboundOption
from app.states.user import TrialFlow


def _cb(tg_id=1):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.message.chat = MagicMock(id=tg_id)
    cb.answer = AsyncMock()
    return cb


async def test_cb_open_disabled(file_db, make_user, monkeypatch):
    from app.db.engine import get_conn

    monkeypatch.setattr(trial_handler.settings, "TRIAL_DAYS", 0, raising=False)
    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
    cb = _cb()
    state = AsyncMock()
    await trial_handler.cb_open(cb, state, AsyncMock(), user=user, lang="ru")
    assert cb.answer.call_args.kwargs.get("show_alert") is True


async def test_cb_open_already_used(file_db, make_user, monkeypatch):
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo
    from datetime import UTC, datetime, timedelta

    monkeypatch.setattr(trial_handler.settings, "TRIAL_DAYS", 3, raising=False)
    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        await subs_repo.create(
            conn,
            user_id=user.id,
            xui_inbound_id=1,
            xui_client_uuid="u",
            xui_client_email="e",
            expires_at=datetime.now(UTC) + timedelta(days=3),
            plan_id=None,
            xui_sub_id="s",
            is_trial=True,
        )
    cb = _cb()
    state = AsyncMock()
    await trial_handler.cb_open(cb, state, AsyncMock(), user=user, lang="ru")
    assert cb.answer.call_args.kwargs.get("show_alert") is True


async def test_cb_open_single_inbound_auto_activates(
    file_db, make_user, monkeypatch
):
    from app.db.engine import get_conn

    monkeypatch.setattr(trial_handler.settings, "TRIAL_DAYS", 3, raising=False)
    monkeypatch.setattr(trial_handler.settings, "TRIAL_TRAFFIC_GB", 0, raising=False)
    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)

    monkeypatch.setattr(
        trial_handler, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    monkeypatch.setattr(
        trial_handler,
        "list_user_inbounds",
        AsyncMock(return_value=[InboundOption(id=5, remark="DE", port=443, enabled=True)]),
    )
    activated = AsyncMock(return_value=MagicMock(
        id=1, xui_inbound_id=5, xui_sub_id="s", xui_client_uuid="u",
        xui_client_email="e", expires_at="2026-01-01", is_trial=True,
    ))
    monkeypatch.setattr(trial_handler.subs_service, "activate_trial", activated)
    monkeypatch.setattr(trial_handler, "deliver_keys", AsyncMock())

    cb = _cb()
    state = AsyncMock()
    await trial_handler.cb_open(cb, state, AsyncMock(), user=user, lang="ru")

    activated.assert_awaited_once()
    assert activated.await_args.kwargs["inbound_id"] == 5
    trial_handler.deliver_keys.assert_awaited_once()


async def test_cb_open_multi_inbound_shows_selection(
    file_db, make_user, monkeypatch
):
    from app.db.engine import get_conn

    monkeypatch.setattr(trial_handler.settings, "TRIAL_DAYS", 3, raising=False)
    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)

    monkeypatch.setattr(
        trial_handler, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    monkeypatch.setattr(
        trial_handler,
        "list_user_inbounds",
        AsyncMock(return_value=[
            InboundOption(id=5, remark="DE", port=443, enabled=True),
            InboundOption(id=6, remark="NL", port=443, enabled=True),
        ]),
    )
    cb = _cb()
    state = AsyncMock()
    await trial_handler.cb_open(cb, state, AsyncMock(), user=user, lang="ru")
    state.set_state.assert_awaited_with(TrialFlow.choosing_inbound)
    cb.message.edit_text.assert_awaited()


async def test_cb_pick_inbound_activates(file_db, make_user, monkeypatch):
    from app.db.engine import get_conn
    from app.keyboards.user import InboundCB

    monkeypatch.setattr(trial_handler.settings, "TRIAL_DAYS", 3, raising=False)
    monkeypatch.setattr(trial_handler.settings, "TRIAL_TRAFFIC_GB", 0, raising=False)
    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)

    monkeypatch.setattr(
        trial_handler, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    activated = AsyncMock(return_value=MagicMock(
        id=1, xui_inbound_id=6, xui_sub_id="s", xui_client_uuid="u",
        xui_client_email="e", expires_at="2026-01-01", is_trial=True,
    ))
    monkeypatch.setattr(trial_handler.subs_service, "activate_trial", activated)
    monkeypatch.setattr(trial_handler, "deliver_keys", AsyncMock())

    cb = _cb()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"inbound_options": [{"id": 6}]})
    cbd = InboundCB(action="pick", inbound_id=6)
    await trial_handler.cb_pick_inbound(cb, cbd, state, AsyncMock(), user=user, lang="ru")
    activated.assert_awaited_once()
    assert activated.await_args.kwargs["inbound_id"] == 6


async def test_cb_pick_inbound_rejects_unoffered(file_db, make_user, monkeypatch):
    from app.db.engine import get_conn
    from app.keyboards.user import InboundCB

    monkeypatch.setattr(trial_handler.settings, "TRIAL_DAYS", 3, raising=False)
    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)

    activated = AsyncMock()
    monkeypatch.setattr(trial_handler.subs_service, "activate_trial", activated)
    cb = _cb()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"inbound_options": [{"id": 5}]})
    cbd = InboundCB(action="pick", inbound_id=99)
    await trial_handler.cb_pick_inbound(cb, cbd, state, AsyncMock(), user=user, lang="ru")
    activated.assert_not_awaited()
    assert cb.answer.call_args.kwargs.get("show_alert") is True


async def test_cb_open_no_user_alerts(file_db):
    cb = _cb()
    state = AsyncMock()
    await trial_handler.cb_open(cb, state, AsyncMock(), user=None, lang="ru")
    assert cb.answer.call_args.kwargs.get("show_alert") is True


async def test_cb_open_panel_unavailable(file_db, make_user, monkeypatch):
    from app.db.engine import get_conn
    from app.xui import XuiError

    monkeypatch.setattr(trial_handler.settings, "TRIAL_DAYS", 3, raising=False)
    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)

    monkeypatch.setattr(
        trial_handler, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    monkeypatch.setattr(
        trial_handler,
        "list_user_inbounds",
        AsyncMock(side_effect=XuiError("down")),
    )
    cb = _cb()
    state = AsyncMock()
    await trial_handler.cb_open(cb, state, AsyncMock(), user=user, lang="ru")
    assert cb.answer.call_args.kwargs.get("show_alert") is True


async def test_cb_open_no_inbounds(file_db, make_user, monkeypatch):
    from app.db.engine import get_conn

    monkeypatch.setattr(trial_handler.settings, "TRIAL_DAYS", 3, raising=False)
    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
    monkeypatch.setattr(
        trial_handler, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    monkeypatch.setattr(
        trial_handler, "list_user_inbounds", AsyncMock(return_value=[])
    )
    cb = _cb()
    state = AsyncMock()
    await trial_handler.cb_open(cb, state, AsyncMock(), user=user, lang="ru")
    assert cb.answer.call_args.kwargs.get("show_alert") is True


async def test_activate_already_used_during_activate(file_db, make_user, monkeypatch):
    from app.db.engine import get_conn
    from app.services import subscriptions as subs_service

    monkeypatch.setattr(trial_handler.settings, "TRIAL_DAYS", 3, raising=False)
    monkeypatch.setattr(trial_handler.settings, "TRIAL_TRAFFIC_GB", 0, raising=False)
    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)

    monkeypatch.setattr(
        trial_handler, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    monkeypatch.setattr(
        trial_handler,
        "list_user_inbounds",
        AsyncMock(return_value=[InboundOption(id=5, remark="DE", port=443, enabled=True)]),
    )
    monkeypatch.setattr(
        trial_handler.subs_service,
        "activate_trial",
        AsyncMock(side_effect=subs_service.TrialAlreadyUsedError(1)),
    )
    cb = _cb()
    state = AsyncMock()
    await trial_handler.cb_open(cb, state, AsyncMock(), user=user, lang="ru")
    state.clear.assert_awaited()
    assert cb.answer.call_args.kwargs.get("show_alert") is True


async def test_activate_xui_error(file_db, make_user, monkeypatch):
    from app.db.engine import get_conn
    from app.xui import XuiError

    monkeypatch.setattr(trial_handler.settings, "TRIAL_DAYS", 3, raising=False)
    monkeypatch.setattr(trial_handler.settings, "TRIAL_TRAFFIC_GB", 0, raising=False)
    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)

    monkeypatch.setattr(
        trial_handler, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    monkeypatch.setattr(
        trial_handler,
        "list_user_inbounds",
        AsyncMock(return_value=[InboundOption(id=5, remark="DE", port=443, enabled=True)]),
    )
    monkeypatch.setattr(
        trial_handler.subs_service,
        "activate_trial",
        AsyncMock(side_effect=XuiError("panel down")),
    )
    cb = _cb()
    state = AsyncMock()
    await trial_handler.cb_open(cb, state, AsyncMock(), user=user, lang="ru")
    state.clear.assert_awaited()
    cb.message.edit_text.assert_awaited()


async def test_cb_back_inbound(file_db, make_user, monkeypatch):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
    monkeypatch.setattr(trial_handler.settings, "TRIAL_DAYS", 3, raising=False)
    cb = _cb()
    state = AsyncMock()
    await trial_handler.cb_back_inbound(cb, state, user=user, lang="ru")
    state.clear.assert_awaited()
    cb.answer.assert_awaited()
