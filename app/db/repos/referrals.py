"""Repository for the ``referrals`` table — the invite-a-friend ledger.

Each referred user appears in exactly one row (``referred_id`` is UNIQUE),
recording who invited them (``referrer_id``) and whether the inviter's bonus
has been paid (``status`` is ``'pending'`` → ``'rewarded'``).

Two idempotency guarantees live in this module:

* :func:`create_pending` uses ``INSERT OR IGNORE`` against the
  ``UNIQUE(referred_id)`` constraint, so a user can be *bound* to a referrer
  exactly once — the very first ``/start?ref=…`` wins and every later attempt is
  a silent no-op (returns ``None``).
* :func:`try_mark_rewarded` flips ``status`` from ``'pending'`` to ``'rewarded'``
  with a guarded ``UPDATE … WHERE status='pending'``. Even two concurrent calls
  can satisfy that predicate only once, so the referral bonus is credited at
  most once per referred user.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import aiosqlite

ReferralStatus = Literal["pending", "rewarded"]


def _utcnow_iso() -> str:
    """Return current UTC time in ISO-8601 (seconds resolution)."""
    return datetime.now(UTC).replace(microsecond=0).isoformat(sep=" ")


@dataclass(slots=True, frozen=True)
class Referral:
    """A row from the ``referrals`` table."""

    id: int
    referrer_id: int
    referred_id: int
    status: ReferralStatus
    created_at: str
    rewarded_at: str | None

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> Referral:
        """Build a :class:`Referral` from an :class:`aiosqlite.Row`."""
        return cls(
            id=row["id"],
            referrer_id=row["referrer_id"],
            referred_id=row["referred_id"],
            status=row["status"],
            created_at=row["created_at"],
            rewarded_at=row["rewarded_at"],
        )


_SELECT = (
    "SELECT id, referrer_id, referred_id, status, created_at, rewarded_at "
    "FROM referrals"
)


async def create_pending(
    conn: aiosqlite.Connection,
    *,
    referrer_id: int,
    referred_id: int,
) -> Referral | None:
    """Bind ``referred_id`` to ``referrer_id`` with ``status='pending'``.

    Uses ``INSERT OR IGNORE`` so the binding happens exactly once: if the
    referred user already has a row (they followed a referral link before, or
    are being re-bound to a different referrer), the insert is ignored and this
    returns ``None``. On a fresh insert the created :class:`Referral` is
    returned.

    The caller (:func:`app.services.referrals.register_referral`) is responsible
    for the self-referral guard (``referrer_id != referred_id``) — this layer
    only enforces the one-referrer-per-user uniqueness.
    """
    cursor = await conn.execute(
        "INSERT OR IGNORE INTO referrals (referrer_id, referred_id, status) "
        "VALUES (?, ?, 'pending')",
        (referrer_id, referred_id),
    )
    await conn.commit()
    if cursor.rowcount != 1:
        # Row already existed for this referred_id — binding is a no-op.
        return None
    new_id = cursor.lastrowid
    assert new_id is not None
    created = await get(conn, new_id)
    assert created is not None
    return created


async def get(conn: aiosqlite.Connection, referral_id: int) -> Referral | None:
    """Fetch a referral by primary key. Returns ``None`` if not found."""
    cursor = await conn.execute(f"{_SELECT} WHERE id = ?", (referral_id,))
    row = await cursor.fetchone()
    return Referral.from_row(row) if row else None


async def get_by_referred(
    conn: aiosqlite.Connection, referred_id: int
) -> Referral | None:
    """Return the referral row for ``referred_id``, or ``None``.

    Because ``referred_id`` is UNIQUE, at most one row matches. Used by
    :func:`app.services.referrals.register_referral` to decide whether the
    user is already bound (skip re-binding) and by
    :func:`reward_referrer_after_first_payment` to resolve the inviter.
    """
    cursor = await conn.execute(
        f"{_SELECT} WHERE referred_id = ?", (referred_id,)
    )
    row = await cursor.fetchone()
    return Referral.from_row(row) if row else None


async def try_mark_rewarded(
    conn: aiosqlite.Connection, referred_id: int
) -> Referral | None:
    """Atomically flip the referral for ``referred_id`` to ``'rewarded'``.

    Runs a single guarded ``UPDATE … WHERE referred_id=? AND status='pending'``
    and checks ``rowcount``: exactly ``1`` means *this* call won the right to
    pay the bonus (returns the now-rewarded :class:`Referral`); ``0`` means the
    referral was already rewarded, does not exist, or another concurrent call
    won the race (returns ``None``). The caller credits the inviter's wallet
    **only** when a non-``None`` row comes back, so the bonus lands exactly once.
    """
    cursor = await conn.execute(
        "UPDATE referrals SET status = 'rewarded', rewarded_at = ? "
        "WHERE referred_id = ? AND status = 'pending'",
        (_utcnow_iso(), referred_id),
    )
    await conn.commit()
    if cursor.rowcount != 1:
        return None
    return await get_by_referred(conn, referred_id)


async def count_for_referrer(
    conn: aiosqlite.Connection, referrer_id: int
) -> int:
    """Return how many users ``referrer_id`` has invited (any status).

    Counts every ``referrals`` row whose ``referrer_id`` matches — both
    ``pending`` and ``rewarded`` — so the «👥 Пригласить друга» screen can show
    the inviter's total reach. Returns ``0`` when the user has invited nobody.
    """
    cursor = await conn.execute(
        "SELECT COUNT(*) AS n FROM referrals WHERE referrer_id = ?",
        (referrer_id,),
    )
    row = await cursor.fetchone()
    assert row is not None
    return int(row["n"])


__all__ = [
    "Referral",
    "ReferralStatus",
    "count_for_referrer",
    "create_pending",
    "get",
    "get_by_referred",
    "try_mark_rewarded",
]
