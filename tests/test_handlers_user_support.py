"""Tests for :mod:`app.handlers.user.support`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.db.repos.users import User
from app.handlers.user import support as support_mod


def _user(**kw):
    base = dict(
        id=1, tg_id=555, username="joe", first_name="Joe",
        is_admin=False, created_at="2025",
    )
    base.update(kw)
    return User(**base)


def _state(data=None):
    s = AsyncMock()
    s.get_data = AsyncMock(return_value=data or {})
    s.update_data = AsyncMock()
    s.set_state = AsyncMock()
    s.clear = AsyncMock()
    return s


def test_user_label_with_username():
    label = support_mod._user_label(_user())
    assert "@joe" in label and "555" in label


def test_user_label_without_username():
    label = support_mod._user_label(_user(username=None, first_name=None))
    assert "#555" in label


async def test_cb_open_requires_user():
    cb = MagicMock()
    cb.answer = AsyncMock()
    await support_mod.cb_open(cb, _state(), user=None, lang="ru")
    cb.answer.assert_awaited_once()
    assert cb.answer.call_args.kwargs.get("show_alert") is True


async def test_cb_open_enters_writing_state():
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await support_mod.cb_open(cb, state, user=_user(), lang="ru")
    state.set_state.assert_awaited_once()
    cb.message.edit_text.assert_awaited_once()


async def test_st_message_rejects_empty():
    msg = MagicMock()
    msg.text = "   "
    msg.answer = AsyncMock()
    bot = AsyncMock()
    state = _state()
    await support_mod.st_message(msg, state, bot, user=_user(), lang="ru")
    msg.answer.assert_awaited_once()
    state.clear.assert_not_awaited()


async def test_st_message_creates_ticket_and_notifies(file_db, monkey_settings):
    from app.db.engine import get_conn
    from app.db.repos import tickets as tickets_repo
    from app.db.repos import users as users_repo

    monkey_settings(ADMIN_IDS=[1, 2], SUPPORT_CHAT_ID=0)
    async with get_conn() as conn:
        user = await users_repo.create(
            conn, tg_id=555, username="joe", first_name="Joe"
        )

    msg = MagicMock()
    msg.text = "my vpn is broken"
    msg.message_id = 77
    msg.answer = AsyncMock()
    bot = AsyncMock()
    state = _state()
    await support_mod.st_message(msg, state, bot, user=user, lang="ru")

    state.clear.assert_awaited_once()
    msg.answer.assert_awaited_once()
    # admins 1 and 2 notified
    assert bot.send_message.await_count == 2
    targets = {c.args[0] for c in bot.send_message.await_args_list}
    assert targets == {1, 2}

    async with get_conn() as conn:
        tickets = await tickets_repo.list_for_user(conn, user.id)
        assert len(tickets) == 1
        msgs = await tickets_repo.list_messages(conn, tickets[0].id)
        assert msgs[0].text == "my vpn is broken"
        assert msgs[0].tg_message_id == 77


async def test_notify_admins_includes_support_chat(monkey_settings):
    monkey_settings(ADMIN_IDS=[1], SUPPORT_CHAT_ID=-100500)
    bot = AsyncMock()
    await support_mod.notify_admins(bot, ticket_id=3, user=_user(), text="hi")
    targets = {c.args[0] for c in bot.send_message.await_args_list}
    assert targets == {1, -100500}


async def test_notify_admins_best_effort_on_failure(monkey_settings):
    """One failing recipient does not abort the fan-out."""
    monkey_settings(ADMIN_IDS=[1, 2], SUPPORT_CHAT_ID=0)
    bot = AsyncMock()
    bot.send_message = AsyncMock(side_effect=[Exception("blocked"), MagicMock()])
    await support_mod.notify_admins(bot, ticket_id=3, user=_user(), text="hi")
    assert bot.send_message.await_count == 2
