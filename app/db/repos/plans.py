"""Repository for the ``plans`` table (tariff plans).

Plans are soft-deleted via :func:`deactivate` (``is_active=0``) — payments and
subscriptions reference plans, so hard deletes would break history.

Functions accept an :class:`aiosqlite.Connection` and return either a
:class:`Plan` dataclass (or list / ``None``).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import aiosqlite

# Whitelist of columns that can be updated through :func:`update`. Anything
# outside this set is rejected to prevent SQL injection via dynamic column
# names.
_UPDATABLE_COLUMNS = frozenset({"title", "days", "price_stars", "traffic_gb", "is_active"})


@dataclass(slots=True, frozen=True)
class Plan:
    """A row from the ``plans`` table."""

    id: int
    title: str
    days: int
    price_stars: int
    traffic_gb: int
    is_active: bool
    created_at: str

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> Plan:
        """Build a :class:`Plan` from an :class:`aiosqlite.Row`."""
        return cls(
            id=row["id"],
            title=row["title"],
            days=row["days"],
            price_stars=row["price_stars"],
            traffic_gb=row["traffic_gb"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
        )


async def create(
    conn: aiosqlite.Connection,
    title: str,
    days: int,
    price_stars: int,
    traffic_gb: int = 0,
) -> Plan:
    """Insert a new active plan.

    ``traffic_gb`` declares the per-client traffic limit forwarded to the
    3x-ui panel as ``totalGB`` (0 means unlimited, matching xui semantics).
    """
    cursor = await conn.execute(
        "INSERT INTO plans (title, days, price_stars, traffic_gb, is_active) "
        "VALUES (?, ?, ?, ?, 1)",
        (title, days, price_stars, traffic_gb),
    )
    await conn.commit()
    new_id = cursor.lastrowid
    assert new_id is not None
    plan = await get(conn, new_id)
    assert plan is not None
    return plan


async def get(conn: aiosqlite.Connection, plan_id: int) -> Plan | None:
    """Fetch a plan by primary key. Returns ``None`` if not found."""
    cursor = await conn.execute(
        "SELECT id, title, days, price_stars, traffic_gb, is_active, created_at "
        "FROM plans WHERE id = ?",
        (plan_id,),
    )
    row = await cursor.fetchone()
    return Plan.from_row(row) if row else None


async def list_active(conn: aiosqlite.Connection) -> list[Plan]:
    """Return all plans where ``is_active=1``, sorted by price ascending."""
    cursor = await conn.execute(
        "SELECT id, title, days, price_stars, traffic_gb, is_active, created_at "
        "FROM plans WHERE is_active = 1 ORDER BY price_stars ASC, id ASC"
    )
    rows = await cursor.fetchall()
    return [Plan.from_row(r) for r in rows]


async def list_all(conn: aiosqlite.Connection) -> list[Plan]:
    """Return all plans (active and inactive), sorted by id."""
    cursor = await conn.execute(
        "SELECT id, title, days, price_stars, traffic_gb, is_active, created_at "
        "FROM plans ORDER BY id ASC"
    )
    rows = await cursor.fetchall()
    return [Plan.from_row(r) for r in rows]


async def update(conn: aiosqlite.Connection, plan_id: int, **fields: Any) -> Plan:
    """Patch one or more columns of a plan and return the fresh row.

    Only columns in :data:`_UPDATABLE_COLUMNS` (``title``, ``days``,
    ``price_stars``, ``traffic_gb``, ``is_active``) may be changed. Booleans
    are coerced to ``0``/``1`` for ``is_active``. Raises :class:`ValueError`
    on unknown columns or :class:`LookupError` if the plan does not exist.
    """
    if not fields:
        plan = await get(conn, plan_id)
        if plan is None:
            raise LookupError(f"plan {plan_id} not found")
        return plan

    unknown = set(fields) - _UPDATABLE_COLUMNS
    if unknown:
        raise ValueError(f"cannot update columns: {sorted(unknown)}")

    set_clauses = []
    values: list[Any] = []
    for col, raw in fields.items():
        value = (1 if raw else 0) if col == "is_active" else raw
        set_clauses.append(f"{col} = ?")
        values.append(value)
    values.append(plan_id)

    await conn.execute(
        f"UPDATE plans SET {', '.join(set_clauses)} WHERE id = ?",  # noqa: S608
        values,
    )
    await conn.commit()

    plan = await get(conn, plan_id)
    if plan is None:
        raise LookupError(f"plan {plan_id} not found")
    return plan


async def deactivate(conn: aiosqlite.Connection, plan_id: int) -> None:
    """Soft-disable a plan by setting ``is_active=0``.

    The row remains so that payments / subscriptions keep their FK reference.
    """
    await conn.execute(
        "UPDATE plans SET is_active = 0 WHERE id = ?",
        (plan_id,),
    )
    await conn.commit()


async def get_inbounds(conn: aiosqlite.Connection, plan_id: int) -> list[int]:
    """Return the 3x-ui inbound ids attached to ``plan_id``, sorted ascending.

    Returns an empty list when the plan has no rows in ``plan_inbounds`` (or
    when ``plan_id`` does not exist). The caller is expected to treat an empty
    list as a misconfigured plan — :func:`set_inbounds` guarantees that any
    plan touched through the API has at least one inbound.
    """
    cursor = await conn.execute(
        "SELECT inbound_id FROM plan_inbounds WHERE plan_id = ? ORDER BY inbound_id",
        (plan_id,),
    )
    rows = await cursor.fetchall()
    return [row["inbound_id"] for row in rows]


async def set_inbounds(
    conn: aiosqlite.Connection,
    plan_id: int,
    inbound_ids: Iterable[int],
) -> None:
    """Replace the set of inbounds attached to ``plan_id`` atomically.

    Strategy: ``DELETE FROM plan_inbounds WHERE plan_id=?`` followed by an
    ``executemany`` of the new rows, wrapped in a single transaction. Duplicate
    ids in the input are deduplicated via :class:`set` before insert.

    A plan must have **at least one** inbound to be usable in the buy flow —
    passing an empty iterable raises :class:`ValueError`. Callers that want to
    fully detach a plan from inbounds should soft-delete the plan instead.
    """
    unique_ids = set(inbound_ids)
    if not unique_ids:
        raise ValueError("plan must have at least one inbound")

    await conn.execute("BEGIN")
    try:
        await conn.execute(
            "DELETE FROM plan_inbounds WHERE plan_id = ?",
            (plan_id,),
        )
        await conn.executemany(
            "INSERT INTO plan_inbounds (plan_id, inbound_id) VALUES (?, ?)",
            [(plan_id, inbound_id) for inbound_id in unique_ids],
        )
    except BaseException:
        await conn.rollback()
        raise
    await conn.commit()
