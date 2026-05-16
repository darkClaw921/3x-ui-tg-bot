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
  optional ``plan_id`` / ``promo_id``).
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


# ---------------------------------------------------------------------------
# Callback factories
# ---------------------------------------------------------------------------


class UserCB(CallbackData, prefix="u"):
    """Top-level user navigation: menu / help / my subscription / cancel."""

    area: str  # menu | help | my | cancel


class BuyCB(CallbackData, prefix="ub"):
    """Buy-flow callbacks.

    ``action``:
    * ``open``         — entry point ("Купить") — show plan list.
    * ``plan``         — a plan was picked (id in ``plan_id``).
    * ``apply_promo``  — user wants to type a promo code.
    * ``confirm``      — proceed to the Stars invoice.
    * ``cancel``       — abort the wizard and return to the main menu.
    """

    action: str
    plan_id: int = 0
    promo_id: int = 0


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
    * ``cancel`` — abort and return to the main menu.
    """

    action: str


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


def confirm_kb(plan_id: int, promo_id: int = 0) -> InlineKeyboardMarkup:
    """Confirmation keyboard shown after a plan was picked.

    Contains «Оплатить», «Применить промокод» (only when no promo is
    currently attached), and «Отмена».
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="💳 Оплатить",
        callback_data=BuyCB(action="confirm", plan_id=plan_id, promo_id=promo_id),
    )
    if promo_id == 0:
        builder.button(
            text="🎟 Применить промокод",
            callback_data=BuyCB(action="apply_promo", plan_id=plan_id),
        )
    builder.button(text="✖ Отмена", callback_data=UserCB(area="cancel"))
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
    "PromoActCB",
    "SubCB",
    "UserCB",
    "back_to_menu_kb",
    "cancel_kb",
    "confirm_kb",
    "plans_kb",
    "subscription_kb",
    "user_main_menu",
]
