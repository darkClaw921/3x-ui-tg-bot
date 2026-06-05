"""Repository for the ``wallet_transactions`` table — the Stars-balance ledger.

The wallet is an **append-only ledger**: there is no stored ``balance`` column.
A user's current balance is always recomputed as ``COALESCE(SUM(amount), 0)``
over all of their rows (:func:`balance`), so the ledger is the single source of
truth and can never drift.

``amount`` is a *signed* integer — credits (``topup`` / ``refund`` /
``referral_bonus`` / ``admin_grant``) are positive, debits (``spend`` /
``payment``) are negative.

Idempotency is enforced at the database level by the partial-unique index
``idx_wallet_ref`` (``UNIQUE(ref) WHERE ref IS NOT NULL``): inserting a row whose
non-NULL ``ref`` already exists raises :class:`aiosqlite.IntegrityError`, which
:func:`add` catches and turns into a ``None`` return. This is the backbone of
the wallet's replay / double-credit / double-spend protection — callers build a
*deterministic* ``ref`` (e.g. ``topup:<charge_id>``) so a retried event maps to
the same ref and is rejected on the second attempt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import aiosqlite

# The set of ledger entry kinds, mirrored by the ``CHECK`` constraint in the
# schema. Credits are positive, debits negative — but the sign lives in
# ``amount``, not in ``type``; ``type`` is purely descriptive / for auditing.
WalletTxnType = Literal[
    "topup",
    "spend",
    "refund",
    "referral_bonus",
    "admin_grant",
    "payment",
]


@dataclass(slots=True, frozen=True)
class WalletTxn:
    """A single row from the ``wallet_transactions`` ledger."""

    id: int
    user_id: int
    type: WalletTxnType
    amount: int
    ref: str | None
    created_at: str

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> WalletTxn:
        """Build a :class:`WalletTxn` from an :class:`aiosqlite.Row`."""
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            type=row["type"],
            amount=row["amount"],
            ref=row["ref"],
            created_at=row["created_at"],
        )


_SELECT = "SELECT id, user_id, type, amount, ref, created_at FROM wallet_transactions"


async def balance(conn: aiosqlite.Connection, user_id: int) -> int:
    """Return the current Stars balance for ``user_id``.

    Computed as ``COALESCE(SUM(amount), 0)`` over the user's ledger rows, so a
    user with no transactions has a balance of ``0`` (never ``None``).
    """
    cursor = await conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS bal FROM wallet_transactions "
        "WHERE user_id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    assert row is not None
    return int(row["bal"])


async def add(
    conn: aiosqlite.Connection,
    *,
    user_id: int,
    type: WalletTxnType,
    amount: int,
    ref: str | None = None,
) -> WalletTxn | None:
    """Append a ledger row and return it, or ``None`` on a duplicate ``ref``.

    When ``ref`` is non-NULL and already present, the partial-unique index
    ``idx_wallet_ref`` makes the insert raise :class:`aiosqlite.IntegrityError`;
    we catch it and return ``None`` so the caller can treat the duplicate as a
    no-op (the original row already recorded the event). When ``ref`` is
    ``None`` no uniqueness is enforced and the row is always inserted.

    The caller owns the transaction boundary: this function commits on success
    so a stand-alone :func:`add` persists, but when invoked inside an open
    transaction (e.g. :func:`app.services.wallet.try_spend` under
    ``BEGIN IMMEDIATE``) the surrounding ``COMMIT`` / ``ROLLBACK`` governs
    durability. The ``IntegrityError`` is raised *before* any commit, so a
    rejected duplicate never leaves a partial write.
    """
    try:
        cursor = await conn.execute(
            "INSERT INTO wallet_transactions (user_id, type, amount, ref) "
            "VALUES (?, ?, ?, ?)",
            (user_id, type, amount, ref),
        )
    except aiosqlite.IntegrityError:
        # Duplicate non-NULL ref — the event was already recorded. Roll back the
        # failed statement's implicit savepoint state by leaving the row absent;
        # we deliberately do NOT commit here.
        return None
    await conn.commit()
    new_id = cursor.lastrowid
    assert new_id is not None
    cursor = await conn.execute(f"{_SELECT} WHERE id = ?", (new_id,))
    row = await cursor.fetchone()
    assert row is not None
    return WalletTxn.from_row(row)


async def get_by_ref(
    conn: aiosqlite.Connection, ref: str
) -> WalletTxn | None:
    """Return the ledger row with the given non-NULL ``ref``, or ``None``.

    Because ``idx_wallet_ref`` is unique over non-NULL refs, at most one row can
    match. Used by the pay-from-balance flow to recover the freshly-inserted
    debit's ``id`` after :func:`app.services.wallet.try_spend` succeeds, so a
    synthetic ``payments`` row can reference it via ``telegram_charge_id =
    wallet:<txn_id>``.
    """
    cursor = await conn.execute(f"{_SELECT} WHERE ref = ?", (ref,))
    row = await cursor.fetchone()
    return WalletTxn.from_row(row) if row else None


async def list_for_user(
    conn: aiosqlite.Connection, user_id: int, limit: int = 20
) -> list[WalletTxn]:
    """Return the most recent ``limit`` ledger rows for ``user_id``.

    Ordered by ``created_at DESC, id DESC`` so the newest transaction is first
    (``id`` breaks ties for rows created within the same clock second).
    """
    cursor = await conn.execute(
        f"{_SELECT} WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
        (user_id, limit),
    )
    rows = await cursor.fetchall()
    return [WalletTxn.from_row(r) for r in rows]


__all__ = [
    "WalletTxn",
    "WalletTxnType",
    "add",
    "balance",
    "get_by_ref",
    "list_for_user",
]
