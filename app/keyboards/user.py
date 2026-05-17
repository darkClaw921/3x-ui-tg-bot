"""Inline keyboards for the user-facing flow.

Every keyboard is a thin builder around :class:`InlineKeyboardBuilder` and
returns a ready-to-send :class:`InlineKeyboardMarkup`. Callback payloads
are encoded via :class:`aiogram.filters.callback_data.CallbackData`
factories declared at the top of this module — keeping the wire format
short (<=64 bytes, Telegram's hard limit) and giving handlers a typed view
of the payload through the ``F`` filter and the
``callback_data: UserCB`` injected parameter.

Callback namespaces
-------------------

* ``UserCB`` — top-level navigation (``area=menu|help|my|cancel``).
* ``BuyCB`` — buy-flow actions (``action=open|plan|apply_promo|confirm|cancel``,
  optional ``plan_id`` / ``promo_id`` / ``inbound_id``).
* ``InboundCB`` — inbound selection step (``action=pick|back`` with
  ``plan_id`` / ``promo_id`` / ``inbound_id``); used by both the buy
  flow and the free-days promo flow.
* ``SubCB`` — actions over an existing subscription (``action=keys|back``,
  optional ``sub_id``).
* ``PromoCB`` — standalone promo activation (``action=open|cancel``).
"""

from __future__ import annotations

from collections.abc import Sequence

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.repos.plans import Plan
from app.db.repos.subscriptions import Subscription
from app.services.inbounds import InboundOption


# ---------------------------------------------------------------------------
# Callback factories
# ---------------------------------------------------------------------------


class UserCB(CallbackData, prefix="u"):
    """Top-level user navigation: menu / help / my subscription / cancel."""

    area: str  # menu | help | my | cancel


class BuyCB(CallbackData, prefix="ub"):
    """Buy-flow callbacks.

    ``action``:
    * ``open``         — entry point ("Купить") — show plan list or the
      "продлить vs новая" action screen when the user already has at
      least one active subscription.
    * ``extend``       — user picked "🔄 Продлить #N" from the action
      screen (or directly from a subscription card in
      :mod:`app.handlers.user.my_subscription`); ``sub_id`` identifies
      the subscription whose expiry will be pushed forward.
    * ``new``          — user picked "🆕 Новая подписка" — proceed with a
      regular new-subscription buy flow (``sub_id`` stays ``0``).
    * ``plan``         — a plan was picked (id in ``plan_id``).
    * ``apply_promo``  — user wants to type a promo code.
    * ``confirm``      — proceed to the Stars invoice; the chosen
      inbound is carried in ``inbound_id`` (``0`` when the plan has a
      single inbound and the wizard auto-skipped the select step).
      ``sub_id`` > 0 signals "extend the existing subscription #N"
      instead of provisioning a brand-new one.
    * ``cancel``       — abort the wizard and return to the main menu.

    ``sub_id``:
    * ``0`` (default) — create a new subscription.
    * ``>0``          — extend the subscription with this id. The
      inbound is then inherited from the existing sub and the allow-list
      check is skipped (an existing sub may live on an inbound that is
      no longer attached to any plan).
    """

    action: str
    plan_id: int = 0
    promo_id: int = 0
    inbound_id: int = 0
    sub_id: int = 0


class InboundCB(CallbackData, prefix="inb"):
    """Inbound selection step (shared by buy + free-days promo flows).

    ``action``:
    * ``pick`` — user picked a specific inbound (``inbound_id``).
      ``plan_id`` is non-zero for the buy flow and ``promo_id`` is
      non-zero for the standalone promo flow — handlers route on
      whichever is set.
    * ``back`` — return to the previous step (plan list for the buy
      flow, promo entry for the promo flow). ``inbound_id`` is unused.
    """

    action: str
    plan_id: int = 0
    promo_id: int = 0
    inbound_id: int = 0


class SubCB(CallbackData, prefix="us"):
    """Actions over an existing subscription card.

    ``action``:
    * ``keys`` — re-send vless + QR + subscription URL.
    * ``back`` — return to the user main menu.
    """

    action: str
    sub_id: int = 0


class PromoActCB(CallbackData, prefix="up"):
    """Standalone promo activation (free-days flow).

    ``action``:
    * ``open``   — entry point ("Активировать промокод").
    * ``extend`` — user picked "🔄 Продлить #N" from the action screen
      shown when the free-days promo could attach to an existing
      subscription instead of provisioning a new one; ``sub_id``
      identifies the subscription whose expiry will be pushed forward.
    * ``new``    — user picked "🆕 Новая подписка" — proceed with the
      regular inbound-selection step (``sub_id`` stays ``0``).
    * ``cancel`` — abort and return to the main menu.

    ``inbound_id``:
    * ``0`` (default) — unused for the ``open`` / ``extend`` / ``new`` /
      ``cancel`` callbacks; reserved for future flows.

    ``sub_id``:
    * ``0`` (default) — create a new subscription (or n/a).
    * ``>0``          — extend the subscription with this id. The
      inbound is inherited from the existing sub and the allow-list
      check is skipped (an existing sub may live on an inbound that is
      no longer attached to any plan).
    """

    action: str
    inbound_id: int = 0
    sub_id: int = 0


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------


def user_main_menu(*, has_subscription: bool) -> InlineKeyboardMarkup:
    """Top-level menu shown after ``/start`` and ``/menu``.

    When the user already has an active subscription the «Моя подписка»
    button is shown first; otherwise «Купить» takes the leading spot. Both
    buttons are always present so the layout stays predictable — the
    ``has_subscription`` flag only reorders them.
    """
    builder = InlineKeyboardBuilder()
    if has_subscription:
        builder.button(text="📦 Моя подписка", callback_data=UserCB(area="my"))
        builder.button(text="🛒 Купить", callback_data=BuyCB(action="open"))
    else:
        builder.button(text="🛒 Купить", callback_data=BuyCB(action="open"))
        builder.button(text="📦 Моя подписка", callback_data=UserCB(area="my"))
    builder.button(
        text="🎟 Активировать промокод",
        callback_data=PromoActCB(action="open"),
    )
    builder.button(text="❓ Помощь", callback_data=UserCB(area="help"))
    builder.adjust(1)
    return builder.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    """Single «◀ В меню» button — used as a fallback footer keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="◀ В меню", callback_data=UserCB(area="menu"))
    return builder.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    """Single «✖ Отмена» button — cancels any active FSM wizard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✖ Отмена", callback_data=UserCB(area="cancel"))
    return builder.as_markup()


def plans_kb(plans: Sequence[Plan]) -> InlineKeyboardMarkup:
    """Plan list shown to the user when buying.

    Each row is a single plan button labelled ``<title> · <days>д · <price>⭐``.
    A trailing «◀ В меню» button lets the user back out of the wizard.
    """
    builder = InlineKeyboardBuilder()
    for plan in plans:
        builder.button(
            text=f"{plan.title} · {plan.days}д · {plan.price_stars}⭐",
            callback_data=BuyCB(action="plan", plan_id=plan.id),
        )
    builder.button(text="◀ В меню", callback_data=UserCB(area="menu"))
    builder.adjust(1)
    return builder.as_markup()


def inbound_select_kb(
    plan_id: int,
    options: Sequence[InboundOption],
    promo_id: int = 0,
) -> InlineKeyboardMarkup:
    """Single-select keyboard for choosing an inbound (server) during the
    buy flow (``plan_id`` > 0) or the free-days promo flow
    (``plan_id`` = 0, ``promo_id`` > 0).

    Each row is one inbound labelled ``<remark> (port <port>)``; tapping
    it sends :class:`InboundCB` ``action='pick'`` with the chosen
    ``inbound_id`` plus the current ``plan_id`` / ``promo_id`` so the
    handler can route the wizard. A trailing «← Назад» row sends
    ``InboundCB(action='back', ...)`` and returns the user to the
    previous step.
    """
    builder = InlineKeyboardBuilder()
    for option in options:
        builder.button(
            text=f"{option.remark} (port {option.port})",
            callback_data=InboundCB(
                action="pick",
                plan_id=plan_id,
                promo_id=promo_id,
                inbound_id=option.id,
            ),
        )
    builder.button(
        text="◀ Назад",
        callback_data=InboundCB(action="back", plan_id=plan_id, promo_id=promo_id),
    )
    builder.adjust(1)
    return builder.as_markup()


def confirm_kb(
    plan_id: int,
    promo_id: int = 0,
    inbound_id: int = 0,
    *,
    sub_id: int = 0,
) -> InlineKeyboardMarkup:
    """Confirmation keyboard shown after a plan (and inbound) were picked.

    Contains «Оплатить», «Применить промокод» (only when no promo is
    currently attached), and «Отмена». The selected ``inbound_id`` is
    threaded through into :class:`BuyCB` ``action='confirm'`` so the
    Stars-invoice payload built downstream can pin the subscription to
    the right server. ``sub_id`` is similarly threaded so the
    "extend existing sub #N" intent survives the round-trip through
    Telegram (the FSM may be cleared between confirm and payment).
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="💳 Оплатить",
        callback_data=BuyCB(
            action="confirm",
            plan_id=plan_id,
            promo_id=promo_id,
            inbound_id=inbound_id,
            sub_id=sub_id,
        ),
    )
    if promo_id == 0:
        builder.button(
            text="🎟 Применить промокод",
            callback_data=BuyCB(
                action="apply_promo",
                plan_id=plan_id,
                inbound_id=inbound_id,
                sub_id=sub_id,
            ),
        )
    builder.button(text="✖ Отмена", callback_data=UserCB(area="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def buy_action_kb(
    active_subs: Sequence[Subscription],
    inbound_remarks: dict[int, str],
) -> InlineKeyboardMarkup:
    """Action-screen keyboard shown when the user already has active subs.

    One row per active subscription labelled ``🔄 Продлить #<id> · <remark>``
    (sending ``BuyCB(action='extend', sub_id=<id>)``), followed by a
    ``🆕 Новая подписка`` row (sending ``BuyCB(action='new')``) and a
    trailing ``◀ Отмена`` that re-uses the standard cancel callback.

    ``inbound_remarks`` is a ``{inbound_id: remark}`` mapping resolved
    from the cached panel inbound list — when a subscription's inbound
    is missing from the mapping (e.g. it was detached on the panel) we
    fall back to ``#<inbound_id>`` so the button still renders.
    """
    builder = InlineKeyboardBuilder()
    for sub in active_subs:
        remark = inbound_remarks.get(sub.xui_inbound_id) or f"#{sub.xui_inbound_id}"
        builder.button(
            text=f"🔄 Продлить #{sub.id} · {remark}",
            callback_data=BuyCB(action="extend", sub_id=sub.id),
        )
    builder.button(
        text="🆕 Новая подписка",
        callback_data=BuyCB(action="new"),
    )
    builder.button(text="◀ Отмена", callback_data=UserCB(area="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def promo_action_kb(
    active_subs: Sequence[Subscription],
    inbound_remarks: dict[int, str],
) -> InlineKeyboardMarkup:
    """Action-screen keyboard shown for ``free_days`` promos when the
    user already has active subscriptions.

    Mirrors :func:`buy_action_kb` but uses :class:`PromoActCB` callbacks
    so the promo router can pick them up under
    :class:`app.states.user.PromoActivate.choosing_action`. One row per
    active subscription labelled ``🔄 Продлить #<id> · <remark>`` (sending
    ``PromoActCB(action='extend', sub_id=<id>)``), followed by a
    ``🆕 Новая подписка`` row (sending ``PromoActCB(action='new')``) and a
    trailing ``◀ Отмена`` that re-uses the standard cancel callback.

    ``inbound_remarks`` is a ``{inbound_id: remark}`` mapping resolved
    from the cached panel inbound list — when a subscription's inbound
    is missing from the mapping (e.g. it was detached on the panel) we
    fall back to ``#<inbound_id>`` so the button still renders.
    """
    builder = InlineKeyboardBuilder()
    for sub in active_subs:
        remark = inbound_remarks.get(sub.xui_inbound_id) or f"#{sub.xui_inbound_id}"
        builder.button(
            text=f"🔄 Продлить #{sub.id} · {remark}",
            callback_data=PromoActCB(action="extend", sub_id=sub.id),
        )
    builder.button(
        text="🆕 Новая подписка",
        callback_data=PromoActCB(action="new"),
    )
    builder.button(text="◀ Отмена", callback_data=UserCB(area="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def subscription_kb(sub_id: int) -> InlineKeyboardMarkup:
    """Subscription card keyboard: re-send keys / back to menu."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔑 Получить ключ ещё раз",
        callback_data=SubCB(action="keys", sub_id=sub_id),
    )
    builder.button(text="◀ В меню", callback_data=UserCB(area="menu"))
    builder.adjust(1)
    return builder.as_markup()


__all__ = [
    "BuyCB",
    "InboundCB",
    "PromoActCB",
    "SubCB",
    "UserCB",
    "back_to_menu_kb",
    "buy_action_kb",
    "cancel_kb",
    "confirm_kb",
    "inbound_select_kb",
    "plans_kb",
    "promo_action_kb",
    "subscription_kb",
    "user_main_menu",
]
