"""Tests for the trial-subscription DB additions (``is_trial`` + one-trial)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import aiosqlite
import pytest

from app.db.repos import subscriptions as subs_repo


def _exp():
    return datetime.now(UTC) + timedelta(days=3)


async def test_create_default_is_trial_false(db_conn, make_user):
    user = await make_user(db_conn, tg_id=1)
    sub = await subs_repo.create(
        db_conn,
        user_id=user.id,
        xui_inbound_id=1,
        xui_client_uuid="u",
        xui_client_email="e",
        expires_at=_exp(),
        plan_id=None,
        xui_sub_id="s",
    )
    assert sub.is_trial is False


async def test_create_trial_sets_flag(db_conn, make_user):
    user = await make_user(db_conn, tg_id=1)
    sub = await subs_repo.create(
        db_conn,
        user_id=user.id,
        xui_inbound_id=1,
        xui_client_uuid="u",
        xui_client_email="e",
        expires_at=_exp(),
        plan_id=None,
        xui_sub_id="s",
        is_trial=True,
    )
    assert sub.is_trial is True


async def test_has_trial(db_conn, make_user):
    user = await make_user(db_conn, tg_id=1)
    assert await subs_repo.has_trial(db_conn, user.id) is False
    await subs_repo.create(
        db_conn,
        user_id=user.id,
        xui_inbound_id=1,
        xui_client_uuid="u",
        xui_client_email="e",
        expires_at=_exp(),
        plan_id=None,
        xui_sub_id="s",
        is_trial=True,
    )
    assert await subs_repo.has_trial(db_conn, user.id) is True


async def test_one_trial_per_user_enforced(db_conn, make_user):
    user = await make_user(db_conn, tg_id=1)
    await subs_repo.create(
        db_conn,
        user_id=user.id,
        xui_inbound_id=1,
        xui_client_uuid="u1",
        xui_client_email="e1",
        expires_at=_exp(),
        plan_id=None,
        xui_sub_id="s1",
        is_trial=True,
    )
    with pytest.raises(aiosqlite.IntegrityError):
        await subs_repo.create(
            db_conn,
            user_id=user.id,
            xui_inbound_id=1,
            xui_client_uuid="u2",
            xui_client_email="e2",
            expires_at=_exp(),
            plan_id=None,
            xui_sub_id="s2",
            is_trial=True,
        )


async def test_regular_subs_unconstrained_by_trial_index(db_conn, make_user):
    user = await make_user(db_conn, tg_id=1)
    for i in range(3):
        await subs_repo.create(
            db_conn,
            user_id=user.id,
            xui_inbound_id=1,
            xui_client_uuid=f"u{i}",
            xui_client_email=f"e{i}",
            expires_at=_exp(),
            plan_id=None,
            xui_sub_id=f"s{i}",
            is_trial=False,
        )
    subs = await subs_repo.list_for_user(db_conn, user.id)
    assert len(subs) == 3
