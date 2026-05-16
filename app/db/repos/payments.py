"""Repository for the ``payments`` table.

Each row is a Stars-payment record produced from a ``successful_payment``
Telegram update. The ``telegram_charge_id`` column has a UNIQUE constraint
so the payment handler can stay idempotent: if Telegram retries the update,
``create`` raises :class:`aiosqlite.IntegrityError` and the caller falls
back to :func:`get_by_charge_id`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import aiosqlite

PaymentStatus = Literal["paid", "refunded"]


@dataclass(slots=True, frozen=True)
class Payment:
    """A row from the ``payments`` table."""

    id: int
    user_id: int
    subscription_id: int | None
    telegram_charge_id: str
    stars_amount: int
    plan_id: int | None
    promo_id: int | None
    status: PaymentStatus
    created_at: str

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> Payment:
        """Build a :class:`Payment` from an :class:`aiosqlite.Row`."""
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            subscription_id=row["subscription_id"],
            telegram_charge_id=row["telegram_charge_id"],
            stars_amount=row["stars_amount"],
            plan_id=row["plan_id"],
            promo_id=row["promo_id"],
            status=row["status"],
            created_at=row["created_at"],
        )


_SELECT = (
    "SELECT id, user_id, subscription_id, telegram_charge_id, stars_amount, "
    "plan_id, promo_id, status, created_at FROM payments"
)


async def create(
    conn: aiosqlite.Connection,
    user_id: int,
    subscription_id: int | None,
    telegram_charge_id: str,
    stars_amount: int,
    plan_id: int | None,
    promo_id: int | None,
    status: PaymentStatus = "paid",
) -> Payment:
    """Insert a payment record.

    Raises :class:`aiosqlite.IntegrityError` if ``telegram_charge_id`` is
    already present (UNIQUE constraint); the caller should treat this as
    a successful duplicate and call :func:`get_by_charge_id`.
    """
    cursor = await conn.execute(
        "INSERT INTO payments "
        "(user_id, subscription_id, telegram_charge_id, stars_amount, "
        " plan_id, promo_id, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            user_id,
            subscription_id,
            telegram_charge_id,
            stars_amount,
            plan_id,
            promo_id,
            status,
        ),
    )
    await conn.commit()
    new_id = cursor.lastrowid
    assert new_id is not None
    payment = await get(conn, new_id)
    assert payment is not None
    return payment


async def get(conn: aiosqlite.Connection, payment_id: int) -> Payment | None:
    """Fetch a payment by primary key. Returns ``None`` if not found."""
    cursor = await conn.execute(f"{_SELECT} WHERE id = ?", (payment_id,))
    row = await cursor.fetchone()
    return Payment.from_row(row) if row else None


async def get_by_charge_id(
    conn: aiosqlite.Connection, telegram_charge_id: str
) -> Payment | None:
    """Lookup a payment by Telegram's ``telegram_payment_charge_id``."""
    cursor = await conn.execute(
        f"{_SELECT} WHERE telegram_charge_id = ?",
        (telegram_charge_id,),
    )
    row = await cursor.fetchone()
    return Payment.from_row(row) if row else None


async def list_for_user(
    conn: aiosqlite.Connection, user_id: int
) -> list[Payment]:
    """Return all payments for ``user_id`` ordered by ``created_at DESC``."""
    cursor = await conn.execute(
        f"{_SELECT} WHERE user_id = ? "
        "ORDER BY created_at DESC, id DESC",
        (user_id,),
    )
    rows = await cursor.fetchall()
    return [Payment.from_row(r) for r in rows]


async def total_stars_period(
    conn: aiosqlite.Connection,
    start: datetime | str,
    end: datetime | str,
) -> int:
    """Sum ``stars_amount`` for ``status='paid'`` payments in ``[start, end]``.

    Both bounds are inclusive. Accepts either ISO-8601 strings or
    :class:`datetime.datetime` (converted to ISO-8601, UTC).
    """
    start_iso = _to_iso(start)
    end_iso = _to_iso(end)
    cursor = await conn.execute(
        "SELECT COALESCE(SUM(stars_amount), 0) AS total FROM payments "
        "WHERE status = 'paid' AND created_at >= ? AND created_at <= ?",
        (start_iso, end_iso),
    )
    row = await cursor.fetchone()
    assert row is not None
    return int(row["total"])


async def set_status(
    conn: aiosqlite.Connection,
    payment_id: int,
    status: PaymentStatus,
) -> None:
    """Update the ``status`` column for a payment."""
    await conn.execute(
        "UPDATE payments SET status = ? WHERE id = ?",
        (status, payment_id),
    )
    await conn.commit()


def _to_iso(value: datetime | str) -> str:
    """Normalize ``value`` to an ISO-8601 string in UTC."""
    if isinstance(value, datetime):
        from datetime import UTC

        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        else:
            value = value.astimezone(UTC)
        return value.replace(microsecond=0).isoformat(sep=" ")
    return value
