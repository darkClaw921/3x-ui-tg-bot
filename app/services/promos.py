"""Promo code business logic.

Three responsibilities:

1. :func:`validate` — synchronous-with-DB sanity checks of a code submitted
   by a user (code exists, not expired, capacity left, this user has not
   already redeemed it).
2. :func:`compute_discount` — pure-function math turning a (plan, promo)
   pair into a :class:`DiscountResult` (``final_price``, ``extra_days``).
3. :func:`apply` — thin wrapper around
   :func:`app.db.repos.promos.try_redeem` so call sites do not need to
   reach into the repository directly.

Validation is intentionally cheap (one or two SELECTs) — the authoritative
race-safe check happens inside :func:`apply` (which runs ``try_redeem``
under ``BEGIN IMMEDIATE``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

import aiosqlite

from app.db.repos import promos as promos_repo
from app.db.repos.plans import Plan
from app.db.repos.promos import Promo


# ---------------------------------------------------------------------- #
# Result types
# ---------------------------------------------------------------------- #


@dataclass(slots=True, frozen=True)
class PromoValidation:
    """Outcome of :func:`validate`.

    * ``is_valid=True``  — ``promo`` is set, ``error`` is ``None``.
    * ``is_valid=False`` — ``promo`` may still be set (e.g. user already
      redeemed the code) but the caller MUST refuse usage. ``error`` is a
      user-facing message in Russian, safe to send to the chat verbatim.
    """

    is_valid: bool
    error: str | None
    promo: Promo | None


@dataclass(slots=True, frozen=True)
class DiscountResult:
    """Outcome of :func:`compute_discount`.

    * ``final_price`` — price in Stars to charge after the discount. For
      ``free_days`` it stays equal to the plan's nominal price.
    * ``extra_days`` — additional days to grant on top of ``plan.days``.
      Always 0 except for ``free_days``.
    """

    final_price: int
    extra_days: int


# ---------------------------------------------------------------------- #
# Validation
# ---------------------------------------------------------------------- #


def _utcnow_iso() -> str:
    """Return current UTC time in ISO-8601 (seconds resolution).

    Mirrors the helper inside :mod:`app.db.repos.promos` so this module
    doesn't reach into private repo internals.
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat(sep=" ")


async def _already_redeemed_by(
    conn: aiosqlite.Connection, promo_id: int, user_id: int
) -> bool:
    """Return ``True`` iff ``user_id`` already redeemed ``promo_id`` once.

    Policy: one redemption per user per promo. This is checked outside the
    redeem transaction (a UI-level guard); the transaction itself does not
    enforce it, so a separate query is necessary.
    """
    cursor = await conn.execute(
        "SELECT 1 FROM promo_redemptions "
        "WHERE promo_id = ? AND user_id = ? LIMIT 1",
        (promo_id, user_id),
    )
    row = await cursor.fetchone()
    return row is not None


async def validate(
    conn: aiosqlite.Connection,
    code: str,
    user_id: int,
    plan: Plan | None,
) -> PromoValidation:
    """Validate a promo code submitted by a user.

    Parameters
    ----------
    conn
        Open SQLite connection (caller owns lifecycle).
    code
        The raw code as typed by the user. Trimmed; lookup is
        case-insensitive (see :func:`app.db.repos.promos.get_by_code`).
    user_id
        Internal user id (``users.id``, NOT ``tg_id``).
    plan
        The plan the user is trying to buy. ``None`` means a standalone
        activation flow (e.g. the "Активировать промокод" entry point)
        where only ``free_days`` promos make sense — the caller should
        check ``promo.type`` after a successful validation.

    Returns
    -------
    PromoValidation
        ``is_valid=False`` with a human-readable ``error`` on any failure;
        ``is_valid=True`` with the resolved :class:`Promo` otherwise.
    """
    stripped = (code or "").strip()
    if not stripped:
        return PromoValidation(is_valid=False, error="Введите код промокода.", promo=None)

    promo = await promos_repo.get_by_code(conn, stripped)
    if promo is None:
        return PromoValidation(
            is_valid=False, error="Промокод не найден.", promo=None
        )

    now = _utcnow_iso()
    if promo.expires_at is not None and promo.expires_at <= now:
        return PromoValidation(
            is_valid=False,
            error="Срок действия промокода истёк.",
            promo=promo,
        )

    if promo.max_uses != 0 and promo.used_count >= promo.max_uses:
        return PromoValidation(
            is_valid=False,
            error="Лимит активаций промокода исчерпан.",
            promo=promo,
        )

    if await _already_redeemed_by(conn, promo.id, user_id):
        return PromoValidation(
            is_valid=False,
            error="Вы уже активировали этот промокод.",
            promo=promo,
        )

    # Type-vs-context sanity. If a plan is provided the type must be one
    # that the buy flow knows how to apply (percent / flat_stars / free_days
    # — all three are valid during a purchase). If plan is None we accept
    # any type here; the caller (promo activation handler) decides whether
    # to refuse non-free_days promos.
    if plan is not None and promo.type not in {"percent", "flat_stars", "free_days"}:
        return PromoValidation(
            is_valid=False,
            error="Неподдерживаемый тип промокода.",
            promo=promo,
        )

    return PromoValidation(is_valid=True, error=None, promo=promo)


# ---------------------------------------------------------------------- #
# Pricing math
# ---------------------------------------------------------------------- #


def compute_discount(plan: Plan, promo: Promo | None) -> DiscountResult:
    """Compute the post-discount price (Stars) and bonus days for a plan.

    Rules:

    * ``promo is None``           → ``final_price = plan.price_stars``,
      ``extra_days = 0``.
    * ``promo.type == 'percent'`` → ``final_price = ceil(plan.price_stars
      * (100 - promo.value) / 100)``. ``promo.value`` is a percentage
      (1..100). The result is rounded **up** so we never undercharge by
      a fractional Stars (Stars are integers).
    * ``promo.type == 'flat_stars'`` → ``final_price = max(0,
      plan.price_stars - promo.value)``.
    * ``promo.type == 'free_days'`` → ``final_price = plan.price_stars``,
      ``extra_days = promo.value``.

    The final price floor is left at 0 here; the invoice builder
    (:mod:`app.services.billing`) raises it to 1 because Telegram refuses
    Stars invoices below 1.
    """
    if promo is None:
        return DiscountResult(final_price=int(plan.price_stars), extra_days=0)

    if promo.type == "percent":
        pct = max(0, min(100, int(promo.value)))
        final = math.ceil(plan.price_stars * (100 - pct) / 100)
        return DiscountResult(final_price=max(0, int(final)), extra_days=0)

    if promo.type == "flat_stars":
        return DiscountResult(
            final_price=max(0, int(plan.price_stars) - int(promo.value)),
            extra_days=0,
        )

    if promo.type == "free_days":
        return DiscountResult(
            final_price=int(plan.price_stars),
            extra_days=max(0, int(promo.value)),
        )

    # Unknown type — fall back to the no-promo price so the user is never
    # charged less than the plan asks for due to a misconfigured promo.
    return DiscountResult(final_price=int(plan.price_stars), extra_days=0)


# ---------------------------------------------------------------------- #
# Atomic redemption
# ---------------------------------------------------------------------- #


async def apply(
    conn: aiosqlite.Connection,
    promo_id: int,
    user_id: int,
    subscription_id: int | None,
) -> bool:
    """Atomically redeem a promo (idempotent at the row level).

    Wraps :func:`app.db.repos.promos.try_redeem`. Returns ``True`` if the
    redemption succeeded; ``False`` if the promo became invalid between
    :func:`validate` and now (capacity exhausted, expired, deleted) or if
    a concurrent transaction won the race.

    The caller is expected to surface a sensible error to the user when
    this returns ``False`` (e.g. revert the discount and refund — though
    in the Stars-buy flow the redemption is done right after the payment
    is recorded, so the worst case is that the user gets the
    discount-charged plan without the promo counter increment, and the
    admin can reconcile manually).
    """
    return await promos_repo.try_redeem(
        conn,
        promo_id=promo_id,
        user_id=user_id,
        subscription_id=subscription_id,
    )


__all__ = [
    "DiscountResult",
    "PromoValidation",
    "apply",
    "compute_discount",
    "validate",
]
