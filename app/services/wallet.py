"""Wallet service — credit and atomic spend on a user's Stars balance.

This is the business-logic layer on top of :mod:`app.db.repos.wallet`. It owns
the two write paths into the ledger:

* :func:`credit` — add Stars to the balance (top-up, refund, referral bonus,
  admin grant). Idempotent through a deterministic ``ref``.
* :func:`try_spend` — atomically debit Stars **iff** the balance covers it.
  Runs inside :func:`app.db.engine.transaction` (``BEGIN IMMEDIATE``) so the
  balance read and the debit insert happen under a single write lock — this is
  what makes the operation safe against double-spend (two concurrent spends
  racing past the balance check) *and* replay (the same logical spend retried),
  the latter via the unique ``ref``.

Why ``BEGIN IMMEDIATE`` matters
-------------------------------

A naive "read balance, then insert spend" is a classic check-then-act race: two
requests could both read a sufficient balance and both insert a debit, over-
drawing the wallet. ``BEGIN IMMEDIATE`` acquires SQLite's RESERVED write lock
*before* the balance is read, serialising every writer — the second request
blocks until the first commits, then re-reads the now-reduced balance. The
deterministic ``ref`` closes the remaining gap: even a perfectly-timed retry of
the *same* spend is rejected by the partial-unique index, so a spend lands at
most once.
"""

from __future__ import annotations

import aiosqlite

from app.db.engine import transaction
from app.db.repos import wallet as wallet_repo
from app.db.repos.wallet import WalletTxnType


async def credit(
    conn: aiosqlite.Connection,
    user_id: int,
    amount: int,
    *,
    type: WalletTxnType,
    ref: str | None = None,
) -> bool:
    """Credit ``amount`` Stars to ``user_id``'s wallet. Return success.

    ``amount`` must be positive (a credit). The signed ledger value stored is
    ``+amount``. Returns ``True`` when a new row was appended, ``False`` when a
    duplicate ``ref`` was rejected (the credit had already been applied) — so a
    retried top-up / referral payout credits the balance exactly once.

    ``type`` should be one of the *credit* kinds (``topup`` / ``refund`` /
    ``referral_bonus`` / ``admin_grant``); the caller picks the semantically
    correct one for auditing. ``ValueError`` is raised for a non-positive
    ``amount`` so a sign bug surfaces immediately instead of silently shrinking
    the balance.
    """
    if amount <= 0:
        raise ValueError(f"credit amount must be positive, got {amount}")
    txn = await wallet_repo.add(
        conn,
        user_id=user_id,
        type=type,
        amount=int(amount),
        ref=ref,
    )
    return txn is not None


async def try_spend(
    conn: aiosqlite.Connection,
    user_id: int,
    amount: int,
    *,
    ref: str,
) -> bool:
    """Atomically debit ``amount`` Stars from ``user_id`` iff the balance covers it.

    Returns ``True`` when the debit was recorded, ``False`` when either:

    * the balance is insufficient (``amount > balance`` — overdraw rejected), or
    * the ``ref`` was already used (replay rejected by the partial-unique index).

    The balance read and the debit insert run inside one
    :func:`app.db.engine.transaction` (``BEGIN IMMEDIATE``) so no other writer
    can interleave between them — this is the double-spend guard. The recorded
    ledger row has ``type='spend'`` and ``amount=-amount`` (debits are negative).

    ``ref`` is **required** (unlike :func:`credit`) and must be deterministic for
    the logical spend (e.g. ``buy:<user>:<plan>:<...>``) so a retried request
    maps to the same ref and is rejected on the second attempt rather than
    debiting twice.

    ``ValueError`` is raised for a non-positive ``amount`` so a sign bug surfaces
    immediately.
    """
    if amount <= 0:
        raise ValueError(f"spend amount must be positive, got {amount}")
    amount = int(amount)
    # The whole critical section runs under one ``BEGIN IMMEDIATE``. We issue raw
    # SQL here (rather than calling :func:`app.db.repos.wallet.add`, which commits
    # on its own) so the balance read and the debit insert share a single
    # transaction boundary — committing mid-block would release the write lock
    # and defeat the double-spend guard.
    #
    # A duplicate ``ref`` (replay) makes the INSERT raise
    # :class:`aiosqlite.IntegrityError`; :func:`app.db.engine.transaction` rolls
    # the section back and re-raises it. We catch it here and report ``False`` —
    # the original spend already debited the balance, so this retry is a no-op.
    try:
        async with transaction(conn):
            current = await wallet_repo.balance(conn, user_id)
            if current < amount:
                # Insufficient funds — leave the ledger untouched. The block
                # commits with no write (a harmless no-op).
                return False
            await conn.execute(
                "INSERT INTO wallet_transactions (user_id, type, amount, ref) "
                "VALUES (?, 'spend', ?, ?)",
                (user_id, -amount, ref),
            )
    except aiosqlite.IntegrityError:
        return False
    return True


__all__ = ["credit", "try_spend"]
