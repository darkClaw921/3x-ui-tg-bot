"""Tests for :mod:`app.db.repos.audit`."""

from __future__ import annotations

from app.db.repos import audit as audit_repo


async def test_add_and_get(db_conn, make_user):
    admin = await make_user(db_conn, tg_id=1, is_admin=True)
    entry = await audit_repo.add(
        db_conn,
        admin_id=admin.id,
        action="plan.create",
        target_type="plan",
        target_id=5,
        details='{"title":"x"}',
    )
    assert entry.action == "plan.create"
    assert entry.target_type == "plan"
    assert entry.target_id == 5
    fetched = await audit_repo.get(db_conn, entry.id)
    assert fetched is not None and fetched.id == entry.id


async def test_add_nullable_fields(db_conn):
    entry = await audit_repo.add(
        db_conn, admin_id=None, action="broadcast.send"
    )
    assert entry.admin_id is None
    assert entry.target_type is None
    assert entry.target_id is None
    assert entry.details is None


async def test_get_missing_returns_none(db_conn):
    assert await audit_repo.get(db_conn, 999) is None


async def test_list_recent_newest_first_and_count(db_conn, make_user):
    admin = await make_user(db_conn, tg_id=1, is_admin=True)
    for i in range(5):
        await audit_repo.add(
            db_conn, admin_id=admin.id, action=f"a{i}", target_id=i
        )
    assert await audit_repo.count(db_conn) == 5
    recent = await audit_repo.list_recent(db_conn, limit=3)
    assert len(recent) == 3
    # newest first → last inserted action "a4"
    assert recent[0].action == "a4"


async def test_list_recent_pagination(db_conn, make_user):
    admin = await make_user(db_conn, tg_id=1, is_admin=True)
    for i in range(5):
        await audit_repo.add(db_conn, admin_id=admin.id, action=f"a{i}")
    page0 = await audit_repo.list_recent(db_conn, limit=2, offset=0)
    page1 = await audit_repo.list_recent(db_conn, limit=2, offset=2)
    assert {e.action for e in page0}.isdisjoint({e.action for e in page1})
