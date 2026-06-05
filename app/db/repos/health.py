"""Repository for the ``health_status`` table — last-known panel reachability.

The bot probes the 3x-ui panel on a schedule (see
:func:`app.scheduler.health_check_job`). To avoid spamming admins on every
probe, the job must remember the *previous* state across runs and only alert on
an up↔down transition. This module persists that single logical row.

One row per ``component`` (currently only ``'xui'``). ``status`` is ``'up'`` or
``'down'``; ``last_error`` carries the most recent failure reason (``NULL`` when
up); ``changed_at`` records when the state last *flipped* (not every probe).

The two public helpers are:

* :func:`get` — read the current state (``None`` before the first probe).
* :func:`record` — upsert the state and report whether it *changed*. Callers use
  the returned ``changed`` flag to decide whether to alert.

All functions are ``async``, accept a caller-owned :class:`aiosqlite.Connection`
and commit their own writes (same DI pattern as the other repos).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import aiosqlite

HealthState = Literal["up", "down"]

# The only component tracked today. Kept as a constant so callers don't sprinkle
# the magic string; a second panel/component would just pass its own name.
DEFAULT_COMPONENT = "xui"


@dataclass(slots=True, frozen=True)
class HealthRow:
    """A row from the ``health_status`` table."""

    id: int
    component: str
    status: HealthState
    last_error: str | None
    changed_at: str

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> HealthRow:
        """Build a :class:`HealthRow` from an :class:`aiosqlite.Row`."""
        return cls(
            id=row["id"],
            component=row["component"],
            status=row["status"],
            last_error=row["last_error"],
            changed_at=row["changed_at"],
        )


_SELECT = (
    "SELECT id, component, status, last_error, changed_at "
    "FROM health_status"
)


async def get(
    conn: aiosqlite.Connection, component: str = DEFAULT_COMPONENT
) -> HealthRow | None:
    """Return the current health row for ``component`` (``None`` if never set)."""
    cursor = await conn.execute(
        f"{_SELECT} WHERE component = ?", (component,)
    )
    row = await cursor.fetchone()
    return HealthRow.from_row(row) if row else None


async def record(
    conn: aiosqlite.Connection,
    *,
    status: HealthState,
    last_error: str | None = None,
    component: str = DEFAULT_COMPONENT,
) -> tuple[HealthRow, bool]:
    """Upsert the health row and report whether the state *changed*.

    Returns ``(row, changed)`` where ``changed`` is ``True`` when this probe
    flipped the persisted ``status`` (including the very first probe, which has
    no prior state to compare against). ``changed_at`` is bumped to
    ``CURRENT_TIMESTAMP`` only on a real flip — a steady-state probe keeps the
    original transition timestamp so admins can see *how long* the component has
    been in its current state.

    Callers (the health-check job) alert admins exactly when ``changed`` is
    ``True``, which guarantees one notification per transition and no spam.
    """
    previous = await get(conn, component)
    changed = previous is None or previous.status != status

    if previous is None:
        await conn.execute(
            "INSERT INTO health_status (component, status, last_error) "
            "VALUES (?, ?, ?)",
            (component, status, last_error),
        )
    elif changed:
        await conn.execute(
            "UPDATE health_status "
            "SET status = ?, last_error = ?, changed_at = CURRENT_TIMESTAMP "
            "WHERE component = ?",
            (status, last_error, component),
        )
    else:
        # Steady state — keep ``changed_at`` but refresh ``last_error`` so the
        # latest failure reason (or its clearing) is always current.
        await conn.execute(
            "UPDATE health_status SET last_error = ? WHERE component = ?",
            (last_error, component),
        )
    await conn.commit()

    fetched = await get(conn, component)
    assert fetched is not None
    return fetched, changed


__all__ = ["DEFAULT_COMPONENT", "HealthRow", "HealthState", "get", "record"]
