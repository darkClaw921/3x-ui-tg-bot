"""Tests for :mod:`app.db.repos.wallet` — the append-only Stars ledger."""

from __future__ import annotations

from app.db.repos import wallet as wallet_repo


async def test_balance_zero_for_unknown_user(db_conn, make_user):
    user = await make_user(db_conn)
    assert await wallet_repo.balance(db_conn, user.id) == 0


async def test_add_returns_txn_and_balance_sums(db_conn, make_user):
    user = await make_user(db_conn)
    t1 = await wallet_repo.add(
        db_conn, user_id=user.id, type="topup", amount=100, ref="topup:c1"
    )
    assert t1 is not None
    assert t1.id > 0
    assert t1.amount == 100
    assert t1.type == "topup"
    assert t1.ref == "topup:c1"

    await wallet_repo.add(db_conn, user_id=user.id, type="spend", amount=-30, ref="buy:1")
    assert await wallet_repo.balance(db_conn, user.id) == 70


async def test_add_duplicate_ref_returns_none_and_no_balance_change(db_conn, make_user):
    user = await make_user(db_conn)
    first = await wallet_repo.add(
        db_conn, user_id=user.id, type="topup", amount=100, ref="topup:dup"
    )
    assert first is not None
    dup = await wallet_repo.add(
        db_conn, user_id=user.id, type="topup", amount=999, ref="topup:dup"
    )
    assert dup is None
    # Balance reflects only the first insert — the duplicate did nothing.
    assert await wallet_repo.balance(db_conn, user.id) == 100


async def test_add_null_ref_allows_multiple_rows(db_conn, make_user):
    user = await make_user(db_conn)
    a = await wallet_repo.add(db_conn, user_id=user.id, type="admin_grant", amount=5)
    b = await wallet_repo.add(db_conn, user_id=user.id, type="admin_grant", amount=5)
    assert a is not None and b is not None
    assert a.id != b.id
    assert await wallet_repo.balance(db_conn, user.id) == 10


async def test_balance_is_per_user(db_conn, make_user):
    u1 = await make_user(db_conn, tg_id=1)
    u2 = await make_user(db_conn, tg_id=2)
    await wallet_repo.add(db_conn, user_id=u1.id, type="topup", amount=100, ref="t:1")
    await wallet_repo.add(db_conn, user_id=u2.id, type="topup", amount=40, ref="t:2")
    assert await wallet_repo.balance(db_conn, u1.id) == 100
    assert await wallet_repo.balance(db_conn, u2.id) == 40


async def test_list_for_user_orders_newest_first_and_limits(db_conn, make_user):
    user = await make_user(db_conn)
    for i in range(5):
        await wallet_repo.add(
            db_conn, user_id=user.id, type="topup", amount=10, ref=f"t:{i}"
        )
    rows = await wallet_repo.list_for_user(db_conn, user.id, limit=3)
    assert len(rows) == 3
    # id DESC tie-break → highest id (most recent insert) first.
    assert rows[0].id > rows[1].id > rows[2].id


async def test_list_for_user_only_returns_own_rows(db_conn, make_user):
    u1 = await make_user(db_conn, tg_id=1)
    u2 = await make_user(db_conn, tg_id=2)
    await wallet_repo.add(db_conn, user_id=u1.id, type="topup", amount=10, ref="a")
    await wallet_repo.add(db_conn, user_id=u2.id, type="topup", amount=20, ref="b")
    rows = await wallet_repo.list_for_user(db_conn, u1.id)
    assert len(rows) == 1
    assert rows[0].user_id == u1.id


async def test_get_by_ref(db_conn, make_user):
    user = await make_user(db_conn)
    txn = await wallet_repo.add(
        db_conn, user_id=user.id, type="spend", amount=-25, ref="buy:42"
    )
    assert txn is not None
    found = await wallet_repo.get_by_ref(db_conn, "buy:42")
    assert found is not None
    assert found.id == txn.id
    assert found.amount == -25
    assert await wallet_repo.get_by_ref(db_conn, "no:such:ref") is None
