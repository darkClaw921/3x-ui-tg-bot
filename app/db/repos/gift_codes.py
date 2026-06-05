"""Repository for the ``gift_codes`` table — purchasable, redeemable codes.

A gift is a subscription a *buyer* pays for but does **not** redeem themselves:
``successful_payment`` mints a unique ``code`` (instead of provisioning a
subscription for the buyer) which a *recipient* later activates. The lifecycle
of a code is encoded in ``status``:

    active  → minted, waiting to be redeemed
    redeemed → claimed by a recipient (terminal)
    refunded → purchase reversed before redemption (terminal)

Two design points mirror :mod:`app.db.repos.promos`:

* :func:`get_by_code` is case-insensitive (``COLLATE NOCASE``) because users
  paste codes in any case from a deep-link or a message.
* :func:`try_redeem` runs inside a ``BEGIN IMMEDIATE`` transaction
  (:func:`app.db.engine.transaction`) and flips ``status`` with a guarded
  ``UPDATE … WHERE status='active'`` so two concurrent redemptions of the same
  code cannot both succeed — the code is claimed at most once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import aiosqlite

from app.db.engine import transaction

GiftCodeStatus = Literal["active", "redeemed", "refunded"]


def _utcnow_iso() -> str:
    """Return current UTC time in ISO-8601 (seconds resolution)."""
    return datetime.now(UTC).replace(microsecond=0).isoformat(sep=" ")


@dataclass(slots=True, frozen=True)
class GiftCode:
    """A row from the ``gift_codes`` table."""

    id: int
    code: str
    plan_id: int | None
    inbound_id: int
    buyer_id: int
    payment_id: int | None
    status: GiftCodeStatus
    redeemed_by: int | None
    subscription_id: int | None
    created_at: str
    redeemed_at: str | None

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> GiftCode:
        """Build a :class:`GiftCode` from an :class:`aiosqlite.Row`."""
        return cls(
            id=row["id"],
            code=row["code"],
            plan_id=row["plan_id"],
            inbound_id=row["inbound_id"],
            buyer_id=row["buyer_id"],
            payment_id=row["payment_id"],
            status=row["status"],
            redeemed_by=row["redeemed_by"],
            subscription_id=row["subscription_id"],
            created_at=row["created_at"],
            redeemed_at=row["redeemed_at"],
        )


_SELECT = (
    "SELECT id, code, plan_id, inbound_id, buyer_id, payment_id, status, "
    "redeemed_by, subscription_id, created_at, redeemed_at FROM gift_codes"
)


async def create(
    conn: aiosqlite.Connection,
    *,
    code: str,
    plan_id: int | None,
    inbound_id: int,
    buyer_id: int,
    payment_id: int | None = None,
) -> GiftCode:
    """Insert a new ``active`` gift code and return it.

    ``code`` must be unique (``UNIQUE`` constraint) — a collision raises
    :class:`aiosqlite.IntegrityError`, which the minting service
    (:func:`app.services.gifts.make_gift_code`) retries with a fresh code.
    ``payment_id`` links the code to the buyer's payment row so refunds can be
    traced; it is nullable so a code can be minted before (or without) a
    recorded payment in tests.
    """
    cursor = await conn.execute(
        "INSERT INTO gift_codes "
        "(code, plan_id, inbound_id, buyer_id, payment_id, status) "
        "VALUES (?, ?, ?, ?, ?, 'active')",
        (code, plan_id, inbound_id, buyer_id, payment_id),
    )
    await conn.commit()
    new_id = cursor.lastrowid
    assert new_id is not None
    created = await get(conn, new_id)
    assert created is not None
    return created


async def get(conn: aiosqlite.Connection, gift_id: int) -> GiftCode | None:
    """Fetch a gift code by primary key. Returns ``None`` if not found."""
    cursor = await conn.execute(f"{_SELECT} WHERE id = ?", (gift_id,))
    row = await cursor.fetchone()
    return GiftCode.from_row(row) if row else None


async def get_by_code(conn: aiosqlite.Connection, code: str) -> GiftCode | None:
    """Case-insensitive lookup by ``code``. Returns ``None`` if not found.

    ``code COLLATE NOCASE`` lets the existing UNIQUE index serve both writes
    and reads without an extra functional index, so a recipient who types the
    code in a different case still finds it.
    """
    cursor = await conn.execute(
        f"{_SELECT} WHERE code = ? COLLATE NOCASE", (code,)
    )
    row = await cursor.fetchone()
    return GiftCode.from_row(row) if row else None


async def try_redeem(
    conn: aiosqlite.Connection,
    *,
    code: str,
    redeemed_by: int,
    subscription_id: int,
) -> bool:
    """Atomically claim ``code`` for ``redeemed_by`` and link the subscription.

    Inside a ``BEGIN IMMEDIATE`` block (so two concurrent redemptions of the
    same code serialise), flips the code from ``'active'`` to ``'redeemed'``
    with a capacity-guarded ``UPDATE … WHERE code=? COLLATE NOCASE AND
    status='active'`` and records ``redeemed_by`` / ``subscription_id`` /
    ``redeemed_at``.

    Returns ``True`` when *this* call performed the claim (``rowcount == 1``);
    ``False`` when the code does not exist, was already redeemed/refunded, or
    another concurrent call won the race. A ``False`` return guarantees the
    caller did not flip the status, so the gift is claimed exactly once.

    Note the redeem links a *pre-created* subscription: the service
    (:func:`app.services.gifts.redeem_gift`) provisions the recipient's
    subscription first, then calls this to atomically bind it and close the
    code — if this returns ``False`` the caller compensates.
    """
    async with transaction(conn):
        cursor = await conn.execute(
            "UPDATE gift_codes "
            "SET status = 'redeemed', redeemed_by = ?, subscription_id = ?, "
            "    redeemed_at = ? "
            "WHERE code = ? COLLATE NOCASE AND status = 'active'",
            (redeemed_by, subscription_id, _utcnow_iso(), code),
        )
        return cursor.rowcount == 1


async def try_claim(
    conn: aiosqlite.Connection,
    *,
    code: str,
    redeemed_by: int,
) -> GiftCode | None:
    """Atomically claim ``code`` for ``redeemed_by`` *before* provisioning.

    The "claim-first" half of the gift redemption: inside a ``BEGIN IMMEDIATE``
    block, flip the code from ``'active'`` to ``'redeemed'`` and stamp
    ``redeemed_by`` / ``redeemed_at`` with a guarded ``UPDATE … WHERE
    status='active'`` (``subscription_id`` stays NULL until provisioning
    succeeds and :func:`link_subscription` runs).

    Returns the now-``redeemed`` :class:`GiftCode` when *this* call won the claim
    (``rowcount == 1``); ``None`` when the code does not exist, was already
    redeemed/refunded, or another concurrent call won — so two redemptions can
    never both proceed to provisioning. On a downstream provisioning failure the
    caller compensates with :func:`set_status` (back to ``'active'``).
    """
    async with transaction(conn):
        cursor = await conn.execute(
            "UPDATE gift_codes "
            "SET status = 'redeemed', redeemed_by = ?, redeemed_at = ? "
            "WHERE code = ? COLLATE NOCASE AND status = 'active'",
            (redeemed_by, _utcnow_iso(), code),
        )
        if cursor.rowcount != 1:
            return None
        fetched = await conn.execute(
            f"{_SELECT} WHERE code = ? COLLATE NOCASE", (code,)
        )
        row = await fetched.fetchone()
    return GiftCode.from_row(row) if row else None


async def link_subscription(
    conn: aiosqlite.Connection,
    gift_id: int,
    subscription_id: int,
) -> None:
    """Attach the provisioned ``subscription_id`` to a claimed gift code.

    The "link" half of the claim-first redemption — called after
    :func:`try_claim` succeeded and :func:`app.services.subscriptions.create_or_extend`
    provisioned the recipient's subscription, so the gift's audit trail points
    at the subscription it produced.
    """
    await conn.execute(
        "UPDATE gift_codes SET subscription_id = ? WHERE id = ?",
        (subscription_id, gift_id),
    )
    await conn.commit()


async def set_status(
    conn: aiosqlite.Connection,
    gift_id: int,
    status: GiftCodeStatus,
) -> None:
    """Force a gift code's ``status`` (used for compensation / refunds).

    Mainly used by :func:`app.services.gifts.redeem_gift` to roll a code back to
    ``'active'`` when provisioning the recipient's subscription fails *after*
    the atomic claim, and by refund tooling to mark a code ``'refunded'``.
    """
    await conn.execute(
        "UPDATE gift_codes SET status = ? WHERE id = ?",
        (status, gift_id),
    )
    await conn.commit()


async def list_for_buyer(
    conn: aiosqlite.Connection, buyer_id: int
) -> list[GiftCode]:
    """Return every gift code purchased by ``buyer_id``, newest first."""
    cursor = await conn.execute(
        f"{_SELECT} WHERE buyer_id = ? ORDER BY created_at DESC, id DESC",
        (buyer_id,),
    )
    rows = await cursor.fetchall()
    return [GiftCode.from_row(r) for r in rows]


__all__ = [
    "GiftCode",
    "GiftCodeStatus",
    "create",
    "get",
    "get_by_code",
    "link_subscription",
    "list_for_buyer",
    "set_status",
    "try_claim",
    "try_redeem",
]
