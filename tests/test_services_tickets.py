"""Tests for :mod:`app.services.tickets` — the ticket status machine."""

from __future__ import annotations

from app.db.repos import tickets as tickets_repo
from app.services import tickets as tickets_service


async def test_open_ticket_creates_and_records(db_conn, make_user):
    user = await make_user(db_conn, tg_id=10)
    ticket, message = await tickets_service.open_ticket(
        db_conn, user, "help me", tg_message_id=7
    )
    assert ticket.status == "open"
    assert message.sender == "user" and message.text == "help me"
    assert message.tg_message_id == 7


async def test_open_ticket_reuses_existing_open(db_conn, make_user):
    user = await make_user(db_conn, tg_id=10)
    t1, _ = await tickets_service.open_ticket(db_conn, user, "first")
    t2, _ = await tickets_service.open_ticket(db_conn, user, "second")
    assert t1.id == t2.id
    msgs = await tickets_repo.list_messages(db_conn, t1.id)
    assert [m.text for m in msgs] == ["first", "second"]


async def test_open_ticket_resets_answered_to_open(db_conn, make_user):
    user = await make_user(db_conn, tg_id=10)
    t1, _ = await tickets_service.open_ticket(db_conn, user, "first")
    await tickets_service.reply_admin(db_conn, t1.id, "answer")
    answered = await tickets_repo.get(db_conn, t1.id)
    assert answered.status == "answered"
    # user follows up → reuse + back to open
    t2, _ = await tickets_service.open_ticket(db_conn, user, "thanks")
    assert t2.id == t1.id and t2.status == "open"


async def test_open_ticket_after_close_creates_new(db_conn, make_user):
    user = await make_user(db_conn, tg_id=10)
    t1, _ = await tickets_service.open_ticket(db_conn, user, "first")
    await tickets_service.close_ticket(db_conn, t1.id)
    t2, _ = await tickets_service.open_ticket(db_conn, user, "new issue")
    assert t2.id != t1.id and t2.status == "open"


async def test_reply_admin_sets_answered(db_conn, make_user):
    user = await make_user(db_conn, tg_id=10)
    t1, _ = await tickets_service.open_ticket(db_conn, user, "q")
    msg = await tickets_service.reply_admin(db_conn, t1.id, "a", tg_message_id=3)
    assert msg.sender == "admin" and msg.tg_message_id == 3
    refreshed = await tickets_repo.get(db_conn, t1.id)
    assert refreshed.status == "answered"


async def test_reply_user_sets_open(db_conn, make_user):
    user = await make_user(db_conn, tg_id=10)
    t1, _ = await tickets_service.open_ticket(db_conn, user, "q")
    await tickets_service.reply_admin(db_conn, t1.id, "a")
    msg = await tickets_service.reply_user(db_conn, t1.id, "more")
    assert msg.sender == "user"
    refreshed = await tickets_repo.get(db_conn, t1.id)
    assert refreshed.status == "open"


async def test_close_ticket_idempotent(db_conn, make_user):
    user = await make_user(db_conn, tg_id=10)
    t1, _ = await tickets_service.open_ticket(db_conn, user, "q")
    await tickets_service.close_ticket(db_conn, t1.id)
    await tickets_service.close_ticket(db_conn, t1.id)
    refreshed = await tickets_repo.get(db_conn, t1.id)
    assert refreshed.status == "closed"
