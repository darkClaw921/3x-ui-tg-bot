"""Repository for ``promos`` and ``promo_redemptions``.

Two design points worth noting:

* :func:`try_redeem` is the only place where ``used_count`` is incremented.
  It runs inside a ``BEGIN IMMEDIATE`` transaction (provided by
  :func:`app.db.engine.transaction`) so two concurrent redemptions of the
  same promo cannot both succeed when ``used_count`` is about to hit
  ``max_uses``.
* ``get_by_code`` is case-insensitive because users type codes in any case
  — ``code COLLATE NOCASE`` lets the existing UNIQUE index serve both writes
  and reads without an extra functional index.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import aiosqlite

from app.db.engine import transaction

PromoType = Literal["percent", "flat_stars", "free_days"]


@dataclass(slots=True, frozen=True)
class Promo:
    """A row from the ``promos`` table."""

    id: int
    code: str
    type: PromoType
    value: int
    max_uses: int
    used_count: int
    expires_at: str | None
    created_at: str
    created_by: int | None

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> Promo:
        """Build a :class:`Promo` from an :class:`aiosqlite.Row`."""
        return cls(
            id=row["id"],
            code=row["code"],
            type=row["type"],
            value=row["value"],
            max_uses=row["max_uses"],
            used_count=row["used_count"],
            expires_at=row["expires_at"],
            created_at=row["created_at"],
            created_by=row["created_by"],
        )


@dataclass(slots=True, frozen=True)
class Redemption:
    """A row from the ``promo_redemptions`` table."""

    id: int
    promo_id: int
    user_id: int
    subscription_id: int | None
    redeemed_at: str

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> Redemption:
        """Build a :class:`Redemption` from an :class:`aiosqlite.Row`."""
        return cls(
            id=row["id"],
            promo_id=row["promo_id"],
            user_id=row["user_id"],
            subscription_id=row["subscription_id"],
            redeemed_at=row["redeemed_at"],
        )


def _utcnow_iso() -> str:
    """Return current UTC time in ISO-8601 (seconds resolution)."""
    return datetime.now(UTC).replace(microsecond=0).isoformat(sep=" ")


async def create(
    conn: aiosqlite.Connection,
    code: str,
    type: PromoType,
    value: int,
    max_uses: int,
    expires_at: str | None,
    created_by: int | None,
) -> Promo:
    """Insert a new promo and return the resulting :class:`Promo`.

    ``code`` is stored as-is. Use :func:`get_by_code` (case-insensitive) for
    lookups. Raises :class:`aiosqlite.IntegrityError` if the code is taken or
    ``type`` is invalid (CHECK constraint).
    """
    cursor = await conn.execute(
        "INSERT INTO promos "
        "(code, type, value, max_uses, used_count, expires_at, created_by) "
        "VALUES (?, ?, ?, ?, 0, ?, ?)",
        (code, type, value, max_uses, expires_at, created_by),
    )
    await conn.commit()
    new_id = cursor.lastrowid
    assert new_id is not None
    promo = await get(conn, new_id)
    assert promo is not None
    return promo


async def get(conn: aiosqlite.Connection, promo_id: int) -> Promo | None:
    """Fetch a promo by primary key. Returns ``None`` if not found."""
    cursor = await conn.execute(
        "SELECT id, code, type, value, max_uses, used_count, "
        "expires_at, created_at, created_by "
        "FROM promos WHERE id = ?",
        (promo_id,),
    )
    row = await cursor.fetchone()
    return Promo.from_row(row) if row else None


async def get_by_code(conn: aiosqlite.Connection, code: str) -> Promo | None:
    """Case-insensitive lookup by ``code``. Returns ``None`` if not found."""
    cursor = await conn.execute(
        "SELECT id, code, type, value, max_uses, used_count, "
        "expires_at, created_at, created_by "
        "FROM promos WHERE code = ? COLLATE NOCASE",
        (code,),
    )
    row = await cursor.fetchone()
    return Promo.from_row(row) if row else None


async def list_active(conn: aiosqlite.Connection) -> list[Promo]:
    """Return all currently-active promos.

    A promo is active when:

    * ``expires_at`` is ``NULL`` or in the future, AND
    * ``max_uses = 0`` (unlimited) or ``used_count < max_uses``.
    """
    now = _utcnow_iso()
    cursor = await conn.execute(
        "SELECT id, code, type, value, max_uses, used_count, "
        "expires_at, created_at, created_by "
        "FROM promos "
        "WHERE (expires_at IS NULL OR expires_at > ?) "
        "  AND (max_uses = 0 OR used_count < max_uses) "
        "ORDER BY created_at DESC, id DESC",
        (now,),
    )
    rows = await cursor.fetchall()
    return [Promo.from_row(r) for r in rows]


async def deactivate(conn: aiosqlite.Connection, promo_id: int) -> None:
    """Soft-disable a promo by setting ``expires_at = now`` (in the past).

    Subsequent :func:`get_by_code` calls still find it, but
    :func:`list_active` and :func:`try_redeem` treat it as expired.
    """
    await conn.execute(
        "UPDATE promos SET expires_at = ? WHERE id = ?",
        (_utcnow_iso(), promo_id),
    )
    await conn.commit()


async def try_redeem(
    conn: aiosqlite.Connection,
    promo_id: int,
    user_id: int,
    subscription_id: int | None,
) -> bool:
    """Attempt to atomically redeem a promo.

    Inside a ``BEGIN IMMEDIATE`` block:

    1. SELECT promo and re-validate (not expired, capacity available).
    2. UPDATE ``used_count = used_count + 1`` (with a guard on the WHERE
       clause so concurrent attempts that race past the limit fail).
    3. INSERT a row into ``promo_redemptions``.

    Returns ``True`` on success, ``False`` if the promo became invalid (or
    raced against another redemption). Never raises on validation failure;
    other exceptions roll the transaction back and re-raise.
    """
    now = _utcnow_iso()
    async with transaction(conn):
        cursor = await conn.execute(
            "SELECT id, max_uses, used_count, expires_at "
            "FROM promos WHERE id = ?",
            (promo_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return False
        if row["expires_at"] is not None and row["expires_at"] <= now:
            return False
        if row["max_uses"] != 0 and row["used_count"] >= row["max_uses"]:
            return False

        # Capacity-guarded UPDATE: even if two transactions get to this
        # point simultaneously, only one can satisfy the predicate.
        update_cursor = await conn.execute(
            "UPDATE promos "
            "SET used_count = used_count + 1 "
            "WHERE id = ? "
            "  AND (max_uses = 0 OR used_count < max_uses) "
            "  AND (expires_at IS NULL OR expires_at > ?)",
            (promo_id, now),
        )
        if update_cursor.rowcount != 1:
            return False

        await conn.execute(
            "INSERT INTO promo_redemptions (promo_id, user_id, subscription_id) "
            "VALUES (?, ?, ?)",
            (promo_id, user_id, subscription_id),
        )
    return True


async def list_redemptions(
    conn: aiosqlite.Connection, promo_id: int
) -> list[Redemption]:
    """Return all redemptions for ``promo_id``, newest first."""
    cursor = await conn.execute(
        "SELECT id, promo_id, user_id, subscription_id, redeemed_at "
        "FROM promo_redemptions "
        "WHERE promo_id = ? "
        "ORDER BY redeemed_at DESC, id DESC",
        (promo_id,),
    )
    rows = await cursor.fetchall()
    return [Redemption.from_row(r) for r in rows]
