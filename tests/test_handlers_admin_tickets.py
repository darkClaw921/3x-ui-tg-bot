"""Tests for :mod:`app.handlers.admin.tickets`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.db.repos.users import User
from app.handlers.admin import tickets as tickets_mod
from app.keyboards.admin import TicketCB


def _admin():
    return User(
        id=99, tg_id=1, username="adm", first_name="Adm",
        is_admin=True, created_at="2025",
    )


def _state(data=None):
    s = AsyncMock()
    s.get_data = AsyncMock(return_value=data or {})
    s.update_data = AsyncMock()
    s.set_state = AsyncMock()
    s.clear = AsyncMock()
    return s


def test_status_label():
    assert "🟡" in tickets_mod._status_label("open", "ru")
    assert "🟢" in tickets_mod._status_label("answered", "ru")
    assert "⚪" in tickets_mod._status_label("closed", "ru")


def test_user_short_variants():
    u = User(id=1, tg_id=5, username="x", first_name="X", is_admin=False, created_at="2025")
    assert tickets_mod._user_short(u) == "@x"
    u2 = User(id=1, tg_id=5, username=None, first_name="X", is_admin=False, created_at="2025")
    assert tickets_mod._user_short(u2) == "X"
    assert tickets_mod._user_short(None) == "—"


async def _setup_ticket(file_db, text="help"):
    from app.db.engine import get_conn
    from app.db.repos import users as users_repo
    from app.services import tickets as tickets_service

    async with get_conn() as conn:
        # A real admin row so audit FK (admin_id → users.id) is satisfied.
        await users_repo.create(
            conn, tg_id=1, username="adm", first_name="Adm", is_admin=True
        )
        owner = await users_repo.create(
            conn, tg_id=555, username="joe", first_name="Joe"
        )
        ticket, _ = await tickets_service.open_ticket(conn, owner, text)
    return owner, ticket


async def _db_admin():
    from app.db.engine import get_conn
    from app.db.repos import users as users_repo

    async with get_conn() as conn:
        return await users_repo.get_by_tg_id(conn, 1)


async def test_cb_open_lists_tickets(file_db):
    await _setup_ticket(file_db)
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await tickets_mod.cb_open(cb, _state(), lang="ru")
    cb.message.edit_text.assert_awaited_once()
    text = cb.message.edit_text.await_args.args[0]
    assert "Открытые тикеты" in text


async def test_cb_open_empty(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await tickets_mod.cb_open(cb, _state(), lang="ru")
    text = cb.message.edit_text.await_args.args[0]
    assert "нет" in text.lower()


async def test_cb_card_shows_transcript(file_db):
    _owner, ticket = await _setup_ticket(file_db, text="my problem")
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await tickets_mod.cb_card(cb, TicketCB(action="card", id=ticket.id), _state(), lang="ru")
    text = cb.message.edit_text.await_args.args[0]
    assert "my problem" in text


async def test_cb_card_not_found(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.answer = AsyncMock()
    await tickets_mod.cb_card(cb, TicketCB(action="card", id=999), _state(), lang="ru")
    cb.answer.assert_awaited_once()
    assert cb.answer.call_args.kwargs.get("show_alert") is True


async def test_cb_reply_enters_state(file_db):
    _owner, ticket = await _setup_ticket(file_db)
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await tickets_mod.cb_reply(cb, TicketCB(action="reply", id=ticket.id), state, lang="ru")
    state.set_state.assert_awaited_once()
    state.update_data.assert_awaited_once()


async def test_st_reply_delivers_and_answers(file_db):
    owner, ticket = await _setup_ticket(file_db)
    from app.db.engine import get_conn
    from app.db.repos import tickets as tickets_repo

    msg = MagicMock()
    msg.text = "we fixed it"
    msg.message_id = 5
    msg.answer = AsyncMock()
    bot = AsyncMock()
    state = _state({"reply_ticket_id": ticket.id})
    await tickets_mod.st_reply(msg, state, bot, user=_admin(), lang="ru")

    # reply delivered to the owner
    assert bot.send_message.await_count == 1
    assert bot.send_message.await_args.args[0] == owner.tg_id
    state.clear.assert_awaited_once()

    async with get_conn() as conn:
        refreshed = await tickets_repo.get(conn, ticket.id)
        assert refreshed.status == "answered"
        msgs = await tickets_repo.list_messages(conn, ticket.id)
        assert msgs[-1].sender == "admin" and msgs[-1].text == "we fixed it"


async def test_st_reply_rejects_empty(file_db):
    _owner, ticket = await _setup_ticket(file_db)
    msg = MagicMock()
    msg.text = ""
    msg.answer = AsyncMock()
    bot = AsyncMock()
    state = _state({"reply_ticket_id": ticket.id})
    await tickets_mod.st_reply(msg, state, bot, user=_admin(), lang="ru")
    msg.answer.assert_awaited_once()
    state.clear.assert_not_awaited()


async def test_st_reply_delivery_failure_reports(file_db):
    _owner, ticket = await _setup_ticket(file_db)
    msg = MagicMock()
    msg.text = "reply"
    msg.message_id = 5
    msg.answer = AsyncMock()
    bot = AsyncMock()
    bot.send_message = AsyncMock(side_effect=Exception("user blocked bot"))
    state = _state({"reply_ticket_id": ticket.id})
    await tickets_mod.st_reply(msg, state, bot, user=_admin(), lang="ru")
    # The admin is told delivery failed (reply_failed), but the reply is saved.
    assert msg.answer.await_count >= 1


async def test_cb_close_closes_and_notifies(file_db):
    owner, ticket = await _setup_ticket(file_db)
    from app.db.engine import get_conn
    from app.db.repos import tickets as tickets_repo

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    bot = AsyncMock()
    await tickets_mod.cb_close(
        cb, TicketCB(action="close", id=ticket.id), _state(), bot, user=_admin(), lang="ru"
    )
    assert bot.send_message.await_count == 1
    assert bot.send_message.await_args.args[0] == owner.tg_id

    async with get_conn() as conn:
        refreshed = await tickets_repo.get(conn, ticket.id)
        assert refreshed.status == "closed"


async def test_audit_written_on_reply(file_db):
    _owner, ticket = await _setup_ticket(file_db)
    from app.db.engine import get_conn
    from app.db.repos import audit as audit_repo

    admin = await _db_admin()
    msg = MagicMock()
    msg.text = "reply"
    msg.message_id = 5
    msg.answer = AsyncMock()
    bot = AsyncMock()
    state = _state({"reply_ticket_id": ticket.id})
    await tickets_mod.st_reply(msg, state, bot, user=admin, lang="ru")

    async with get_conn() as conn:
        rows = await audit_repo.list_recent(conn, limit=10)
    assert any(r.action == "ticket.reply" and r.target_id == ticket.id for r in rows)
