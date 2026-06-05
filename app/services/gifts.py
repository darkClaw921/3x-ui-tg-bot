"""Gift subscriptions — mint codes on purchase, redeem them with compensation.

Two public entry points:

* :func:`make_gift_code` — mint a fresh ``active`` gift code for a buyer's
  paid plan/inbound. Generates a ``GIFT-XXXXXXXX`` token (8 hex chars) and
  retries on the (astronomically rare) ``UNIQUE(code)`` collision so a code is
  always handed back.
* :func:`redeem_gift` — atomically claim a code, provision the recipient's
  subscription (xui-first via :func:`app.services.subscriptions.create_or_extend`),
  link the new subscription to the code, and **compensate** (roll the code back
  to ``'active'``) if provisioning fails — so a panel error never burns a code.

Why claim-first
---------------

Redemption claims the code (``status='active'`` → ``'redeemed'``) *before*
touching the panel. This serialises two concurrent redemptions at the DB
(``try_claim`` runs under ``BEGIN IMMEDIATE``) — only one wins the claim, the
other gets :class:`GiftRedeemError`. The provisioning then runs outside the
write lock; on :class:`app.xui.XuiError` we revert the status so the *same*
recipient (or another) can retry, rather than losing the gift.
"""

from __future__ import annotations

import secrets

import aiosqlite
from loguru import logger

from app.db.repos import gift_codes as gift_repo
from app.db.repos.gift_codes import GiftCode
from app.db.repos.plans import Plan
from app.db.repos.subscriptions import Subscription
from app.db.repos.users import User
from app.services import subscriptions as subs_service
from app.xui import XuiClient, XuiError

# Gift-code format: a fixed ``GIFT-`` prefix plus 8 uppercase hex chars
# (4 random bytes). 16^8 ≈ 4.3e9 keyspace — collisions are practically
# impossible, but ``make_gift_code`` retries anyway for correctness.
_GIFT_PREFIX = "GIFT-"
_GIFT_HEX_BYTES = 4
_MINT_MAX_RETRIES = 5


class GiftRedeemError(Exception):
    """Raised by :func:`redeem_gift` when a code cannot be redeemed.

    Two terminal reasons, distinguished by :attr:`reason`:

    * ``"not_found"`` — no code matches (wrong / mistyped token).
    * ``"not_active"`` — the code exists but is already redeemed / refunded, or
      another concurrent redemption won the atomic claim.

    The handler maps each to a localized message (``gift.code_not_found`` /
    ``gift.code_not_active``).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _new_code() -> str:
    """Return a fresh ``GIFT-XXXXXXXX`` token (uppercase hex)."""
    return _GIFT_PREFIX + secrets.token_hex(_GIFT_HEX_BYTES).upper()


async def make_gift_code(
    conn: aiosqlite.Connection,
    *,
    plan_id: int | None,
    inbound_id: int,
    buyer_id: int,
    payment_id: int | None = None,
) -> GiftCode:
    """Mint a new ``active`` gift code for ``buyer_id``'s purchase.

    Inserts a row via :func:`app.db.repos.gift_codes.create` with a freshly
    generated token. On the rare ``UNIQUE(code)`` collision
    (:class:`aiosqlite.IntegrityError`) it regenerates and retries up to
    :data:`_MINT_MAX_RETRIES` times before giving up (re-raising the last
    error) — so a code is virtually always returned.

    ``plan_id`` / ``inbound_id`` describe what the recipient will get;
    ``payment_id`` links the code to the buyer's payment row (passed once the
    payment is recorded) for refund traceability.
    """
    last_exc: aiosqlite.IntegrityError | None = None
    for _ in range(_MINT_MAX_RETRIES):
        code = _new_code()
        try:
            gift = await gift_repo.create(
                conn,
                code=code,
                plan_id=plan_id,
                inbound_id=int(inbound_id),
                buyer_id=buyer_id,
                payment_id=payment_id,
            )
        except aiosqlite.IntegrityError as exc:
            # Code collision (or a duplicate payment_id, which would be a caller
            # bug). Regenerate the code and retry.
            last_exc = exc
            logger.warning("make_gift_code: code collision on {} — retrying", code)
            continue
        logger.info(
            "make_gift_code: minted {} for buyer {} (plan {}, inbound {})",
            gift.code,
            buyer_id,
            plan_id,
            inbound_id,
        )
        return gift
    assert last_exc is not None
    raise last_exc


async def redeem_gift(
    conn: aiosqlite.Connection,
    xui: XuiClient,
    *,
    code: str,
    redeemer: User,
) -> tuple[GiftCode, Subscription]:
    """Redeem ``code`` for ``redeemer`` and return ``(gift, subscription)``.

    Flow (claim-first, with compensation):

    1. **Claim** — :func:`app.db.repos.gift_codes.try_claim` atomically flips the
       code ``active`` → ``redeemed`` under ``BEGIN IMMEDIATE``. A ``None`` return
       means the code is missing or already claimed (mapped to
       :class:`GiftRedeemError` — ``not_found`` / ``not_active`` after a lookup
       to distinguish them), so a double-redeem is impossible.
    2. **Provision** — :func:`app.services.subscriptions.create_or_extend` with
       ``extend_sub_id=None`` and the code's ``inbound_id`` creates a fresh
       subscription for the recipient (xui-first). The gift carries no promo and
       always provisions a brand-new subscription (never extends).
    3. **Link** — :func:`app.db.repos.gift_codes.link_subscription` records the
       new ``subscription_id`` on the code for the audit trail.

    Compensation: if step 2 raises :class:`app.xui.XuiError`, the claim from step
    1 is rolled back (:func:`set_status` → ``'active'``) so the gift is not burned
    and can be retried once the panel recovers; the error is re-raised for the
    handler to apologise.

    Provisioning needs the plan's ``days`` / ``traffic_gb``, so the gift's
    ``plan_id`` is resolved up-front. If the plan was deleted in the meantime we
    raise :class:`GiftRedeemError("not_active")` *before* claiming the code, so
    the recipient is told to contact support rather than getting a zero-day
    subscription and the code stays redeemable.
    """
    from app.db.repos import plans as plans_repo

    existing = await gift_repo.get_by_code(conn, code)
    if existing is None:
        raise GiftRedeemError("not_found")
    if existing.status != "active":
        raise GiftRedeemError("not_active")

    # Resolve the plan up-front; a gift for a deleted plan can't be provisioned.
    plan: Plan | None = None
    if existing.plan_id is not None:
        plan = await plans_repo.get(conn, existing.plan_id)
    if plan is None:
        logger.error(
            "redeem_gift: plan {} for code {} missing — cannot provision",
            existing.plan_id,
            existing.code,
        )
        raise GiftRedeemError("not_active")

    # Step 1 — atomic claim. Anything other than a clean win is a no-op for us.
    claimed = await gift_repo.try_claim(
        conn, code=existing.code, redeemed_by=redeemer.id
    )
    if claimed is None:
        # Re-read to give the most accurate reason (raced to redeemed/refunded).
        raise GiftRedeemError("not_active")

    # Step 2 — provision (xui-first). Compensate on panel failure.
    try:
        sub = await subs_service.create_or_extend(
            conn=conn,
            xui=xui,
            user=redeemer,
            plan=plan,
            promo=None,
            inbound_id=int(claimed.inbound_id),
            extend_sub_id=None,
        )
    except XuiError:
        # Roll the claim back so the gift can be redeemed again later.
        logger.error(
            "redeem_gift: provisioning failed for code {} — reverting claim",
            claimed.code,
        )
        await gift_repo.set_status(conn, claimed.id, "active")
        raise

    # Step 3 — link the provisioned subscription to the code (audit trail).
    await gift_repo.link_subscription(conn, claimed.id, sub.id)
    refreshed = await gift_repo.get(conn, claimed.id)
    assert refreshed is not None
    logger.info(
        "redeem_gift: code {} redeemed by user {} → sub {}",
        claimed.code,
        redeemer.id,
        sub.id,
    )
    return refreshed, sub


__all__ = [
    "GiftRedeemError",
    "make_gift_code",
    "redeem_gift",
]
