"""Tests for :mod:`app.db.repos.tickets`."""

from __future__ import annotations

from app.db.repos import tickets as tickets_repo


async def test_create_ticket(db_conn, make_user):
    user = await make_user(db_conn, tg_id=10)
    ticket = await tickets_repo.create_ticket(db_conn, user.id)
    assert ticket.user_id == user.id
    assert ticket.status == "open"
    assert ticket.created_at and ticket.updated_at


async def test_add_message_and_list(db_conn, make_user):
    user = await make_user(db_conn, tg_id=10)
    ticket = await tickets_repo.create_ticket(db_conn, user.id)
    m1 = await tickets_repo.add_message(
        db_conn, ticket.id, "user", "hello", tg_message_id=99
    )
    m2 = await tickets_repo.add_message(db_conn, ticket.id, "admin", "hi back")
    assert m1.sender == "user" and m1.tg_message_id == 99
    assert m2.sender == "admin" and m2.tg_message_id is None
    msgs = await tickets_repo.list_messages(db_conn, ticket.id)
    assert [m.text for m in msgs] == ["hello", "hi back"]


async def test_get_returns_none_for_missing(db_conn):
    assert await tickets_repo.get(db_conn, 999) is None


async def test_set_status_transitions(db_conn, make_user):
    user = await make_user(db_conn, tg_id=10)
    ticket = await tickets_repo.create_ticket(db_conn, user.id)
    await tickets_repo.set_status(db_conn, ticket.id, "answered")
    refreshed = await tickets_repo.get(db_conn, ticket.id)
    assert refreshed is not None and refreshed.status == "answered"
    await tickets_repo.set_status(db_conn, ticket.id, "closed")
    refreshed = await tickets_repo.get(db_conn, ticket.id)
    assert refreshed.status == "closed"


async def test_list_open_excludes_closed(db_conn, make_user):
    user = await make_user(db_conn, tg_id=10)
    t1 = await tickets_repo.create_ticket(db_conn, user.id)
    t2 = await tickets_repo.create_ticket(db_conn, user.id)
    await tickets_repo.set_status(db_conn, t2.id, "answered")
    await tickets_repo.set_status(db_conn, t1.id, "closed")
    open_tickets = await tickets_repo.list_open(db_conn)
    ids = {t.id for t in open_tickets}
    assert t2.id in ids
    assert t1.id not in ids


async def test_list_open_ordered_by_recency(db_conn, make_user):
    user = await make_user(db_conn, tg_id=10)
    t1 = await tickets_repo.create_ticket(db_conn, user.id)
    t2 = await tickets_repo.create_ticket(db_conn, user.id)
    # Touch t1 so it becomes the most-recently-updated.
    await tickets_repo.add_message(db_conn, t1.id, "user", "newer")
    open_tickets = await tickets_repo.list_open(db_conn)
    assert open_tickets[0].id == t1.id
    assert t2.id in {t.id for t in open_tickets}


async def test_list_for_user(db_conn, make_user):
    a = await make_user(db_conn, tg_id=10, username="a")
    b = await make_user(db_conn, tg_id=20, username="b")
    ta1 = await tickets_repo.create_ticket(db_conn, a.id)
    ta2 = await tickets_repo.create_ticket(db_conn, a.id)
    await tickets_repo.create_ticket(db_conn, b.id)
    for_a = await tickets_repo.list_for_user(db_conn, a.id)
    assert {t.id for t in for_a} == {ta1.id, ta2.id}
    # newest first
    assert for_a[0].id == ta2.id


async def test_get_open_for_user(db_conn, make_user):
    user = await make_user(db_conn, tg_id=10)
    assert await tickets_repo.get_open_for_user(db_conn, user.id) is None
    t1 = await tickets_repo.create_ticket(db_conn, user.id)
    found = await tickets_repo.get_open_for_user(db_conn, user.id)
    assert found is not None and found.id == t1.id
    await tickets_repo.set_status(db_conn, t1.id, "closed")
    assert await tickets_repo.get_open_for_user(db_conn, user.id) is None
