"""Repository for the ``audit_log`` table — the admin-action trail.

Every privileged admin mutation (plan / promo CRUD, user revoke / toggle_admin /
grant_sub / block, broadcast) appends one append-only row here so the «📜 Аудит»
screen can reconstruct *who did what, to which entity, when*.

``action`` is a short dotted verb (e.g. ``'plan.create'``, ``'user.block'``);
``target_type`` / ``target_id`` identify the affected entity (nullable for
actions with no single target, e.g. a broadcast); ``details`` is an optional
free-form string (callers serialise JSON into it). ``admin_id`` is the acting
admin's ``users.id`` (nullable / SET NULL on delete so the trail survives an
admin account removal).

All functions are ``async``, accept a caller-owned :class:`aiosqlite.Connection`
and commit their own writes.
"""

from __future__ import annotations

from dataclasses import dataclass

import aiosqlite


@dataclass(slots=True, frozen=True)
class AuditEntry:
    """A row from the ``audit_log`` table."""

    id: int
    admin_id: int | None
    action: str
    target_type: str | None
    target_id: int | None
    details: str | None
    created_at: str

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> AuditEntry:
        """Build an :class:`AuditEntry` from an :class:`aiosqlite.Row`."""
        return cls(
            id=row["id"],
            admin_id=row["admin_id"],
            action=row["action"],
            target_type=row["target_type"],
            target_id=row["target_id"],
            details=row["details"],
            created_at=row["created_at"],
        )


_SELECT = (
    "SELECT id, admin_id, action, target_type, target_id, details, created_at "
    "FROM audit_log"
)


async def add(
    conn: aiosqlite.Connection,
    *,
    admin_id: int | None,
    action: str,
    target_type: str | None = None,
    target_id: int | None = None,
    details: str | None = None,
) -> AuditEntry:
    """Append an audit entry and return it. Commits immediately."""
    cursor = await conn.execute(
        "INSERT INTO audit_log "
        "(admin_id, action, target_type, target_id, details) "
        "VALUES (?, ?, ?, ?, ?)",
        (admin_id, action, target_type, target_id, details),
    )
    await conn.commit()
    new_id = cursor.lastrowid
    assert new_id is not None
    fetched = await get(conn, new_id)
    assert fetched is not None
    return fetched


async def get(conn: aiosqlite.Connection, entry_id: int) -> AuditEntry | None:
    """Fetch an audit entry by primary key. Returns ``None`` if not found."""
    cursor = await conn.execute(f"{_SELECT} WHERE id = ?", (entry_id,))
    row = await cursor.fetchone()
    return AuditEntry.from_row(row) if row else None


async def list_recent(
    conn: aiosqlite.Connection, *, limit: int = 20, offset: int = 0
) -> list[AuditEntry]:
    """Return the most recent audit entries, newest first.

    ``limit`` / ``offset`` page the trail for the «📜 Аудит» screen.
    """
    cursor = await conn.execute(
        f"{_SELECT} ORDER BY id DESC LIMIT ? OFFSET ?",
        (int(limit), int(offset)),
    )
    rows = await cursor.fetchall()
    return [AuditEntry.from_row(r) for r in rows]


async def count(conn: aiosqlite.Connection) -> int:
    """Return the total number of audit entries."""
    cursor = await conn.execute("SELECT COUNT(*) AS n FROM audit_log")
    row = await cursor.fetchone()
    assert row is not None
    return int(row["n"])


__all__ = ["AuditEntry", "add", "count", "get", "list_recent"]
