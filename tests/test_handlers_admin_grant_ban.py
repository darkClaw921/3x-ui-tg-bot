"""Tests for the admin manual-grant + ban handlers in :mod:`app.handlers.admin.users`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.handlers.admin import users as users_mod
from app.keyboards.admin import GrantCB, UserCB


def _state(data=None):
    s = AsyncMock()
    s.get_data = AsyncMock(return_value=data or {})
    s.update_data = AsyncMock()
    s.set_state = AsyncMock()
    s.clear = AsyncMock()
    return s


def _admin_user():
    from app.db.repos.users import User

    return User(
        id=99, tg_id=1, username="adm", first_name="Adm",
        is_admin=True, created_at="2025",
    )


# --------------------------------------------------------------------------- #
# Grant flow
# --------------------------------------------------------------------------- #


async def test_grant_open_shows_plans(file_db, make_user, make_plan):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        target = await make_user(conn, tg_id=200)
        await make_plan(conn, days=30, inbound_ids=[1])

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await users_mod.cb_grant_open(
        cb, UserCB(action="grant_sub", id=target.id), state, lang="ru"
    )
    state.set_state.assert_awaited_once()
    state.update_data.assert_awaited_once()
    cb.message.edit_text.assert_awaited_once()


async def test_grant_open_no_plans_alerts(file_db, make_user):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        target = await make_user(conn, tg_id=200)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.answer = AsyncMock()
    await users_mod.cb_grant_open(
        cb, UserCB(action="grant_sub", id=target.id), _state(), lang="ru"
    )
    cb.answer.assert_awaited_once()
    assert cb.answer.call_args.kwargs.get("show_alert") is True


async def test_grant_plan_asks_days(file_db, make_user, make_plan):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        target = await make_user(conn, tg_id=200)
        plan = await make_plan(conn, days=30, inbound_ids=[7])

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state({"grant_user_id": target.id})
    await users_mod.cb_grant_plan(
        cb, GrantCB(action="plan", plan_id=plan.id), state, lang="ru"
    )
    state.set_state.assert_awaited_once()
    # inbound resolved + stored
    update_kwargs = state.update_data.await_args.kwargs
    assert update_kwargs.get("grant_plan_id") == plan.id
    assert update_kwargs.get("grant_inbound_id") == 7


async def test_grant_days_rejects_bad_input(file_db, make_user, make_plan):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        target = await make_user(conn, tg_id=200)
        plan = await make_plan(conn, days=30, inbound_ids=[7])

    msg = MagicMock()
    msg.text = "abc"
    msg.answer = AsyncMock()
    bot = AsyncMock()
    state = _state(
        {"grant_user_id": target.id, "grant_plan_id": plan.id, "grant_inbound_id": 7}
    )
    await users_mod.st_grant_days(msg, state, bot, user=_admin_user(), lang="ru")
    msg.answer.assert_awaited_once()
    state.clear.assert_not_awaited()


async def test_grant_days_default_provisions(file_db, make_user, make_plan, monkeypatch):
    from app.db.engine import get_conn
    from app.db.repos import audit as audit_repo
    from app.db.repos import subscriptions as subs_repo

    async with get_conn() as conn:
        admin = await make_user(conn, tg_id=1, is_admin=True)
        target = await make_user(conn, tg_id=200)
        plan = await make_plan(conn, days=30, inbound_ids=[7])

    monkeypatch.setattr(
        users_mod, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    # Make deliver_keys a no-op so we don't exercise the link-builder here.
    monkeypatch.setattr(users_mod, "deliver_keys", AsyncMock())

    msg = MagicMock()
    msg.text = "-"
    msg.answer = AsyncMock()
    bot = AsyncMock()
    state = _state(
        {"grant_user_id": target.id, "grant_plan_id": plan.id, "grant_inbound_id": 7}
    )
    await users_mod.st_grant_days(msg, state, bot, user=admin, lang="ru")

    state.clear.assert_awaited_once()
    async with get_conn() as conn:
        subs = await subs_repo.list_for_user(conn, target.id)
        assert len(subs) == 1 and subs[0].plan_id == plan.id
        audit = await audit_repo.list_recent(conn, limit=10)
        assert any(a.action == "user.grant_sub" for a in audit)

    # the target user got a DM notice
    assert bot.send_message.await_count >= 1


async def test_grant_days_custom_term(file_db, make_user, make_plan, monkeypatch):
    from app.db.engine import get_conn
    from app.db.repos import subscriptions as subs_repo

    async with get_conn() as conn:
        target = await make_user(conn, tg_id=200)
        plan = await make_plan(conn, days=30, inbound_ids=[7])

    monkeypatch.setattr(
        users_mod, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    monkeypatch.setattr(users_mod, "deliver_keys", AsyncMock())

    msg = MagicMock()
    msg.text = "5"
    msg.answer = AsyncMock()
    bot = AsyncMock()
    state = _state(
        {"grant_user_id": target.id, "grant_plan_id": plan.id, "grant_inbound_id": 7}
    )
    await users_mod.st_grant_days(msg, state, bot, user=_admin_user(), lang="ru")
    async with get_conn() as conn:
        subs = await subs_repo.list_for_user(conn, target.id)
        assert len(subs) == 1


# --------------------------------------------------------------------------- #
# Ban / block flow
# --------------------------------------------------------------------------- #


async def test_toggle_block_blocks_user(file_db, make_user, monkey_settings):
    from app.db.engine import get_conn
    from app.db.repos import audit as audit_repo
    from app.db.repos import users as users_repo

    monkey_settings(ADMIN_IDS=[])
    async with get_conn() as conn:
        admin = await make_user(conn, tg_id=1, is_admin=True)
        target = await make_user(conn, tg_id=200)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await users_mod.cb_toggle_block(
        cb, UserCB(action="toggle_block", id=target.id), user=admin, lang="ru"
    )

    async with get_conn() as conn:
        refreshed = await users_repo.get_by_id(conn, target.id)
        assert refreshed.is_blocked is True
        audit = await audit_repo.list_recent(conn, limit=10)
        assert any(a.action == "user.block" for a in audit)


async def test_toggle_block_unblocks_user(file_db, make_user, monkey_settings):
    from app.db.engine import get_conn
    from app.db.repos import users as users_repo

    monkey_settings(ADMIN_IDS=[])
    async with get_conn() as conn:
        target = await make_user(conn, tg_id=200)
        await users_repo.set_blocked(conn, target.id, True)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await users_mod.cb_toggle_block(
        cb, UserCB(action="toggle_block", id=target.id), user=_admin_user(), lang="ru"
    )
    async with get_conn() as conn:
        refreshed = await users_repo.get_by_id(conn, target.id)
        assert refreshed.is_blocked is False


async def test_toggle_block_refuses_self(file_db, make_user, monkey_settings):
    from app.db.engine import get_conn
    from app.db.repos import users as users_repo

    monkey_settings(ADMIN_IDS=[])
    async with get_conn() as conn:
        admin = await make_user(conn, tg_id=1, is_admin=True)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.answer = AsyncMock()
    acting = await _reload(admin.id)
    await users_mod.cb_toggle_block(
        cb, UserCB(action="toggle_block", id=admin.id), user=acting, lang="ru"
    )
    cb.answer.assert_awaited_once()
    assert cb.answer.call_args.kwargs.get("show_alert") is True
    async with get_conn() as conn:
        refreshed = await users_repo.get_by_id(conn, admin.id)
        assert refreshed.is_blocked is False


async def test_toggle_block_refuses_admin_target(file_db, make_user, monkey_settings):
    from app.db.engine import get_conn
    from app.db.repos import users as users_repo

    monkey_settings(ADMIN_IDS=[500])
    async with get_conn() as conn:
        target = await make_user(conn, tg_id=500, is_admin=True)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.answer = AsyncMock()
    await users_mod.cb_toggle_block(
        cb, UserCB(action="toggle_block", id=target.id), user=_admin_user(), lang="ru"
    )
    cb.answer.assert_awaited_once()
    assert cb.answer.call_args.kwargs.get("show_alert") is True
    async with get_conn() as conn:
        refreshed = await users_repo.get_by_id(conn, target.id)
        assert refreshed.is_blocked is False


async def _reload(user_id: int):
    from app.db.engine import get_conn
    from app.db.repos import users as users_repo

    async with get_conn() as conn:
        return await users_repo.get_by_id(conn, user_id)
