"""Tests for :func:`app.db.repos.plans.set_inbounds` /
:func:`app.db.repos.plans.get_inbounds` and the ``plan_inbounds`` many-to-many
table.

Covered behaviour:

* :func:`set_inbounds` with an empty iterable raises :class:`ValueError`
  (a plan must have at least one inbound to be usable in the buy flow).
* :func:`set_inbounds` followed by :func:`get_inbounds` returns the same
  ids, sorted ascending.
* A second :func:`set_inbounds` call replaces the previous set atomically
  — no leftover rows from the first call.
* Duplicate ids in the input to :func:`set_inbounds` are deduplicated.
* :func:`get_inbounds` for a non-existent ``plan_id`` returns ``[]``.
* Hard-deleting a plan cascades into ``plan_inbounds`` (FK ``ON DELETE
  CASCADE``) so no orphan rows remain.
"""

from __future__ import annotations

import pytest

from app.db.repos import plans as plans_repo


async def test_set_inbounds_empty_raises(db_conn, make_plan):
    """An empty iterable is rejected — plans must have at least one inbound."""
    plan = await make_plan(db_conn)
    with pytest.raises(ValueError):
        await plans_repo.set_inbounds(db_conn, plan.id, [])


async def test_set_then_get_inbounds_sorted(db_conn, make_plan):
    """`get_inbounds` returns the same ids set via `set_inbounds`, ascending."""
    plan = await make_plan(db_conn)
    await plans_repo.set_inbounds(db_conn, plan.id, [3, 1, 2])
    got = await plans_repo.get_inbounds(db_conn, plan.id)
    assert got == [1, 2, 3]


async def test_set_inbounds_replaces_previous(db_conn, make_plan):
    """A second `set_inbounds` call replaces, not appends."""
    plan = await make_plan(db_conn)
    await plans_repo.set_inbounds(db_conn, plan.id, [1, 2])
    await plans_repo.set_inbounds(db_conn, plan.id, [3, 4])
    got = await plans_repo.get_inbounds(db_conn, plan.id)
    assert got == [3, 4]


async def test_set_inbounds_dedups_input(db_conn, make_plan):
    """Duplicate ids in the input are deduplicated before insert."""
    plan = await make_plan(db_conn)
    await plans_repo.set_inbounds(db_conn, plan.id, [1, 1, 2, 2, 2])
    got = await plans_repo.get_inbounds(db_conn, plan.id)
    assert got == [1, 2]


async def test_get_inbounds_missing_plan_returns_empty(db_conn):
    """`get_inbounds` for a non-existent plan id returns an empty list."""
    got = await plans_repo.get_inbounds(db_conn, 999999)
    assert got == []


async def test_cascade_on_plan_delete(db_conn, make_plan):
    """Hard-deleting a plan removes its `plan_inbounds` rows via CASCADE."""
    plan = await make_plan(db_conn)
    await plans_repo.set_inbounds(db_conn, plan.id, [1, 2, 3])
    pre = await plans_repo.get_inbounds(db_conn, plan.id)
    assert pre == [1, 2, 3]

    await db_conn.execute("DELETE FROM plans WHERE id = ?", (plan.id,))
    await db_conn.commit()

    # `get_inbounds` against the freshly-deleted plan id must come back
    # empty — the row from `plan_inbounds` was cascaded away.
    after = await plans_repo.get_inbounds(db_conn, plan.id)
    assert after == []

    # Defence-in-depth: explicitly count rows in `plan_inbounds`. We do
    # not rely on the existence of any other rows here, so the table
    # should be empty after the cascade.
    cur = await db_conn.execute("SELECT COUNT(*) FROM plan_inbounds")
    (count,) = await cur.fetchone()
    assert count == 0


async def test_set_inbounds_is_atomic_on_replace(db_conn, make_plan):
    """The DELETE+INSERT pair is committed as a single unit.

    We cannot easily inject a failure between DELETE and INSERT without
    monkeypatching, but we can at least assert that after a successful
    replacement no row from the previous set survives.
    """
    plan = await make_plan(db_conn)
    await plans_repo.set_inbounds(db_conn, plan.id, [10, 20, 30])
    await plans_repo.set_inbounds(db_conn, plan.id, [40])
    got = await plans_repo.get_inbounds(db_conn, plan.id)
    assert got == [40]
    # Sanity: row count matches.
    cur = await db_conn.execute(
        "SELECT COUNT(*) FROM plan_inbounds WHERE plan_id = ?", (plan.id,)
    )
    (n,) = await cur.fetchone()
    assert n == 1
