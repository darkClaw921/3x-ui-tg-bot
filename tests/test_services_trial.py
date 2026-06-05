"""Tests for :func:`app.services.subscriptions.activate_trial`."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.db.repos import subscriptions as subs_repo
from app.services import subscriptions as subs_service


async def test_activate_trial_provisions_trial(file_db, make_user):
    from app.db.engine import get_conn

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"id": "uuid", "email": "e"})

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        sub = await subs_service.activate_trial(
            conn, xui, user, inbound_id=7, days=3, traffic_gb=5
        )

    assert sub.is_trial is True
    assert sub.plan_id is None
    assert sub.xui_inbound_id == 7
    # add_client was called.
    assert xui.request_json.await_count >= 1


async def test_activate_trial_second_attempt_rejected(file_db, make_user):
    from app.db.engine import get_conn

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"id": "uuid", "email": "e"})

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        await subs_service.activate_trial(
            conn, xui, user, inbound_id=7, days=3, traffic_gb=5
        )
        with pytest.raises(subs_service.TrialAlreadyUsedError):
            await subs_service.activate_trial(
                conn, xui, user, inbound_id=7, days=3, traffic_gb=5
            )


async def test_activate_trial_sets_has_trial(file_db, make_user):
    from app.db.engine import get_conn

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"id": "uuid", "email": "e"})

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=1)
        assert await subs_repo.has_trial(conn, user.id) is False
        await subs_service.activate_trial(
            conn, xui, user, inbound_id=7, days=3, traffic_gb=0
        )
        assert await subs_repo.has_trial(conn, user.id) is True
