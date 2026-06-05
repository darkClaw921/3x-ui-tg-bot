"""Tests for :mod:`app.handlers.admin.broadcast`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.handlers.admin import broadcast as bc_mod
from app.services.broadcast import BroadcastResult
from app.states.admin import BroadcastCreate


def _state(data=None):
    s = AsyncMock()
    s.get_data = AsyncMock(return_value=data or {})
    s.update_data = AsyncMock()
    s.set_state = AsyncMock()
    s.clear = AsyncMock()
    return s


def test_plural_endings():
    assert bc_mod._plural(1) == "ю"
    assert bc_mod._plural(21) == "ю"
    assert bc_mod._plural(11) == "ям"  # teens are an exception
    assert bc_mod._plural(2) == "ям"
    assert bc_mod._plural(0) == "ям"


async def test_cb_open_enters_waiting_post():
    """Opening the broadcast flow edits the menu into the prompt."""
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await bc_mod.cb_open(cb, state)
    state.set_state.assert_awaited_with(BroadcastCreate.waiting_post)
    cb.message.edit_text.assert_awaited()
    cb.answer.assert_awaited()


async def test_st_post_stores_ref_and_confirms(file_db, make_user):
    """The post's (chat_id, message_id) is stashed; confirm shows the count."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        await make_user(conn, tg_id=111, username="a")
        await make_user(conn, tg_id=222, username="b")

    msg = MagicMock()
    msg.chat = MagicMock()
    msg.chat.id = 555
    msg.message_id = 777
    msg.answer = AsyncMock()
    state = _state()

    await bc_mod.st_post(msg, state)

    state.update_data.assert_awaited_with(post_chat_id=555, post_message_id=777)
    state.set_state.assert_awaited_with(BroadcastCreate.confirming)
    msg.answer.assert_awaited()
    # Confirmation prompt mentions the audience size (2 users).
    text = msg.answer.await_args.args[0]
    assert "2" in text


async def test_cb_send_broadcasts_and_reports(file_db, make_user, monkeypatch):
    """Confirm copies the stored post to all users and edits in the summary."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        await make_user(conn, tg_id=111, username="a")
        await make_user(conn, tg_id=222, username="b")
        await make_user(conn, tg_id=333, username="c")

    fake = AsyncMock(return_value=BroadcastResult(total=3, sent=2, blocked=1, failed=0))
    monkeypatch.setattr(bc_mod, "broadcast_message", fake)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    bot = AsyncMock()
    state = _state({"post_chat_id": 555, "post_message_id": 777})

    await bc_mod.cb_send(cb, state, bot)

    fake.assert_awaited_once()
    kwargs = fake.await_args.kwargs
    assert kwargs["from_chat_id"] == 555
    assert kwargs["message_id"] == 777
    assert sorted(kwargs["tg_ids"]) == [111, 222, 333]
    cb.answer.assert_awaited()
    state.clear.assert_awaited()
    # Two edits: «запущена…» then the result summary.
    assert cb.message.edit_text.await_count == 2
    summary = cb.message.edit_text.await_args_list[-1].args[0]
    assert "Доставлено: 2" in summary
    assert "Заблокировали бота: 1" in summary


async def test_cb_send_missing_post_ref_aborts():
    """No stored post → alert + reset, no broadcast attempted."""
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    bot = AsyncMock()
    state = _state({})  # no post_chat_id / post_message_id

    await bc_mod.cb_send(cb, state, bot)

    cb.answer.assert_awaited()
    assert cb.answer.await_args.kwargs.get("show_alert") is True
    state.clear.assert_awaited()
