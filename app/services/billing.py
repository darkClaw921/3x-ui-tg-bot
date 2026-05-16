"""Stars invoice construction and final-price computation.

The bot accepts Telegram Stars exclusively (``currency='XTR'``); no
``provider_token`` is required for Stars payments and an empty string is
passed explicitly to make the intent obvious.

Three helpers:

* :func:`calc_price` — wraps :func:`app.services.promos.compute_discount`
  and applies the **Stars-minimum** floor (Telegram refuses Stars invoices
  with ``amount < 1``).
* :func:`build_invoice_payload` / :func:`parse_invoice_payload` — JSON
  encoder + decoder for the ``payload`` field, which Telegram echoes back
  in both ``pre_checkout_query`` and ``successful_payment`` and is the
  only state-carrying channel between sending an invoice and receiving
  the payment confirmation.
* :func:`send_invoice` — convenience wrapper around
  :meth:`aiogram.Bot.send_invoice` that fills in the boilerplate
  (currency, prices, payload, sensible title/description).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import LabeledPrice, Message

from app.db.repos.plans import Plan
from app.db.repos.promos import Promo
from app.services.promos import DiscountResult, compute_discount


# Telegram's minimum Stars amount for an invoice is 1; sending 0 returns
# 400 "Bad Request: amount must be positive". We round up to this floor
# even if a promo would otherwise produce a free invoice — discounts that
# fully cover a plan should use the ``free_days`` flow instead.
_STARS_MIN = 1

# Stars invoices must fit Telegram's 128-byte payload limit. Our payload
# is a short JSON object so this is a sanity bound rather than a real
# constraint, but we surface it as a constant so it's easy to find.
_PAYLOAD_BYTE_LIMIT = 128


@dataclass(slots=True, frozen=True)
class InvoicePrice:
    """Final price summary returned by :func:`calc_price`.

    * ``stars`` — what the user will pay (always ``>= _STARS_MIN``).
    * ``raw_discount`` — the raw :class:`DiscountResult` from
      :mod:`app.services.promos` (before the Stars-minimum floor).
    * ``extra_days`` — bonus days granted by a ``free_days`` promo (0
      otherwise). Kept here so the confirmation message can show it.
    """

    stars: int
    raw_discount: DiscountResult
    extra_days: int


# ---------------------------------------------------------------------- #
# Pricing
# ---------------------------------------------------------------------- #


def calc_price(plan: Plan, promo: Promo | None) -> InvoicePrice:
    """Return the final Stars price for ``plan`` after applying ``promo``.

    Delegates to :func:`app.services.promos.compute_discount` and then
    raises the price to ``_STARS_MIN`` if the discount would otherwise
    produce a 0-Stars invoice (Telegram requires at least 1).
    """
    discount = compute_discount(plan, promo)
    stars = max(_STARS_MIN, int(discount.final_price))
    return InvoicePrice(stars=stars, raw_discount=discount, extra_days=discount.extra_days)


# ---------------------------------------------------------------------- #
# Payload
# ---------------------------------------------------------------------- #


def build_invoice_payload(plan_id: int, promo_id: int | None) -> str:
    """Encode the persistent state needed by ``successful_payment``.

    The payload is echoed verbatim by Telegram in:

    * ``pre_checkout_query.invoice_payload``
    * ``message.successful_payment.invoice_payload``

    It is the only place we can stash ``plan_id`` / ``promo_id`` because
    the user's FSM state may have been cleared (or moved on) between
    invoice creation and payment.
    """
    payload = json.dumps(
        {"plan_id": int(plan_id), "promo_id": int(promo_id) if promo_id else None},
        separators=(",", ":"),  # compact form keeps us well under 128 bytes
    )
    if len(payload.encode("utf-8")) > _PAYLOAD_BYTE_LIMIT:
        # Should never happen with current shape; surface as a programmer
        # error so the buy handler doesn't silently fail later.
        raise ValueError(f"invoice payload exceeds {_PAYLOAD_BYTE_LIMIT} bytes")
    return payload


def parse_invoice_payload(payload: str) -> tuple[int, int | None]:
    """Decode the JSON written by :func:`build_invoice_payload`.

    Returns ``(plan_id, promo_id_or_None)``. Raises :class:`ValueError`
    on a malformed payload — the buy handler treats this as "answer
    pre_checkout with ok=False".
    """
    try:
        data = json.loads(payload)
    except ValueError as exc:
        raise ValueError(f"invalid invoice payload: {payload!r}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"invoice payload not an object: {payload!r}")
    try:
        plan_id = int(data["plan_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invoice payload missing/bad plan_id: {payload!r}") from exc
    raw_promo = data.get("promo_id")
    promo_id: int | None
    if raw_promo is None:
        promo_id = None
    else:
        try:
            promo_id = int(raw_promo)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"invoice payload bad promo_id: {payload!r}"
            ) from exc
        if promo_id == 0:
            promo_id = None
    return plan_id, promo_id


# ---------------------------------------------------------------------- #
# Invoice send
# ---------------------------------------------------------------------- #


def _invoice_title(plan: Plan) -> str:
    """Return a concise title for the Stars-invoice header."""
    return f"VPN · {plan.title}"


def _invoice_description(plan: Plan, price: InvoicePrice, promo: Promo | None) -> str:
    """Return a human-readable description shown inside the invoice card."""
    parts = [f"Доступ на {plan.days} дн."]
    if price.extra_days:
        parts.append(f"+{price.extra_days} бонусных дн.")
    if promo is not None and promo.type != "free_days":
        # Show the discount applied. For percent we surface the percent,
        # for flat_stars the absolute Stars amount.
        if promo.type == "percent":
            parts.append(f"Промокод {promo.code}: −{promo.value}%")
        elif promo.type == "flat_stars":
            parts.append(f"Промокод {promo.code}: −{promo.value}⭐")
    return ". ".join(parts) + "."


async def send_invoice(
    bot: Bot,
    chat_id: int,
    plan: Plan,
    promo: Promo | None,
) -> Message:
    """Send a Stars invoice for ``plan`` (with optional ``promo``).

    Telegram quirks accounted for:

    * ``currency='XTR'`` is Stars.
    * ``provider_token=''`` is required for Stars (empty string).
    * ``prices`` must contain at least one :class:`LabeledPrice`; we use
      a single line whose amount is the final Stars price.
    * The minimum invoice amount is 1 Stars — enforced by :func:`calc_price`.
    """
    price = calc_price(plan, promo)
    payload = build_invoice_payload(plan_id=plan.id, promo_id=promo.id if promo else None)
    prices = [LabeledPrice(label=plan.title, amount=price.stars)]

    return await bot.send_invoice(
        chat_id=chat_id,
        title=_invoice_title(plan),
        description=_invoice_description(plan, price, promo),
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=prices,
    )


__all__ = [
    "InvoicePrice",
    "build_invoice_payload",
    "calc_price",
    "parse_invoice_payload",
    "send_invoice",
]
