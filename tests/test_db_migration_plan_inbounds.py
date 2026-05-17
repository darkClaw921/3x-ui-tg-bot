"""Tests for the ``plan_inbounds`` backfill in :func:`app.db.engine.init_db`.

Behaviour under test:

* Old databases (rows in ``plans`` but no rows in ``plan_inbounds``) get
  a single entry per plan pointing at :attr:`settings.XUI_INBOUND_ID`
  after the first ``init_db()`` call.
* The backfill is idempotent at the per-plan level: running ``init_db``
  twice does NOT overwrite an admin-customised inbound set.
* The backfill targets ONLY plans without rows in ``plan_inbounds`` —
  plans that already have an admin-defined inbound set are left alone
  even when a different plan in the same DB needs backfilling.
* When :attr:`settings.XUI_INBOUND_ID` is falsy (``0`` or missing) the
  backfill is skipped without crashing — the install is misconfigured
  but startup must still proceed.
"""

from __future__ import annotations

import aiosqlite
import pytest

from app.db.engine import init_db
from app.db.repos import plans as plans_repo


@pytest.fixture
async def fresh_db(tmp_path, monkeypatch):
    """Yield a file-backed empty DB path with settings.DB_PATH pointed at it.

    Unlike :func:`tests.conftest.file_db`, this fixture does NOT initialise
    the schema — that's the unit under test. The caller is expected to
    invoke :func:`init_db` (and may pre-seed plans/inbounds first).
    """
    from app.config import settings

    db_path = tmp_path / "migration.db"
    monkeypatch.setattr(settings, "DB_PATH", str(db_path), raising=False)
    return db_path


async def _seed_legacy_plan(db_path, *, title: str = "legacy") -> int:
    """Create the minimal `plans` table and one plan, no `plan_inbounds`.

    Simulates the on-disk state of an old install that pre-dates the
    multi-inbound feature.
    """
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plans (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                title        TEXT NOT NULL,
                days         INTEGER NOT NULL,
                price_stars  INTEGER NOT NULL,
                is_active    INTEGER NOT NULL DEFAULT 1,
                created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur = await conn.execute(
            "INSERT INTO plans (title, days, price_stars, is_active) VALUES (?, ?, ?, 1)",
            (title, 30, 100),
        )
        await conn.commit()
        return cur.lastrowid


async def test_backfill_inserts_default_inbound(fresh_db, monkey_settings):
    """Old DB without `plan_inbounds` → each plan gets XUI_INBOUND_ID after init_db."""
    monkey_settings(XUI_INBOUND_ID=7)
    plan_id = await _seed_legacy_plan(fresh_db, title="legacy-1")

    await init_db()

    async with aiosqlite.connect(fresh_db) as conn:
        conn.row_factory = aiosqlite.Row
        got = await plans_repo.get_inbounds(conn, plan_id)
    assert got == [7]


async def test_backfill_idempotent_preserves_admin_choice(fresh_db, monkey_settings):
    """`init_db` does NOT overwrite an admin-defined inbound set on re-run."""
    monkey_settings(XUI_INBOUND_ID=1)
    plan_id = await _seed_legacy_plan(fresh_db, title="custom")

    # First init creates schema + backfills with id=1.
    await init_db()
    async with aiosqlite.connect(fresh_db) as conn:
        conn.row_factory = aiosqlite.Row
        await plans_repo.set_inbounds(conn, plan_id, [10, 20])

    # Run init_db again — backfill must not touch a plan that already has rows.
    await init_db()

    async with aiosqlite.connect(fresh_db) as conn:
        conn.row_factory = aiosqlite.Row
        got = await plans_repo.get_inbounds(conn, plan_id)
    assert got == [10, 20]


async def test_backfill_only_targets_plans_without_rows(fresh_db, monkey_settings):
    """A plan with an admin set is kept; a plan without one gets the default."""
    monkey_settings(XUI_INBOUND_ID=5)

    # Seed two legacy plans.
    plan_with_set = await _seed_legacy_plan(fresh_db, title="has-set")
    plan_without = await _seed_legacy_plan(fresh_db, title="missing")

    # First init creates the schema and backfills BOTH (since neither had
    # any rows yet) — then we deliberately mutate one to a custom set.
    await init_db()
    async with aiosqlite.connect(fresh_db) as conn:
        conn.row_factory = aiosqlite.Row
        await plans_repo.set_inbounds(conn, plan_with_set, [99])
        # Drop the second plan's rows to simulate a half-migrated state
        # (e.g. a plan added between two `init_db` calls without an
        # explicit `set_inbounds`).
        await conn.execute(
            "DELETE FROM plan_inbounds WHERE plan_id = ?", (plan_without,)
        )
        await conn.commit()

    # Second init: should backfill the second plan (no rows) and leave
    # the first plan's [99] alone.
    await init_db()

    async with aiosqlite.connect(fresh_db) as conn:
        conn.row_factory = aiosqlite.Row
        kept = await plans_repo.get_inbounds(conn, plan_with_set)
        filled = await plans_repo.get_inbounds(conn, plan_without)
    assert kept == [99]
    assert filled == [5]


async def test_backfill_skipped_when_default_missing(fresh_db, monkey_settings):
    """If XUI_INBOUND_ID is 0/missing the backfill is a no-op (no crash)."""
    monkey_settings(XUI_INBOUND_ID=0)
    plan_id = await _seed_legacy_plan(fresh_db, title="no-default")

    # Must not raise.
    await init_db()

    async with aiosqlite.connect(fresh_db) as conn:
        conn.row_factory = aiosqlite.Row
        got = await plans_repo.get_inbounds(conn, plan_id)
    # No backfill happened — plan still has no inbounds.
    assert got == []
