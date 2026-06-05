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
from app.i18n import DEFAULT_LANG, LANG_NAMES, SUPPORTED_LANGS, t
from app.services.health import get_cached_status
from app.services.inbounds import InboundOption


def location_indicator(lang: str = DEFAULT_LANG) -> str:
    """Return the 🟢/🔴/⚪ availability indicator for the panel locations.

    Reads the process-local health snapshot
    (:func:`app.services.health.get_cached_status`) refreshed by the
    scheduler's ``health_check_job``: ``'up'`` → 🟢, ``'down'`` → 🔴,
    ``None`` (no probe yet) → ⚪ (neutral / unknown). Synchronous and cheap so
    keyboards can call it inline while building a markup, without hitting the
    panel.
    """
    status = get_cached_status()
    if status == "up":
        return t("location.indicator_up", lang)
    if status == "down":
        return t("location.indicator_down", lang)
    return t("health.status_unknown", lang).split()[0]


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
    gift: int = 0


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


class LangCB(CallbackData, prefix="lng"):
    """Language picker callbacks.

    ``action``:
    * ``open`` — open the language menu (from the «🌐 Язык / Language»
      button in :func:`user_main_menu`). ``lang`` is unused.
    * ``set``  — apply the language carried in ``lang`` (one of
      :data:`app.i18n.SUPPORTED_LANGS`), persist it and re-render the menu.

    ``lang`` is the two-letter target language code (empty for ``open``).
    """

    action: str  # open | set
    lang: str = ""


class WalletCB(CallbackData, prefix="uw"):
    """Wallet-screen callbacks.

    ``action``:
    * ``open``  — open the «👛 Кошелёк» screen (balance + history). Reached from
      the main-menu button or as a "back" target after a top-up prompt.
    * ``topup`` — show the top-up preset menu (list of
      :data:`app.config.settings.WALLET_TOPUP_PRESETS` amounts).
    * ``pick``  — the user tapped a preset amount (``stars``): send a Stars
      top-up invoice via :func:`app.services.billing.send_topup_invoice`.

    ``stars`` carries the chosen preset amount (``0`` for ``open`` / ``topup``).
    """

    action: str  # open | topup | pick
    stars: int = 0


class TrialCB(CallbackData, prefix="ut"):
    """Free-trial flow callbacks.

    ``action``:
    * ``open`` — entry point («🎁 Пробный период») — start the trial wizard
      (enter :class:`app.states.user.TrialFlow.choosing_inbound`).

    Inbound selection reuses the shared :class:`InboundCB` factory (filtered on
    ``TrialFlow.choosing_inbound`` so it doesn't collide with the buy / promo
    inbound steps).
    """

    action: str  # open


class ReferralCB(CallbackData, prefix="ur"):
    """Referral («👥 Пригласить друга») screen callbacks.

    ``action``:
    * ``open`` — render the referral screen (invite link + invited-friends
      counter).
    """

    action: str  # open


class GiftCB(CallbackData, prefix="ug"):
    """Gift-flow callbacks.

    ``action``:
    * ``buy``    — start the "buy a gift" wizard (reuses the buy plan→inbound
      wizard with the ``gift`` flag set on :class:`BuyCB`).
    * ``redeem`` — enter :class:`app.states.user.GiftRedeem.waiting_code` and
      prompt the recipient to type a ``GIFT-…`` code.
    """

    action: str  # buy | redeem


class SupportCB(CallbackData, prefix="usup"):
    """Support («❓ Поддержка») flow callbacks.

    ``action``:
    * ``open`` — open the support screen and start the
      :class:`app.states.user.SupportFlow.writing` state so the user's next
      message is captured as a ticket message.
    """

    action: str  # open


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


def user_main_menu(
    *,
    has_subscription: bool,
    can_trial: bool = False,
    lang: str = DEFAULT_LANG,
) -> InlineKeyboardMarkup:
    """Top-level menu shown after ``/start`` and ``/menu``.

    When the user already has an active subscription the «Моя подписка»
    button is shown first; otherwise «Купить» takes the leading spot. Both
    buttons are always present so the layout stays predictable — the
    ``has_subscription`` flag only reorders them.

    The «🎁 Пробный период» button is shown **only** when ``can_trial`` is
    ``True`` — the caller computes this as ``settings.TRIAL_DAYS > 0 AND NOT
    has_trial(user)`` so the trial offer is hidden once the feature is disabled
    or the user has already claimed it. The growth buttons «👥 Пригласить
    друга», «🎁 Подарить подписку» and «🎁 У меня есть подарок» are always
    present (they self-gate at the handler layer when their feature is off).

    A trailing «🌐 Язык / Language» button opens the language picker. Labels are
    localized via :func:`app.i18n.t` (``lang`` defaults to Russian).
    """
    builder = InlineKeyboardBuilder()
    if has_subscription:
        builder.button(text=t("menu.btn_my", lang), callback_data=UserCB(area="my"))
        builder.button(text=t("menu.btn_buy", lang), callback_data=BuyCB(action="open"))
    else:
        builder.button(text=t("menu.btn_buy", lang), callback_data=BuyCB(action="open"))
        builder.button(text=t("menu.btn_my", lang), callback_data=UserCB(area="my"))
    if can_trial:
        builder.button(
            text=t("trial.btn", lang),
            callback_data=TrialCB(action="open"),
        )
    builder.button(
        text=t("wallet.btn_open", lang),
        callback_data=WalletCB(action="open"),
    )
    builder.button(
        text=t("menu.btn_promo", lang),
        callback_data=PromoActCB(action="open"),
    )
    builder.button(
        text=t("referral.btn", lang),
        callback_data=ReferralCB(action="open"),
    )
    builder.button(
        text=t("gift.btn_buy", lang),
        callback_data=GiftCB(action="buy"),
    )
    builder.button(
        text=t("gift.btn_redeem", lang),
        callback_data=GiftCB(action="redeem"),
    )
    builder.button(
        text=t("support.btn", lang),
        callback_data=SupportCB(action="open"),
    )
    builder.button(text=t("menu.btn_help", lang), callback_data=UserCB(area="help"))
    builder.button(text=t("menu.btn_lang", lang), callback_data=LangCB(action="open"))
    builder.adjust(1)
    return builder.as_markup()


def back_to_menu_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Single «◀ В меню» button — used as a fallback footer keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("menu.btn_back", lang), callback_data=UserCB(area="menu"))
    return builder.as_markup()


def cancel_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Single «✖ Отмена» button — cancels any active FSM wizard."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("menu.btn_cancel", lang), callback_data=UserCB(area="cancel"))
    return builder.as_markup()


def plans_kb(plans: Sequence[Plan], lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Plan list shown to the user when buying.

    Each row is a single plan button labelled ``<title> · <days>д · <price>⭐``.
    A trailing «◀ В меню» button lets the user back out of the wizard.
    """
    builder = InlineKeyboardBuilder()
    for plan in plans:
        builder.button(
            text=t(
                "kb.plan_label",
                lang,
                title=plan.title,
                days=plan.days,
                price=plan.price_stars,
            ),
            callback_data=BuyCB(action="plan", plan_id=plan.id),
        )
    builder.button(text=t("menu.btn_back", lang), callback_data=UserCB(area="menu"))
    builder.adjust(1)
    return builder.as_markup()


def inbound_select_kb(
    plan_id: int,
    options: Sequence[InboundOption],
    promo_id: int = 0,
    lang: str = DEFAULT_LANG,
) -> InlineKeyboardMarkup:
    """Single-select keyboard for choosing an inbound (server) during the
    buy flow (``plan_id`` > 0) or the free-days promo flow
    (``plan_id`` = 0, ``promo_id`` > 0).

    Each row is one inbound labelled ``<indicator> <remark> (port <port>)``
    where ``<indicator>`` is the panel availability marker (🟢/🔴/⚪) from
    :func:`location_indicator` (driven by the scheduler health-check) and
    ``<remark>`` falls back to ``Локация #<id>`` when the panel returns an
    empty remark. Tapping a row sends :class:`InboundCB` ``action='pick'``
    with the chosen ``inbound_id`` plus the current ``plan_id`` /
    ``promo_id`` so the handler can route the wizard. A trailing «← Назад»
    row sends ``InboundCB(action='back', ...)`` and returns the user to the
    previous step.
    """
    indicator = location_indicator(lang)
    builder = InlineKeyboardBuilder()
    for option in options:
        remark = option.remark or t("kb.inbound_fallback_remark", lang, id=option.id)
        builder.button(
            text=t(
                "location.label_with_port",
                lang,
                indicator=indicator,
                remark=remark,
                port=option.port,
            ),
            callback_data=InboundCB(
                action="pick",
                plan_id=plan_id,
                promo_id=promo_id,
                inbound_id=option.id,
            ),
        )
    builder.button(
        text=t("menu.btn_back_short", lang),
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
    can_pay_from_balance: bool = False,
    gift: int = 0,
    offer_subscription: bool = False,
    lang: str = DEFAULT_LANG,
) -> InlineKeyboardMarkup:
    """Confirmation keyboard shown after a plan (and inbound) were picked.

    Contains «Оплатить», «Применить промокод» (only when no promo is
    currently attached), and «Отмена». The selected ``inbound_id`` is
    threaded through into :class:`BuyCB` ``action='confirm'`` so the
    Stars-invoice payload built downstream can pin the subscription to
    the right server. ``sub_id`` is similarly threaded so the
    "extend existing sub #N" intent survives the round-trip through
    Telegram (the FSM may be cleared between confirm and payment).

    ``gift`` (``1`` for a gift purchase) is threaded through every
    :class:`BuyCB` so the confirm handler knows to mint a gift code rather than
    provision the buyer a subscription. A gift purchase **hides** the
    «💰 Оплатить с баланса» button (gifts are paid via a Telegram Stars invoice
    so the recipient's redemption is decoupled from the buyer's wallet).

    When ``can_pay_from_balance`` is ``True`` (and not a gift) an extra
    «💰 Оплатить с баланса» button is shown.

    When ``offer_subscription`` is ``True`` an extra «🔁 Подписка
    (автопродление)» button (``BuyCB(action='sub')``) is shown — the caller sets
    this only for an eligible plan (``plan.days ==
    settings.STAR_SUBSCRIPTION_PLAN_DAYS``) on a brand-new, non-gift purchase, so
    the user can opt into a native recurring Telegram Star subscription instead
    of a one-off charge.
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("kb.btn_pay", lang),
        callback_data=BuyCB(
            action="confirm",
            plan_id=plan_id,
            promo_id=promo_id,
            inbound_id=inbound_id,
            sub_id=sub_id,
            gift=gift,
        ),
    )
    if can_pay_from_balance and not gift:
        builder.button(
            text=t("wallet.pay_from_balance", lang),
            callback_data=BuyCB(
                action="balance",
                plan_id=plan_id,
                promo_id=promo_id,
                inbound_id=inbound_id,
                sub_id=sub_id,
            ),
        )
    if offer_subscription and not gift and sub_id == 0:
        builder.button(
            text=t("autorenew.btn_subscribe", lang),
            callback_data=BuyCB(
                action="sub",
                plan_id=plan_id,
                inbound_id=inbound_id,
            ),
        )
    if promo_id == 0:
        builder.button(
            text=t("kb.btn_apply_promo", lang),
            callback_data=BuyCB(
                action="apply_promo",
                plan_id=plan_id,
                inbound_id=inbound_id,
                sub_id=sub_id,
                gift=gift,
            ),
        )
    builder.button(text=t("menu.btn_cancel", lang), callback_data=UserCB(area="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def buy_action_kb(
    active_subs: Sequence[Subscription],
    inbound_remarks: dict[int, str],
    lang: str = DEFAULT_LANG,
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
            text=t("kb.btn_extend_sub", lang, sub_id=sub.id, remark=remark),
            callback_data=BuyCB(action="extend", sub_id=sub.id),
        )
    builder.button(
        text=t("kb.btn_new_sub", lang),
        callback_data=BuyCB(action="new"),
    )
    builder.button(text=t("kb.btn_cancel_back", lang), callback_data=UserCB(area="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def promo_action_kb(
    active_subs: Sequence[Subscription],
    inbound_remarks: dict[int, str],
    lang: str = DEFAULT_LANG,
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
            text=t("kb.btn_extend_sub", lang, sub_id=sub.id, remark=remark),
            callback_data=PromoActCB(action="extend", sub_id=sub.id),
        )
    builder.button(
        text=t("kb.btn_new_sub", lang),
        callback_data=PromoActCB(action="new"),
    )
    builder.button(text=t("kb.btn_cancel_back", lang), callback_data=UserCB(area="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def subscription_kb(sub_id: int, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Subscription card keyboard: re-send keys / back to menu."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("kb.btn_resend_key", lang),
        callback_data=SubCB(action="keys", sub_id=sub_id),
    )
    builder.button(text=t("menu.btn_back", lang), callback_data=UserCB(area="menu"))
    builder.adjust(1)
    return builder.as_markup()


def subscription_link_kb(
    url: str, lang: str = DEFAULT_LANG
) -> InlineKeyboardMarkup:
    """Single URL button opening a native Telegram Star subscription invoice.

    Native recurring Star subscriptions are created via
    :func:`app.services.billing.create_subscription_invoice_link` which returns
    a ``https://t.me/...`` invoice URL — Telegram only accepts a recurring
    subscription through such an invoice **link** (not ``send_invoice``). The URL
    is attached as a :class:`aiogram.types.InlineKeyboardButton` ``url=`` button
    the user taps to subscribe.
    """
    from aiogram.types import InlineKeyboardButton

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t("autorenew.btn_subscribe", lang), url=url)
    )
    builder.row(
        InlineKeyboardButton(
            text=t("menu.btn_back", lang),
            callback_data=UserCB(area="menu").pack(),
        )
    )
    return builder.as_markup()


def renew_reminder_kb(
    sub_id: int, lang: str = DEFAULT_LANG
) -> InlineKeyboardMarkup:
    """Single «🔁 Продлить в 1 тап» button for expiry reminders.

    Attached by :func:`app.scheduler.reminders_job` to the 3d / 1d / 0d
    reminder messages. Tapping it sends ``BuyCB(action='extend', sub_id=<id>)``
    — the very same callback the «Моя подписка» card uses — which routes into
    the existing extend flow (:func:`app.handlers.user.buy.cb_pick_action_extend`)
    pre-pinned to the about-to-expire subscription, letting the user renew
    without re-navigating the menu.
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("reminder.btn_renew", lang),
        callback_data=BuyCB(action="extend", sub_id=int(sub_id)),
    )
    builder.adjust(1)
    return builder.as_markup()


def language_menu_kb(current: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Language picker keyboard listing every supported language.

    One row per language from :data:`app.i18n.SUPPORTED_LANGS`, labelled with
    its self-describing :data:`app.i18n.LANG_NAMES` entry. The user's currently
    selected language (``current``) is prefixed with a ``✅`` check mark so the
    active choice is obvious. Tapping a row sends ``LangCB(action='set',
    lang=<code>)``. A trailing «◀ В меню» row returns to the main menu.
    """
    builder = InlineKeyboardBuilder()
    for code in SUPPORTED_LANGS:
        name = LANG_NAMES.get(code, code)
        label = f"✅ {name}" if code == current else name
        builder.button(text=label, callback_data=LangCB(action="set", lang=code))
    builder.button(
        text=t("menu.btn_back", current), callback_data=UserCB(area="menu")
    )
    builder.adjust(1)
    return builder.as_markup()


def wallet_screen_kb(
    *, has_presets: bool, lang: str = DEFAULT_LANG
) -> InlineKeyboardMarkup:
    """Keyboard for the «👛 Кошелёк» screen.

    Shows a «➕ Пополнить» button (only when ``has_presets`` — i.e.
    :data:`app.config.settings.WALLET_TOPUP_PRESETS` is non-empty) that opens the
    top-up preset menu, followed by «◀ В меню».
    """
    builder = InlineKeyboardBuilder()
    if has_presets:
        builder.button(
            text=t("wallet.btn_topup", lang),
            callback_data=WalletCB(action="topup"),
        )
    builder.button(text=t("menu.btn_back", lang), callback_data=UserCB(area="menu"))
    builder.adjust(1)
    return builder.as_markup()


def wallet_topup_kb(
    presets: Sequence[int], lang: str = DEFAULT_LANG
) -> InlineKeyboardMarkup:
    """Top-up preset menu — one button per Stars amount + a «◀ Назад» row.

    Each preset button carries :class:`WalletCB` ``action='pick'`` with the
    chosen ``stars`` amount; tapping it sends a Stars top-up invoice. The back
    button returns to the wallet screen (``WalletCB(action='open')``).
    """
    builder = InlineKeyboardBuilder()
    for stars in presets:
        builder.button(
            text=t("wallet.btn_topup_preset", lang, stars=stars),
            callback_data=WalletCB(action="pick", stars=int(stars)),
        )
    builder.button(
        text=t("menu.btn_back_short", lang),
        callback_data=WalletCB(action="open"),
    )
    builder.adjust(1)
    return builder.as_markup()


__all__ = [
    "BuyCB",
    "GiftCB",
    "InboundCB",
    "LangCB",
    "PromoActCB",
    "ReferralCB",
    "SubCB",
    "SupportCB",
    "TrialCB",
    "UserCB",
    "WalletCB",
    "back_to_menu_kb",
    "buy_action_kb",
    "cancel_kb",
    "confirm_kb",
    "inbound_select_kb",
    "language_menu_kb",
    "location_indicator",
    "plans_kb",
    "promo_action_kb",
    "renew_reminder_kb",
    "subscription_kb",
    "subscription_link_kb",
    "user_main_menu",
    "wallet_screen_kb",
    "wallet_topup_kb",
]
