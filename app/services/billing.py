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
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from aiogram import Bot
from aiogram.types import LabeledPrice, Message
from loguru import logger

from app.config import settings
from app.db.repos.plans import Plan
from app.db.repos.promos import Promo
from app.i18n import DEFAULT_LANG, t
from app.services.promos import DiscountResult, compute_discount

# Native Telegram Stars subscriptions are billed on a fixed 30-day period.
# Telegram's Bot API accepts *only* this exact value (2_592_000 seconds =
# 30 days) for ``create_invoice_link(subscription_period=...)``; any other
# value is rejected with 400. It is intentionally a module constant so the
# requirement is impossible to miss.
SUBSCRIPTION_PERIOD_SECONDS = 2_592_000

# The ``kind`` discriminator carried in the invoice payload's ``"k"`` key.
# ``"buy"`` is the implicit default for legacy payloads (which have no
# ``"k"`` key) so the historical purchase flow keeps working untouched.
InvoiceKind = Literal["buy", "topup", "gift", "sub"]


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


@dataclass(slots=True, frozen=True)
class InvoiceContext:
    """Decoded invoice payload — the only state-carrying channel between
    sending a Stars invoice and receiving its ``successful_payment``.

    Telegram echoes the raw payload string verbatim in both
    ``pre_checkout_query.invoice_payload`` and
    ``message.successful_payment.invoice_payload``; :func:`parse_invoice_payload`
    turns that string into this structured object so handlers branch on
    :attr:`kind` instead of re-parsing JSON.

    Fields
    ------
    * ``plan_id`` — plan being purchased / gifted (``0`` for a pure
      top-up, which carries no plan).
    * ``promo_id`` — applied promo, or ``None``.
    * ``inbound_id`` — 3x-ui inbound the subscription will be provisioned
      into (``0`` for a top-up).
    * ``sub_id`` — existing subscription this charge extends (``0`` =
      create a new one / native Star-subscription bootstrap).
    * ``kind`` — discriminator: ``"buy"`` (one-off purchase, the legacy
      default), ``"topup"`` (wallet balance), ``"gift"`` (buy a giftable
      code) or ``"sub"`` (native recurring Star subscription).
    * ``gift`` — gift flag/marker (``1`` when this is a gift purchase,
      ``0`` otherwise). Kept numeric for compact payload encoding.
    * ``topup`` — Stars amount being added to the wallet for a top-up
      (``0`` for every other kind).

    The object is **iterable** as the historical
    ``(plan_id, promo_id, inbound_id, sub_id)`` 4-tuple so existing
    tuple-unpacking call sites keep working during the migration::

        plan_id, promo_id, inbound_id, sub_id = parse_invoice_payload(p)
    """

    plan_id: int
    promo_id: int | None
    inbound_id: int
    sub_id: int
    kind: InvoiceKind = "buy"
    gift: int = 0
    topup: int = 0

    def __iter__(self) -> Iterator[object]:
        """Yield the legacy 4-tuple so old tuple-unpacking still works."""
        yield self.plan_id
        yield self.promo_id
        yield self.inbound_id
        yield self.sub_id


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


def _encode_payload(obj: dict[str, object]) -> str:
    """Serialise ``obj`` to compact JSON and enforce the 128-byte limit.

    Shared by every payload builder so the byte-budget guard lives in one
    place. Raises :class:`ValueError` when the encoded payload would exceed
    :data:`_PAYLOAD_BYTE_LIMIT` — surfaced as a programmer error so a buy /
    top-up / gift handler fails loudly at send time instead of silently
    later.
    """
    payload = json.dumps(
        obj,
        separators=(",", ":"),  # compact form keeps us well under 128 bytes
    )
    if len(payload.encode("utf-8")) > _PAYLOAD_BYTE_LIMIT:
        raise ValueError(f"invoice payload exceeds {_PAYLOAD_BYTE_LIMIT} bytes")
    return payload


def build_invoice_payload(
    plan_id: int,
    promo_id: int | None,
    inbound_id: int,
    *,
    sub_id: int = 0,
) -> str:
    """Encode the persistent state needed by ``successful_payment``.

    The payload is echoed verbatim by Telegram in:

    * ``pre_checkout_query.invoice_payload``
    * ``message.successful_payment.invoice_payload``

    It is the only place we can stash ``plan_id`` / ``promo_id`` /
    ``inbound_id`` / ``sub_id`` because the user's FSM state may have
    been cleared (or moved on) between invoice creation and payment.

    Schema (compact JSON, single-letter keys to stay under the 128-byte
    Telegram limit even for large ids)::

        {"p": <plan_id>, "r": <promo_id_or_null>, "i": <inbound_id>,
         "s": <sub_id_to_extend>}

    This builder produces a ``kind="buy"`` payload and therefore **omits**
    the ``"k"`` discriminator entirely — legacy payloads have no ``"k"``
    and decode as ``kind="buy"`` (see :func:`parse_invoice_payload`), so a
    one-off purchase stays byte-for-byte compatible with pre-``kind``
    payloads.

    The ``"s"`` key is **omitted entirely** when ``sub_id == 0`` (the
    "create new subscription" case) — both for byte-budget hygiene and
    so legacy payloads without ``"s"`` parse as ``sub_id=0`` without
    needing a separate compatibility branch.
    """
    obj: dict[str, object] = {
        "p": int(plan_id),
        "r": int(promo_id) if promo_id else None,
        "i": int(inbound_id),
    }
    if sub_id:
        obj["s"] = int(sub_id)
    return _encode_payload(obj)


def build_topup_payload(stars: int) -> str:
    """Encode a wallet **top-up** payload (``kind="topup"``).

    A top-up carries no plan / inbound — only the Stars amount to credit
    to the user's wallet (``"t"`` key). The ``"k":"topup"`` discriminator
    routes ``successful_payment`` into the wallet-credit branch (Phase 2).

    Schema::

        {"k": "topup", "t": <stars>}
    """
    stars = int(stars)
    if stars < _STARS_MIN:
        raise ValueError(f"top-up amount must be >= {_STARS_MIN} Stars, got {stars}")
    return _encode_payload({"k": "topup", "t": stars})


def build_gift_payload(
    plan_id: int,
    inbound_id: int,
    promo_id: int | None = None,
) -> str:
    """Encode a **gift** purchase payload (``kind="gift"``, ``gift=1``).

    A gift purchase pays for a plan/inbound the buyer does *not* redeem
    themselves — ``successful_payment`` mints a gift code instead of
    provisioning a subscription (Phase 3). It reuses the same plan /
    promo / inbound keys as a normal buy plus the ``"k":"gift"`` and
    ``"g":1`` markers.

    Schema::

        {"k": "gift", "g": 1, "p": <plan_id>, "r": <promo_id_or_null>,
         "i": <inbound_id>}
    """
    obj: dict[str, object] = {
        "k": "gift",
        "g": 1,
        "p": int(plan_id),
        "r": int(promo_id) if promo_id else None,
        "i": int(inbound_id),
    }
    return _encode_payload(obj)


def parse_invoice_payload(payload: str) -> InvoiceContext:
    """Decode a Stars invoice payload into an :class:`InvoiceContext`.

    Raises :class:`ValueError` on a malformed payload — the buy handler
    treats this as "answer pre_checkout with ok=False".

    The returned object is iterable as the historical
    ``(plan_id, promo_id, inbound_id, sub_id)`` 4-tuple so old
    tuple-unpacking call sites keep working.

    Discriminator (``"k"`` key):

    * **Missing** → ``kind="buy"``. Every legacy payload (issued before
      the ``kind`` rollout) has no ``"k"`` and therefore decodes as a
      one-off purchase — this is the backbone of backward compatibility.
    * ``"topup"`` → wallet top-up; carries ``"t"`` (Stars). No plan /
      inbound, so ``plan_id`` / ``inbound_id`` default to ``0``.
    * ``"gift"`` → gift purchase; same plan / promo / inbound keys as a
      buy plus ``gift=1``.
    * ``"sub"`` → native recurring Star subscription bootstrap.

    Backwards compatibility for the buy/gift/sub kinds:

    * The new payload uses short keys ``p`` / ``r`` / ``i`` / ``s``.
      Old payloads use the long keys ``plan_id`` / ``promo_id`` and have
      no ``i`` field; we still accept them and fall back to
      :attr:`settings.XUI_INBOUND_ID` with a WARNING log so operators see
      exactly how many in-flight invoices were affected by the deploy.
    * The ``s`` key (sub_id-to-extend) is optional. Payloads without it
      — both legacy and current "create new subscription" payloads —
      decode as ``sub_id=0``.
    """
    try:
        data = json.loads(payload)
    except ValueError as exc:
        raise ValueError(f"invalid invoice payload: {payload!r}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"invoice payload not an object: {payload!r}")

    # kind — missing "k" means a legacy / one-off purchase ("buy").
    raw_kind = data.get("k")
    kind: InvoiceKind
    if raw_kind is None:
        kind = "buy"
    elif raw_kind in ("buy", "topup", "gift", "sub"):
        kind = raw_kind  # type: ignore[assignment]
    else:
        raise ValueError(f"invoice payload bad kind {raw_kind!r}: {payload!r}")

    # topup amount — only meaningful for kind="topup".
    raw_topup = data.get("t")
    topup = 0
    if raw_topup is not None:
        try:
            topup = int(raw_topup)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invoice payload bad topup: {payload!r}") from exc

    # gift marker — 1 when this is a gift purchase, 0 otherwise.
    raw_gift = data.get("g")
    gift = 0
    if raw_gift is not None:
        try:
            gift = int(raw_gift)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invoice payload bad gift: {payload!r}") from exc

    # A pure top-up carries no plan / promo / inbound — short-circuit so
    # the "missing plan_id" guard below doesn't reject a valid top-up.
    if kind == "topup":
        return InvoiceContext(
            plan_id=0,
            promo_id=None,
            inbound_id=0,
            sub_id=0,
            kind=kind,
            gift=gift,
            topup=topup,
        )

    # plan_id — accept both "p" (new) and "plan_id" (legacy).
    raw_plan = data.get("p", data.get("plan_id"))
    if raw_plan is None:
        raise ValueError(f"invoice payload missing plan_id: {payload!r}")
    try:
        plan_id = int(raw_plan)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invoice payload bad plan_id: {payload!r}") from exc

    # promo_id — accept "r" (new) and "promo_id" (legacy); ``0`` / missing
    # → None to keep callers' "no promo" branch simple.
    raw_promo = data.get("r", data.get("promo_id"))
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

    # inbound_id — only present in new payloads; legacy payloads fall back
    # to the configured default inbound so in-flight purchases mid-deploy
    # do not fail. We log so the on-call operator can tell the difference.
    raw_inbound = data.get("i")
    if raw_inbound is None:
        inbound_id = int(settings.XUI_INBOUND_ID)
        logger.warning(
            "invoice payload missing 'i' (inbound_id); falling back to "
            "settings.XUI_INBOUND_ID={} (payload={!r}). This is expected only "
            "for invoices created before the inbound-selection rollout.",
            inbound_id,
            payload,
        )
    else:
        try:
            inbound_id = int(raw_inbound)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"invoice payload bad inbound_id: {payload!r}"
            ) from exc

    # sub_id — optional ("s" key). Missing / 0 → 0 (legacy and new payloads
    # that create a brand-new subscription).
    raw_sub = data.get("s")
    if raw_sub is None:
        sub_id = 0
    else:
        try:
            sub_id = int(raw_sub)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"invoice payload bad sub_id: {payload!r}"
            ) from exc

    return InvoiceContext(
        plan_id=plan_id,
        promo_id=promo_id,
        inbound_id=inbound_id,
        sub_id=sub_id,
        kind=kind,
        gift=gift,
        topup=topup,
    )


# ---------------------------------------------------------------------- #
# Invoice send
# ---------------------------------------------------------------------- #


def _invoice_title(plan: Plan) -> str:
    """Return a concise title for the Stars-invoice header."""
    return f"VPN · {plan.title}"


def _invoice_description(
    plan: Plan,
    price: InvoicePrice,
    promo: Promo | None,
    *,
    sub_id: int = 0,
) -> str:
    """Return a human-readable description shown inside the invoice card.

    When ``sub_id > 0`` the description signals "продление подписки
    #N" so the user sees in the Stars confirmation that this charge
    extends an existing subscription rather than creating a new one.
    """
    if sub_id:
        parts = [f"Продление подписки #{int(sub_id)} на {plan.days} дн."]
    else:
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
    *,
    inbound_id: int,
    sub_id: int = 0,
) -> Message:
    """Send a Stars invoice for ``plan`` (with optional ``promo``).

    ``inbound_id`` is the 3x-ui inbound the user picked; it is embedded
    into the invoice payload so the ``successful_payment`` handler can
    provision into the right inbound without re-reading the FSM state
    (which Telegram may have cleared between invoice creation and
    payment).

    ``sub_id`` is the existing subscription this purchase should extend
    (``0`` = create a brand-new subscription). It is embedded into the
    payload and surfaced in the human-readable description so the user
    sees "Продление подписки #N" in the Stars confirmation card.

    Telegram quirks accounted for:

    * ``currency='XTR'`` is Stars.
    * ``provider_token=''`` is required for Stars (empty string).
    * ``prices`` must contain at least one :class:`LabeledPrice`; we use
      a single line whose amount is the final Stars price.
    * The minimum invoice amount is 1 Stars — enforced by :func:`calc_price`.
    """
    price = calc_price(plan, promo)
    payload = build_invoice_payload(
        plan_id=plan.id,
        promo_id=promo.id if promo else None,
        inbound_id=int(inbound_id),
        sub_id=int(sub_id),
    )
    prices = [LabeledPrice(label=plan.title, amount=price.stars)]

    return await bot.send_invoice(
        chat_id=chat_id,
        title=_invoice_title(plan),
        description=_invoice_description(plan, price, promo, sub_id=int(sub_id)),
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=prices,
    )


async def send_gift_invoice(
    bot: Bot,
    chat_id: int,
    plan: Plan,
    promo: Promo | None,
    *,
    inbound_id: int,
) -> Message:
    """Send a Stars invoice that **buys a giftable code** for ``plan``.

    Identical pricing to :func:`send_invoice` (so any promo discount applies to
    the gift's price), but the payload is built by :func:`build_gift_payload`
    with ``kind="gift"`` / ``gift=1`` so the ``successful_payment`` handler mints
    a gift code instead of provisioning the buyer a subscription. A gift always
    creates a brand-new subscription for the recipient (no ``sub_id`` /
    extend semantics) so none is threaded.
    """
    price = calc_price(plan, promo)
    payload = build_gift_payload(
        plan_id=plan.id,
        inbound_id=int(inbound_id),
        promo_id=promo.id if promo else None,
    )
    prices = [LabeledPrice(label=plan.title, amount=price.stars)]
    return await bot.send_invoice(
        chat_id=chat_id,
        title=_invoice_title(plan),
        description=_invoice_description(plan, price, promo, sub_id=0),
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=prices,
    )


async def send_topup_invoice(
    bot: Bot,
    chat_id: int,
    stars: int,
    *,
    lang: str = DEFAULT_LANG,
) -> Message:
    """Send a Stars invoice that **tops up the user's wallet balance**.

    Unlike :func:`send_invoice` (which buys a plan), a top-up carries no plan /
    inbound — only the Stars amount to credit. The payload is built by
    :func:`build_topup_payload` with ``kind="topup"`` so the
    ``successful_payment`` handler routes into the wallet-credit branch
    (:func:`app.handlers.user.buy.on_successful_payment`).

    ``stars`` must be ``>= _STARS_MIN`` (Telegram rejects 0-Stars invoices);
    :func:`build_topup_payload` enforces this and raises :class:`ValueError`
    otherwise. The single :class:`LabeledPrice` line equals ``stars`` so the
    user is charged exactly the amount credited.

    Title / description are localized via :func:`app.i18n.t` (``wallet.*``).
    """
    stars = max(_STARS_MIN, int(stars))
    payload = build_topup_payload(stars)
    prices = [LabeledPrice(label=t("wallet.invoice_label", lang), amount=stars)]
    return await bot.send_invoice(
        chat_id=chat_id,
        title=t("wallet.invoice_title", lang),
        description=t("wallet.invoice_description", lang, stars=stars),
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=prices,
    )


def build_subscription_payload(
    plan_id: int,
    inbound_id: int,
    *,
    sub_id: int = 0,
) -> str:
    """Encode a native **Star-subscription** bootstrap payload (``kind="sub"``).

    A recurring Star subscription is created via
    :func:`create_subscription_invoice_link`; ``successful_payment`` then
    routes on ``kind="sub"`` to provision the subscription and persist the
    ``telegram_payment_charge_id`` needed to manage recurring billing
    (Phase 4). Promos do not apply to recurring subscriptions, so there is
    no ``"r"`` key.

    Schema::

        {"k": "sub", "p": <plan_id>, "i": <inbound_id>,
         "s": <sub_id_to_extend>}
    """
    obj: dict[str, object] = {
        "k": "sub",
        "p": int(plan_id),
        "i": int(inbound_id),
    }
    if sub_id:
        obj["s"] = int(sub_id)
    return _encode_payload(obj)


async def create_subscription_invoice_link(
    bot: Bot,
    plan: Plan,
    *,
    inbound_id: int,
    sub_id: int = 0,
) -> str:
    """Create a native recurring **Star subscription** invoice link.

    Unlike :func:`send_invoice` (a one-off charge), this uses
    :meth:`aiogram.Bot.create_invoice_link` with ``subscription_period``
    set so Telegram bills the user every 30 days automatically until they
    cancel. The returned URL is attached to a button the user taps to
    subscribe.

    Telegram constraints (enforced here):

    * ``currency='XTR'`` — Stars.
    * ``provider_token=''`` — required (empty) for Stars.
    * ``subscription_period`` **must** be exactly
      :data:`SUBSCRIPTION_PERIOD_SECONDS` (2_592_000 s = 30 days); any
      other value is rejected by the Bot API. This parameter exists *only*
      on ``create_invoice_link``, never on ``send_invoice``.
    * Promos are not applied to recurring subscriptions — the user pays the
      plan's full Stars price each period.

    ``sub_id`` is threaded into the payload (``0`` = new subscription) for
    the ``successful_payment`` / recurring-charge handling in Phase 4.
    """
    payload = build_subscription_payload(
        plan_id=plan.id,
        inbound_id=int(inbound_id),
        sub_id=int(sub_id),
    )
    stars = max(_STARS_MIN, int(plan.price_stars))
    prices = [LabeledPrice(label=plan.title, amount=stars)]

    return await bot.create_invoice_link(
        title=_invoice_title(plan),
        description=_invoice_description(plan, calc_price(plan, None), None, sub_id=int(sub_id)),
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=prices,
        subscription_period=SUBSCRIPTION_PERIOD_SECONDS,
    )


__all__ = [
    "SUBSCRIPTION_PERIOD_SECONDS",
    "InvoiceContext",
    "InvoiceKind",
    "InvoicePrice",
    "build_gift_payload",
    "build_invoice_payload",
    "build_subscription_payload",
    "build_topup_payload",
    "calc_price",
    "create_subscription_invoice_link",
    "parse_invoice_payload",
    "send_gift_invoice",
    "send_invoice",
    "send_topup_invoice",
]
