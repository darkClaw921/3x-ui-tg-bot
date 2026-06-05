"""Buy-flow: plan selection → optional promo → Stars invoice →
pre_checkout → successful_payment.

Handlers
--------

UI callbacks (FSM-driven):
    * :func:`cb_open`         — ``BuyCB(action='open')``: show the plan list.
    * :func:`cb_pick_plan`    — ``BuyCB(action='plan', plan_id)``: store
      the selected plan, then either auto-skip the inbound step (single
      inbound) or enter ``BuyFlow.choosing_inbound`` (N>1 inbounds).
    * :func:`cb_pick_inbound` — ``InboundCB(action='pick', plan_id,
      promo_id, inbound_id)``: persist the chosen inbound and render
      the confirmation card.
    * :func:`cb_pick_inbound_back` — ``InboundCB(action='back', plan_id,
      promo_id)``: return to the plan list.
    * :func:`cb_apply_promo`  — ``BuyCB(action='apply_promo', plan_id,
      inbound_id)``: prompt the user for a promo code (preserving the
      pinned inbound).
    * :func:`msg_promo_code`  — message handler bound to
      :class:`BuyFlow.entering_promo`: validate the code and either go
      back to the confirmation card with a discount or re-prompt on error.
    * :func:`cb_confirm`      — ``BuyCB(action='confirm', plan_id,
      promo_id, inbound_id)``: build and send the Stars invoice
      (embedding ``inbound_id`` in the payload), then clear the FSM.

Payment callbacks (stateless — invoice payload carries the IDs):
    * :func:`on_pre_checkout`     — re-validates plan + promo and answers
      ``answer_pre_checkout_query``.
    * :func:`on_successful_payment` — idempotent finalisation:
      ``payments_repo.get_or_create`` → ``subscriptions.create_or_extend``
      → ``promos.apply`` (if promo) → deliver vless / QR / sub URL.

Idempotency
-----------

The :class:`successful_payment.telegram_payment_charge_id` is unique
across Telegram's universe and is enforced by a UNIQUE constraint on
``payments.telegram_charge_id``. If Telegram retries the update we
detect the duplicate (via the IntegrityError raised by
:func:`app.db.repos.payments.create`) and short-circuit without
re-creating a subscription.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import aiosqlite
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    Message,
    PreCheckoutQuery,
)
from loguru import logger

from app.config import settings
from app.db.engine import get_conn
from app.db.repos import payments as payments_repo
from app.db.repos import plans as plans_repo
from app.db.repos import promos as promos_repo
from app.db.repos import subscriptions as subs_repo
from app.db.repos import users as users_repo
from app.db.repos import wallet as wallet_repo
from app.db.repos.plans import Plan
from app.db.repos.promos import Promo
from app.db.repos.subscriptions import Subscription
from app.db.repos.users import User
from app.handlers.user._keys import deliver_keys
from app.i18n import DEFAULT_LANG, resolve_lang, t
from app.keyboards.user import (
    BuyCB,
    GiftCB,
    InboundCB,
    buy_action_kb,
    confirm_kb,
    inbound_select_kb,
    plans_kb,
    subscription_link_kb,
)
from app.bot_meta import get_bot_username
from app.services import (
    billing,
    gifts as gifts_service,
    promos as promos_service,
    referrals as referrals_service,
    subscriptions as subs_service,
    wallet as wallet_service,
)
from app.services.inbounds import InboundOption, list_user_inbounds
from app.states.user import BuyFlow
from app.xui import XuiError, get_xui_client
from app.xui.clients import update_client

router = Router(name="user_buy")


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #


def _format_confirm(
    plan: Plan,
    promo: Promo | None,
    inbound_remark: str | None = None,
    extending_sub: Subscription | None = None,
    lang: str = DEFAULT_LANG,
) -> str:
    """Render the confirmation card text (HTML).

    Shows the plan, the applied promo (if any), the chosen inbound
    (server) and the resulting price. The header explicitly states
    whether this is a brand-new subscription («🆕 Новая подписка на …»)
    or an extension of an existing one («🔄 Продление подписки #N · remark
    до DATE»). For the extend case ``inbound_remark`` should be the
    extending subscription's inbound remark so the user can verify they
    are extending the right server.

    The numbers come from :func:`app.services.billing.calc_price` so
    what the user sees matches what gets charged.
    """
    price = billing.calc_price(plan, promo)
    total_days = plan.days + (price.extra_days or 0)

    def _term_line() -> str:
        if price.extra_days:
            return t("buy.confirm_term_bonus", lang, days=plan.days, extra=price.extra_days)
        return t("buy.confirm_term", lang, days=plan.days)

    if extending_sub is not None:
        if inbound_remark:
            header = t(
                "buy.confirm_header_extend_remark",
                lang,
                sub_id=extending_sub.id,
                remark=inbound_remark,
            )
        else:
            header = t("buy.confirm_header_extend", lang, sub_id=extending_sub.id)
        new_expiry = _shift_expiry(extending_sub.expires_at, total_days)
        lines = [
            header,
            t("buy.confirm_plan", lang, title=plan.title),
            _term_line(),
            t("buy.confirm_valid_until", lang, date=new_expiry),
        ]
    else:
        if inbound_remark:
            header = t("buy.confirm_header_new_on", lang, remark=inbound_remark)
        else:
            header = t("buy.confirm_header_new", lang)
        lines = [
            header,
            t("buy.confirm_plan", lang, title=plan.title),
            _term_line(),
        ]
    if promo is not None:
        lines.append(t("buy.confirm_promo", lang, code=promo.code))
        if promo.type == "percent":
            lines.append(t("buy.confirm_discount_percent", lang, value=promo.value))
        elif promo.type == "flat_stars":
            lines.append(t("buy.confirm_discount_flat", lang, value=promo.value))
        elif promo.type == "free_days":
            lines.append(t("buy.confirm_bonus_days", lang, value=promo.value))
    lines.append("")
    lines.append(t("buy.confirm_total", lang, stars=price.stars))
    return "\n".join(lines)


def _shift_expiry(current_expires_at: str, plus_days: int) -> str:
    """Return ``current_expires_at + plus_days`` in YYYY-MM-DD format.

    Used by :func:`_format_confirm` for the "Действует до DATE" line on
    the extend confirmation card. Falls back to the raw string when the
    timestamp cannot be parsed (defensive — should never happen for a
    well-formed DB row).
    """
    from datetime import datetime, timedelta

    try:
        # Stored format: 'YYYY-MM-DD HH:MM:SS' (UTC, seconds resolution).
        dt = datetime.fromisoformat(str(current_expires_at).replace(" ", "T"))
    except ValueError:
        return str(current_expires_at)
    return (dt + timedelta(days=int(plus_days))).date().isoformat()


async def _fetch_plan(conn: aiosqlite.Connection, plan_id: int) -> Plan | None:
    """Convenience: get plan by id (no-op wrapper, kept for symmetry)."""
    return await plans_repo.get(conn, plan_id)


async def _fetch_promo(conn: aiosqlite.Connection, promo_id: int) -> Promo | None:
    """Convenience: get promo by id (no-op wrapper, kept for symmetry)."""
    return await promos_repo.get(conn, promo_id)


async def _can_pay_from_balance(
    user: User | None, plan: Plan, promo: Promo | None
) -> bool:
    """Return ``True`` iff the user's wallet balance covers the final price.

    The final Stars price is computed by :func:`app.services.billing.calc_price`
    (so any promo discount is reflected), then compared against the user's
    current ledger balance. Returns ``False`` when ``user`` is ``None`` (no
    registered account → no wallet) so the "pay from balance" button is hidden
    for anonymous users.
    """
    if user is None:
        return False
    price = billing.calc_price(plan, promo)
    async with get_conn() as conn:
        balance = await wallet_repo.balance(conn, user.id)
    return balance >= price.stars


def _plan_is_buyable(plan: Plan | None) -> bool:
    """Return ``True`` if a plan exists and is currently active."""
    return plan is not None and plan.is_active


def _offers_subscription(plan: Plan, *, sub_id: int, gift: int) -> bool:
    """Return ``True`` when the confirm card should offer a native Star subscription.

    A native recurring Telegram Star subscription is only offered for a
    brand-new, non-gift purchase of a plan whose length matches Telegram's
    fixed 30-day billing period (``settings.STAR_SUBSCRIPTION_PLAN_DAYS``), and
    only when the feature flag ``settings.AUTO_RENEW_ENABLED`` is on. Extends
    (``sub_id > 0``) and gifts are excluded — recurring billing always creates a
    fresh subscription for the buyer.
    """
    return (
        settings.AUTO_RENEW_ENABLED
        and not gift
        and int(sub_id) == 0
        and int(plan.days) == int(settings.STAR_SUBSCRIPTION_PLAN_DAYS)
    )


def _promo_is_usable(promo: Promo | None) -> bool:
    """Return ``True`` if a promo is non-expired and has capacity left.

    Mirrors the cheap checks inside :func:`app.services.promos.validate`
    but without the "already redeemed by this user" check — used in
    :func:`on_pre_checkout` where we accept the promo if it was valid
    when chosen even if its global state changed slightly (the
    one-per-user guarantee is enforced at redemption time by
    :func:`app.db.repos.promos.try_redeem`).
    """
    if promo is None:
        return False
    from datetime import UTC, datetime

    now = datetime.now(UTC).replace(microsecond=0).isoformat(sep=" ")
    if promo.expires_at is not None and promo.expires_at <= now:
        return False
    if promo.max_uses != 0 and promo.used_count >= promo.max_uses:
        return False
    return True


# ---------------------------------------------------------------------- #
# Plan selection
# ---------------------------------------------------------------------- #


@router.callback_query(BuyCB.filter(F.action == "open"))
async def cb_open(
    callback: CallbackQuery,
    state: FSMContext,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Entry point of the buy flow.

    When the user already has one or more active subscriptions, show the
    "продлить vs новая" action screen (:class:`BuyFlow.choosing_action`)
    so they can pick a specific subscription to extend. Otherwise fall
    through to the regular plan list (:class:`BuyFlow.choosing_plan`).

    The action-screen branch resolves each active sub's inbound remark
    via the cached :func:`app.services.inbounds.list_user_inbounds`
    helper — on a panel error the remarks fall back to ``#<inbound_id>``
    placeholders but the screen still renders so the user is not
    blocked from purchasing.
    """
    await state.clear()
    active: list[Subscription] = []
    if user is not None:
        async with get_conn() as conn:
            active = await subs_repo.list_active_for_user(conn, user.id)

    if active:
        # Action screen — resolve inbound remarks (best-effort).
        remarks: dict[int, str] = {}
        try:
            xui = await get_xui_client()
            options = await list_user_inbounds(xui)
            remarks = {o.id: o.remark or f"#{o.id}" for o in options}
        except XuiError as exc:
            logger.warning(
                "cb_open: list_user_inbounds failed, rendering action screen "
                "with raw inbound ids: {}",
                exc,
            )
        await state.set_state(BuyFlow.choosing_action)
        if callback.message is not None:
            await callback.message.edit_text(
                t("buy.has_active_choose", lang),
                reply_markup=buy_action_kb(active, remarks),
            )
        await callback.answer()
        return

    # No active subs — go straight to plan list.
    await state.set_state(BuyFlow.choosing_plan)
    async with get_conn() as conn:
        plans = await plans_repo.list_active(conn)
    if not plans:
        if callback.message is not None:
            await callback.message.edit_text(t("buy.no_plans", lang))
        await callback.answer()
        return
    if callback.message is not None:
        await callback.message.edit_text(
            t("buy.choose_plan", lang),
            reply_markup=plans_kb(plans),
        )
    await callback.answer()


@router.callback_query(GiftCB.filter(F.action == "buy"))
async def cb_gift_buy(
    callback: CallbackQuery,
    state: FSMContext,
    lang: str = DEFAULT_LANG,
) -> None:
    """Entry point of the **gift** purchase flow.

    A gift always provisions a brand-new subscription for the *recipient*, so it
    reuses the regular plan→inbound→confirm wizard with two FSM markers set:
    ``gift=1`` (mints a code instead of provisioning the buyer) and ``sub_id=0``
    (never an extend). The action screen (продлить vs новая) is intentionally
    skipped — there is nothing of the buyer's to extend when gifting.
    """
    await state.clear()
    await state.set_state(BuyFlow.choosing_plan)
    await state.update_data(gift=1, sub_id=0)
    async with get_conn() as conn:
        plans = await plans_repo.list_active(conn)
    if callback.message is None:
        await callback.answer()
        return
    if not plans:
        await callback.message.edit_text(t("buy.no_plans", lang))
        await callback.answer()
        return
    await callback.message.edit_text(
        t("buy.choose_plan", lang),
        reply_markup=plans_kb(plans),
    )
    await callback.answer()


async def _send_plan_list(
    callback: CallbackQuery,
    state: FSMContext,
    lang: str = DEFAULT_LANG,
) -> None:
    """Helper: enter :class:`BuyFlow.choosing_plan` and render plans_kb.

    Shared by :func:`cb_pick_action_extend` and :func:`cb_pick_action_new`
    so the action-screen → plan-list transition stays consistent.
    """
    await state.set_state(BuyFlow.choosing_plan)
    async with get_conn() as conn:
        plans = await plans_repo.list_active(conn)
    if callback.message is None:
        return
    if not plans:
        await callback.message.edit_text(t("buy.no_plans", lang))
        return
    await callback.message.edit_text(
        t("buy.choose_plan", lang),
        reply_markup=plans_kb(plans),
    )


# ---------------------------------------------------------------------- #
# Action picker (only shown when the user has 1+ active subscriptions)
# ---------------------------------------------------------------------- #


@router.callback_query(BuyCB.filter(F.action == "extend"))
async def cb_pick_action_extend(
    callback: CallbackQuery,
    callback_data: BuyCB,
    state: FSMContext,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """User picked "🔄 Продлить #N" — pin the sub_id and jump to plans.

    This handler is registered WITHOUT a state filter so it works both
    from the action screen (:class:`BuyFlow.choosing_action`) and as a
    standalone entry point from the «Моя подписка» card (Phase 4) where
    no FSM state has been set yet.

    Validates ownership defensively: even though the keyboard only
    surfaces the caller's own subscriptions, a stale keyboard or a hand-
    crafted callback from another chat must not allow extending a
    foreign sub. On a mismatch we ``answer`` with an alert and leave the
    FSM untouched.
    """
    if user is None:
        await callback.answer(t("buy.need_start", lang), show_alert=True)
        return
    sub_id = int(callback_data.sub_id or 0)
    if sub_id <= 0:
        await callback.answer(t("buy.no_sub_specified", lang), show_alert=True)
        return

    async with get_conn() as conn:
        sub = await subs_repo.get(conn, sub_id)
    if (
        sub is None
        or sub.user_id != user.id
        or sub.status != "active"
    ):
        await callback.answer(t("buy.sub_unavailable_extend", lang), show_alert=True)
        return

    await state.update_data(
        sub_id=sub.id,
        inbound_id=int(sub.xui_inbound_id),
        # Wipe any stale plan/promo from a previous attempt.
        plan_id=0,
        promo_id=0,
        inbound_options=None,
    )
    await _send_plan_list(callback, state, lang)
    await callback.answer()


@router.callback_query(BuyCB.filter(F.action == "new"))
async def cb_pick_action_new(
    callback: CallbackQuery,
    state: FSMContext,
    lang: str = DEFAULT_LANG,
) -> None:
    """User picked "🆕 Новая подписка" — clear FSM and show plans.

    Registered without a state filter so it can be invoked both from the
    action screen and (for symmetry with ``cb_pick_action_extend``) from
    other entry points that want to force "new sub" semantics.
    """
    await state.clear()
    await state.update_data(sub_id=0)
    await _send_plan_list(callback, state, lang)
    await callback.answer()


def _remark_for(options: list[InboundOption] | list[dict], inbound_id: int) -> str:
    """Return the user-facing remark of ``inbound_id`` from ``options``.

    Accepts either a list of :class:`InboundOption` (in-memory) or a
    list of plain dicts (after a round-trip through the FSM, where
    aiogram serialises dataclasses to dicts). Falls back to a
    placeholder when the inbound is not found in the supplied options.
    """
    for opt in options:
        if isinstance(opt, InboundOption):
            if opt.id == inbound_id:
                return opt.remark or f"#{inbound_id}"
        else:
            if int(opt.get("id", 0)) == inbound_id:
                return str(opt.get("remark") or f"#{inbound_id}")
    return f"#{inbound_id}"


def _options_to_jsonable(options: list[InboundOption]) -> list[dict]:
    """Serialise :class:`InboundOption` for FSM storage.

    aiogram's FSM storage round-trips data through JSON, so frozen
    dataclasses must be flattened to plain dicts before being stashed.
    """
    return [
        {"id": o.id, "remark": o.remark, "port": o.port, "enabled": o.enabled}
        for o in options
    ]


def _jsonable_to_options(items: list[dict]) -> list[InboundOption]:
    """Inverse of :func:`_options_to_jsonable`."""
    return [
        InboundOption(
            id=int(it["id"]),
            remark=str(it.get("remark") or ""),
            port=int(it.get("port") or 0),
            enabled=bool(it.get("enabled", True)),
        )
        for it in items
    ]


@router.callback_query(BuyCB.filter(F.action == "plan"))
async def cb_pick_plan(
    callback: CallbackQuery,
    callback_data: BuyCB,
    state: FSMContext,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Store the chosen plan and route to the next step in the wizard.

    Routing:

    * ``sub_id > 0`` in the FSM (extend flow) → always skip the inbound
      selection step (the inbound is inherited from the existing
      subscription, even for multi-inbound plans); jump straight to
      ``BuyFlow.confirming`` with the extend-aware confirmation card.
    * Plan has **exactly one** inbound → skip the selection step,
      store the only ``inbound_id`` in the FSM and jump straight to
      ``BuyFlow.confirming`` with the confirmation card.
    * Plan has **N>1 inbounds** → fetch the panel's inbound list
      (cached via :func:`app.services.inbounds.list_user_inbounds`),
      intersect with the plan's allow-list, stash the options in the
      FSM and enter ``BuyFlow.choosing_inbound`` with a selection
      keyboard.
    * Plan has **zero inbounds** (misconfiguration) or the panel call
      fails — show an alert and stay on the previous step.

    Preserves any ``promo_id`` already stored in the FSM (so re-picking
    the same plan after applying a promo does not drop the discount).
    """
    plan_id = callback_data.plan_id
    async with get_conn() as conn:
        plan = await _fetch_plan(conn, plan_id)
    if not _plan_is_buyable(plan):
        await callback.answer(t("buy.plan_unavailable", lang), show_alert=True)
        return
    assert plan is not None  # narrowed by _plan_is_buyable

    data = await state.get_data()
    promo_id = int(data.get("promo_id") or 0)
    promo: Promo | None = None
    if promo_id:
        async with get_conn() as conn:
            promo = await _fetch_promo(conn, promo_id)
        if not _promo_is_usable(promo):
            promo = None
            promo_id = 0

    sub_id = int(data.get("sub_id") or 0)
    gift = int(data.get("gift") or 0)

    # ---- Extend branch — bypass inbound selection entirely. ----
    if sub_id > 0:
        extending_sub: Subscription | None = None
        if user is not None:
            async with get_conn() as conn:
                extending_sub = await subs_repo.get(conn, sub_id)
            if (
                extending_sub is None
                or extending_sub.user_id != user.id
                or extending_sub.status != "active"
            ):
                await callback.answer(
                    t("buy.sub_unavailable_extend", lang), show_alert=True
                )
                await state.clear()
                return
        # Inbound is pinned to the existing sub.
        inbound_id = int(extending_sub.xui_inbound_id) if extending_sub else int(
            data.get("inbound_id") or 0
        )
        remark: str | None = None
        try:
            xui = await get_xui_client()
            options = await list_user_inbounds(xui)
            remark = next(
                (o.remark for o in options if o.id == inbound_id),
                None,
            )
        except XuiError as exc:
            logger.warning(
                "cb_pick_plan(extend): panel unreachable, rendering confirm "
                "without inbound remark for plan {}: {}",
                plan.id,
                exc,
            )
        await state.update_data(
            plan_id=plan.id,
            promo_id=promo_id,
            inbound_id=inbound_id,
            sub_id=sub_id,
            inbound_options=None,
        )
        await state.set_state(BuyFlow.confirming)
        can_balance = await _can_pay_from_balance(user, plan, promo)
        if callback.message is not None:
            await callback.message.edit_text(
                _format_confirm(
                    plan, promo,
                    inbound_remark=remark,
                    extending_sub=extending_sub,
                    lang=lang,
                ),
                reply_markup=confirm_kb(
                    plan.id,
                    promo_id=promo_id,
                    inbound_id=inbound_id,
                    sub_id=sub_id,
                    can_pay_from_balance=can_balance,
                    lang=lang,
                ),
            )
        await callback.answer()
        return

    # ---- New-subscription branch (original logic). ----
    async with get_conn() as conn:
        inbound_ids = await plans_repo.get_inbounds(conn, plan.id)

    if not inbound_ids:
        await callback.answer(
            t("buy.plan_no_inbounds", lang),
            show_alert=True,
        )
        return

    # Single-inbound plan — skip the selection step entirely.
    if len(inbound_ids) == 1:
        only_inbound_id = int(inbound_ids[0])
        # Try to resolve the remark for a nicer confirm card; falls back
        # to a placeholder on panel error.
        remark = None
        try:
            xui = await get_xui_client()
            options = await list_user_inbounds(xui)
            remark = next(
                (o.remark for o in options if o.id == only_inbound_id),
                None,
            )
        except XuiError as exc:
            logger.warning(
                "cb_pick_plan: panel unreachable, rendering confirm without "
                "inbound remark for plan {}: {}",
                plan.id,
                exc,
            )

        await state.update_data(
            plan_id=plan.id,
            promo_id=promo_id,
            inbound_id=only_inbound_id,
            sub_id=0,
            gift=gift,
            inbound_options=None,
        )
        await state.set_state(BuyFlow.confirming)
        can_balance = await _can_pay_from_balance(user, plan, promo)
        if callback.message is not None:
            await callback.message.edit_text(
                _format_confirm(plan, promo, inbound_remark=remark, extending_sub=None, lang=lang),
                reply_markup=confirm_kb(
                    plan.id,
                    promo_id=promo_id,
                    inbound_id=only_inbound_id,
                    can_pay_from_balance=can_balance,
                    gift=gift,
                    offer_subscription=_offers_subscription(plan, sub_id=0, gift=gift),
                    lang=lang,
                ),
            )
        await callback.answer()
        return

    # Multi-inbound plan — present the selection keyboard.
    try:
        xui = await get_xui_client()
        all_options = await list_user_inbounds(xui)
    except XuiError as exc:
        logger.warning(
            "cb_pick_plan: failed to list inbounds for plan {}: {}", plan.id, exc
        )
        await callback.answer(
            t("buy.inbounds_unavailable", lang),
            show_alert=True,
        )
        return

    allowed = set(inbound_ids)
    filtered = [o for o in all_options if o.id in allowed]
    if not filtered:
        await callback.answer(
            t("buy.no_inbounds_for_plan", lang),
            show_alert=True,
        )
        return

    await state.update_data(
        plan_id=plan.id,
        promo_id=promo_id,
        inbound_id=0,
        sub_id=0,
        inbound_options=_options_to_jsonable(filtered),
    )
    await state.set_state(BuyFlow.choosing_inbound)
    if callback.message is not None:
        await callback.message.edit_text(
            t("buy.choose_inbound", lang),
            reply_markup=inbound_select_kb(plan.id, filtered, promo_id=promo_id),
        )
    await callback.answer()


# ---------------------------------------------------------------------- #
# Inbound selection
# ---------------------------------------------------------------------- #


@router.callback_query(
    BuyFlow.choosing_inbound, InboundCB.filter(F.action == "pick")
)
async def cb_pick_inbound(
    callback: CallbackQuery,
    callback_data: InboundCB,
    state: FSMContext,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Persist the chosen inbound and render the confirmation card.

    Re-validates that ``inbound_id`` still belongs to the plan via
    :func:`app.db.repos.plans.get_inbounds` — protects against a race
    where the admin detached the inbound between rendering the keyboard
    and the user tapping a button.
    """
    plan_id = callback_data.plan_id
    inbound_id = callback_data.inbound_id

    async with get_conn() as conn:
        plan = await _fetch_plan(conn, plan_id)
        allowed = await plans_repo.get_inbounds(conn, plan_id) if plan is not None else []
    if not _plan_is_buyable(plan):
        await callback.answer(t("buy.plan_unavailable", lang), show_alert=True)
        await state.clear()
        return
    assert plan is not None
    if inbound_id not in allowed:
        await callback.answer(
            t("buy.inbound_unavailable_for_plan", lang),
            show_alert=True,
        )
        return

    data = await state.get_data()
    promo_id = int(data.get("promo_id") or callback_data.promo_id or 0)
    promo: Promo | None = None
    if promo_id:
        async with get_conn() as conn:
            promo = await _fetch_promo(conn, promo_id)
        if not _promo_is_usable(promo):
            promo = None
            promo_id = 0

    raw_options = data.get("inbound_options") or []
    options = (
        _jsonable_to_options(raw_options)
        if isinstance(raw_options, list) and raw_options
        else []
    )
    remark = _remark_for(options, inbound_id) if options else f"#{inbound_id}"

    sub_id = int(data.get("sub_id") or 0)
    gift = int(data.get("gift") or 0)
    await state.update_data(
        plan_id=plan.id,
        promo_id=promo_id,
        inbound_id=inbound_id,
        sub_id=sub_id,
        gift=gift,
    )
    await state.set_state(BuyFlow.confirming)
    can_balance = await _can_pay_from_balance(user, plan, promo)
    if callback.message is not None:
        await callback.message.edit_text(
            _format_confirm(plan, promo, inbound_remark=remark, extending_sub=None, lang=lang),
            reply_markup=confirm_kb(
                plan.id,
                promo_id=promo_id,
                inbound_id=inbound_id,
                sub_id=sub_id,
                can_pay_from_balance=can_balance,
                gift=gift,
                offer_subscription=_offers_subscription(plan, sub_id=sub_id, gift=gift),
                lang=lang,
            ),
        )
    await callback.answer()


@router.callback_query(
    BuyFlow.choosing_inbound, InboundCB.filter(F.action == "back")
)
async def cb_pick_inbound_back(
    callback: CallbackQuery,
    state: FSMContext,
    lang: str = DEFAULT_LANG,
) -> None:
    """Return from the inbound-selection step back to the plan list."""
    await state.set_state(BuyFlow.choosing_plan)
    await state.update_data(inbound_id=0, inbound_options=None)
    async with get_conn() as conn:
        plans = await plans_repo.list_active(conn)
    if callback.message is not None:
        if not plans:
            await callback.message.edit_text(t("buy.no_plans", lang))
        else:
            await callback.message.edit_text(
                t("buy.choose_plan", lang),
                reply_markup=plans_kb(plans),
            )
    await callback.answer()


# ---------------------------------------------------------------------- #
# Promo input
# ---------------------------------------------------------------------- #


@router.callback_query(BuyCB.filter(F.action == "apply_promo"))
async def cb_apply_promo(
    callback: CallbackQuery,
    callback_data: BuyCB,
    state: FSMContext,
    lang: str = DEFAULT_LANG,
) -> None:
    """Prompt the user to type a promo code.

    Stores the active ``plan_id`` and the previously-chosen
    ``inbound_id`` (taken from the callback payload, falling back to
    the FSM data) so :func:`msg_promo_code` can return to the
    confirmation card with the same inbound pinned.
    """
    data = await state.get_data()
    inbound_id = int(callback_data.inbound_id or data.get("inbound_id") or 0)
    sub_id = int(callback_data.sub_id or data.get("sub_id") or 0)
    gift = int(callback_data.gift or data.get("gift") or 0)
    await state.update_data(
        plan_id=callback_data.plan_id,
        inbound_id=inbound_id,
        sub_id=sub_id,
        gift=gift,
    )
    await state.set_state(BuyFlow.entering_promo)
    if callback.message is not None:
        await callback.message.edit_text(
            t("buy.enter_promo", lang),
            reply_markup=confirm_kb(
                callback_data.plan_id,
                inbound_id=inbound_id,
                sub_id=sub_id,
                gift=gift,
            ),
        )
    await callback.answer()


@router.message(BuyFlow.entering_promo)
async def msg_promo_code(
    message: Message,
    state: FSMContext,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Validate the typed code and return to the confirmation card.

    On a valid code we store the ``promo_id`` in the FSM and re-render
    the confirmation card with the new total. On an error we show the
    error message and stay in :class:`BuyFlow.entering_promo` so the user
    can try again.
    """
    if user is None:
        await message.answer(t("buy.need_start_full", lang))
        return

    data = await state.get_data()
    plan_id = int(data.get("plan_id") or 0)
    inbound_id = int(data.get("inbound_id") or 0)
    sub_id = int(data.get("sub_id") or 0)
    gift = int(data.get("gift") or 0)
    async with get_conn() as conn:
        plan = await _fetch_plan(conn, plan_id)
        if not _plan_is_buyable(plan):
            await message.answer(t("buy.plan_gone", lang))
            await state.clear()
            return
        assert plan is not None
        result = await promos_service.validate(
            conn, code=message.text or "", user_id=user.id, plan=plan
        )

    if not result.is_valid or result.promo is None:
        await message.answer(
            t(
                "buy.promo_invalid_retry",
                lang,
                error=result.error or t("buy.promo_default_invalid", lang),
            ),
            reply_markup=confirm_kb(
                plan.id, inbound_id=inbound_id, sub_id=sub_id, gift=gift
            ),
        )
        return

    await state.update_data(
        promo_id=result.promo.id, inbound_id=inbound_id, sub_id=sub_id, gift=gift
    )
    await state.set_state(BuyFlow.confirming)

    # Resolve the chosen inbound's remark (best-effort — falls back to
    # a placeholder when the panel is unreachable or the cache is empty).
    remark: str | None = None
    if inbound_id:
        try:
            xui = await get_xui_client()
            options = await list_user_inbounds(xui)
            remark = next(
                (o.remark for o in options if o.id == inbound_id),
                None,
            )
        except XuiError as exc:
            logger.warning(
                "msg_promo_code: panel unreachable, rendering confirm without "
                "inbound remark: {}",
                exc,
            )

    # Re-resolve the extending subscription (if any) so the confirm card
    # shows "🔄 Продление подписки #N · до DATE" rather than the "new"
    # variant. Ownership/status was already checked when entering the
    # extend branch in cb_pick_plan, but it's cheap to verify again.
    extending_sub: Subscription | None = None
    if sub_id > 0:
        async with get_conn() as conn:
            extending_sub = await subs_repo.get(conn, sub_id)
        if extending_sub is not None and (
            extending_sub.user_id != user.id or extending_sub.status != "active"
        ):
            extending_sub = None

    can_balance = await _can_pay_from_balance(user, plan, result.promo)
    await message.answer(
        t("buy.promo_applied", lang)
        + _format_confirm(
            plan, result.promo,
            inbound_remark=remark,
            extending_sub=extending_sub,
            lang=lang,
        ),
        reply_markup=confirm_kb(
            plan.id,
            promo_id=result.promo.id,
            inbound_id=inbound_id,
            sub_id=sub_id,
            can_pay_from_balance=can_balance,
            gift=gift,
            lang=lang,
        ),
    )


# ---------------------------------------------------------------------- #
# Confirm → send invoice
# ---------------------------------------------------------------------- #


@router.callback_query(BuyCB.filter(F.action == "confirm"))
async def cb_confirm(
    callback: CallbackQuery,
    callback_data: BuyCB,
    state: FSMContext,
    bot: Bot,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Re-validate, send the Stars invoice, and clear FSM state.

    Re-validation is a defence-in-depth: another admin might have
    deactivated the plan, exhausted the promo or detached the inbound
    from the plan between selection and confirmation.
    ``pre_checkout`` will validate again at payment time.

    The ``inbound_id`` is sourced from the callback payload (the
    keyboard threads it through :class:`BuyCB`) and — for the new-sub
    branch only — re-validated against
    :func:`app.db.repos.plans.get_inbounds`. On mismatch we send the user
    back to the inbound-selection step instead of issuing the invoice.

    When ``sub_id > 0`` (extend flow):

    * The allow-list check is **intentionally skipped** — an existing
      subscription may live on an inbound that has since been detached
      from any plan, and extending it must still succeed.
    * Ownership of ``sub_id`` is re-verified (the keyboard is server-
      trusted but defence-in-depth: a stale keyboard mid-session must
      not let a user extend someone else's sub).
    * ``inbound_id`` is taken from the existing subscription if missing
      from the payload (legacy keyboards).
    """
    plan_id = callback_data.plan_id
    promo_id = callback_data.promo_id or 0
    inbound_id = int(callback_data.inbound_id or 0)
    sub_id = int(callback_data.sub_id or 0)
    gift = int(callback_data.gift or 0)
    if not inbound_id or not sub_id or not gift:
        # Fallback: the FSM should always have these by this point, but
        # if it doesn't (e.g. a stale keyboard from before the rollout),
        # recover from state data.
        data = await state.get_data()
        if not inbound_id:
            inbound_id = int(data.get("inbound_id") or 0)
        if not sub_id:
            sub_id = int(data.get("sub_id") or 0)
        if not gift:
            gift = int(data.get("gift") or 0)

    async with get_conn() as conn:
        plan = await _fetch_plan(conn, plan_id)
        promo = await _fetch_promo(conn, promo_id) if promo_id else None
        allowed_inbounds = (
            await plans_repo.get_inbounds(conn, plan_id) if plan is not None else []
        )

    if not _plan_is_buyable(plan):
        await callback.answer(t("buy.plan_unavailable", lang), show_alert=True)
        await state.clear()
        return
    assert plan is not None
    if promo_id and not _promo_is_usable(promo):
        await callback.answer(
            t("buy.promo_became_invalid", lang),
            show_alert=True,
        )
        promo = None
        promo_id = 0

    # ---- Gift branch — buy a giftable code (always a new sub for the
    # recipient, so sub_id / extend semantics never apply). The inbound
    # allow-list is re-checked exactly like the new-sub branch. ----
    if gift:
        if not inbound_id or inbound_id not in allowed_inbounds:
            await callback.answer(t("buy.inbound_unavailable_pick", lang), show_alert=True)
            return
        chat_id = callback.message.chat.id if callback.message is not None else None
        if chat_id is None:
            await callback.answer(t("buy.chat_undetermined", lang), show_alert=True)
            return
        await billing.send_gift_invoice(
            bot,
            chat_id=chat_id,
            plan=plan,
            promo=promo,
            inbound_id=inbound_id,
        )
        await state.clear()
        await callback.answer()
        return

    # ---- Extend branch — verify ownership, skip allow-list. ----
    if sub_id > 0:
        if user is None:
            await callback.answer(t("buy.need_start", lang), show_alert=True)
            return
        async with get_conn() as conn:
            sub = await subs_repo.get(conn, sub_id)
        if sub is None or sub.user_id != user.id or sub.status != "active":
            await callback.answer(
                t("buy.sub_unavailable_extend", lang), show_alert=True
            )
            await state.clear()
            return
        if not inbound_id:
            inbound_id = int(sub.xui_inbound_id)
        chat_id = callback.message.chat.id if callback.message is not None else None
        if chat_id is None:
            await callback.answer(t("buy.chat_undetermined", lang), show_alert=True)
            return
        await billing.send_invoice(
            bot,
            chat_id=chat_id,
            plan=plan,
            promo=promo,
            inbound_id=inbound_id,
            sub_id=sub_id,
        )
        await state.clear()
        await callback.answer()
        return

    # ---- New-subscription branch — original allow-list check. ----
    if not inbound_id or inbound_id not in allowed_inbounds:
        # Inbound was either never set or no longer attached to the plan.
        # Drop the user back to the selection step so they can pick a
        # currently-valid one.
        await callback.answer(
            t("buy.inbound_unavailable_pick", lang),
            show_alert=True,
        )
        try:
            xui = await get_xui_client()
            all_options = await list_user_inbounds(xui)
        except XuiError as exc:
            logger.warning(
                "cb_confirm: failed to refresh inbounds for plan {}: {}",
                plan.id,
                exc,
            )
            return
        allowed_set = set(allowed_inbounds)
        filtered = [o for o in all_options if o.id in allowed_set]
        if not filtered:
            await state.clear()
            if callback.message is not None:
                await callback.message.edit_text(
                    t("buy.plan_no_inbounds_retry", lang),
                )
            return
        await state.update_data(
            plan_id=plan.id,
            promo_id=promo_id,
            inbound_id=0,
            inbound_options=_options_to_jsonable(filtered),
        )
        await state.set_state(BuyFlow.choosing_inbound)
        if callback.message is not None:
            await callback.message.edit_text(
                t("buy.choose_inbound", lang),
                reply_markup=inbound_select_kb(plan.id, filtered, promo_id=promo_id),
            )
        return

    chat_id = callback.message.chat.id if callback.message is not None else None
    if chat_id is None:
        await callback.answer(t("buy.chat_undetermined", lang), show_alert=True)
        return

    await billing.send_invoice(
        bot,
        chat_id=chat_id,
        plan=plan,
        promo=promo,
        inbound_id=inbound_id,
        sub_id=0,
    )
    # The state has done its job — the invoice payload carries plan_id,
    # promo_id, inbound_id and sub_id (0 for new) through to
    # pre_checkout / successful_payment.
    await state.clear()
    await callback.answer()


# ---------------------------------------------------------------------- #
# Native recurring Star subscription (invoice link)
# ---------------------------------------------------------------------- #


@router.callback_query(BuyCB.filter(F.action == "sub"))
async def cb_subscribe(
    callback: CallbackQuery,
    callback_data: BuyCB,
    state: FSMContext,
    bot: Bot,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Offer a native recurring **Telegram Star subscription** via an invoice link.

    Reached from the «🔁 Подписка (автопродление)» button on the confirm card
    (shown only for an eligible 30-day plan — see :func:`_offers_subscription`).
    Telegram only supports recurring Star billing through a
    ``create_invoice_link`` URL (never ``send_invoice``), so this handler builds
    the link via :func:`app.services.billing.create_subscription_invoice_link`
    (payload ``kind='sub'``, ``subscription_period=2592000``) and sends it as a
    URL button the user taps to subscribe.

    Re-validates the plan (defence-in-depth — it may have been deactivated since
    the card was rendered) and that the inbound is still attached to it (a
    recurring subscription always provisions a fresh client, so the allow-list
    check mirrors the new-sub branch of :func:`cb_confirm`).
    """
    if not settings.AUTO_RENEW_ENABLED:
        await callback.answer(t("autorenew.cancel_failed", lang), show_alert=True)
        return

    plan_id = callback_data.plan_id
    inbound_id = int(callback_data.inbound_id or 0)
    if not inbound_id:
        data = await state.get_data()
        inbound_id = int(data.get("inbound_id") or 0)

    async with get_conn() as conn:
        plan = await _fetch_plan(conn, plan_id)
        allowed_inbounds = (
            await plans_repo.get_inbounds(conn, plan_id) if plan is not None else []
        )

    if not _plan_is_buyable(plan):
        await callback.answer(t("buy.plan_unavailable", lang), show_alert=True)
        await state.clear()
        return
    assert plan is not None
    if not inbound_id or inbound_id not in allowed_inbounds:
        await callback.answer(t("buy.inbound_unavailable_pick", lang), show_alert=True)
        return

    link = await billing.create_subscription_invoice_link(
        bot,
        plan,
        inbound_id=inbound_id,
        sub_id=0,
    )
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text(
            t("autorenew.subscribe_prompt", lang),
            reply_markup=subscription_link_kb(link, lang),
        )
    await callback.answer()


# ---------------------------------------------------------------------- #
# Pay from wallet balance (no Telegram invoice)
# ---------------------------------------------------------------------- #


@router.callback_query(BuyCB.filter(F.action == "balance"))
async def cb_pay_from_balance(
    callback: CallbackQuery,
    callback_data: BuyCB,
    state: FSMContext,
    bot: Bot,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Pay for a plan with the user's wallet balance — no Telegram invoice.

    Flow (mirrors :func:`cb_confirm`'s re-validation, then spends + provisions):

    1. Re-validate plan + promo (defence-in-depth: state may have changed).
    2. For the extend branch, re-verify ownership of ``sub_id``; for a new
       subscription, re-check the inbound is still on the plan's allow-list.
    3. :func:`app.services.wallet.try_spend` debits the final Stars price under
       ``BEGIN IMMEDIATE``. The ``ref`` is ``buy:<callback.id>`` — Telegram's
       callback-query id is unique per tap, so a duplicate-delivery of the same
       tap is rejected (no double-spend) while a genuine second purchase (a new
       tap) gets a fresh ref. On insufficient balance the button-press is
       rejected with an alert (the balance may have dropped since render).
    4. Provision via :func:`app.services.subscriptions.create_or_extend`. If
       3x-ui provisioning fails we **refund** the wallet (compensating credit
       with ref ``refund:<txn_id>``) so the user is not charged for a key they
       never received.
    5. Record a synthetic ``payments`` row with ``telegram_charge_id =
       wallet:<txn_id>`` so stats / ``total_stars_period`` count the spend.
    6. Deliver keys.
    """
    if user is None:
        await callback.answer(t("buy.need_start", lang), show_alert=True)
        return

    plan_id = callback_data.plan_id
    promo_id = callback_data.promo_id or 0
    inbound_id = int(callback_data.inbound_id or 0)
    sub_id = int(callback_data.sub_id or 0)
    if not inbound_id or not sub_id:
        data = await state.get_data()
        if not inbound_id:
            inbound_id = int(data.get("inbound_id") or 0)
        if not sub_id:
            sub_id = int(data.get("sub_id") or 0)

    async with get_conn() as conn:
        plan = await _fetch_plan(conn, plan_id)
        promo = await _fetch_promo(conn, promo_id) if promo_id else None
        allowed_inbounds = (
            await plans_repo.get_inbounds(conn, plan_id) if plan is not None else []
        )

    if not _plan_is_buyable(plan):
        await callback.answer(t("buy.plan_unavailable", lang), show_alert=True)
        await state.clear()
        return
    assert plan is not None
    if promo_id and not _promo_is_usable(promo):
        await callback.answer(t("buy.promo_became_invalid", lang), show_alert=True)
        promo = None
        promo_id = 0

    # ---- Extend branch — verify ownership; skip allow-list. ----
    extend_sub_id: int | None = None
    if sub_id > 0:
        async with get_conn() as conn:
            sub_row = await subs_repo.get(conn, sub_id)
        if sub_row is None or sub_row.user_id != user.id or sub_row.status != "active":
            await callback.answer(t("buy.sub_unavailable_extend", lang), show_alert=True)
            await state.clear()
            return
        if not inbound_id:
            inbound_id = int(sub_row.xui_inbound_id)
        extend_sub_id = sub_id
    # ---- New-subscription branch — re-check allow-list. ----
    elif not inbound_id or inbound_id not in allowed_inbounds:
        await callback.answer(t("buy.inbound_unavailable_pick", lang), show_alert=True)
        return

    price = billing.calc_price(plan, promo)
    chat_id = callback.message.chat.id if callback.message is not None else None
    if chat_id is None:
        await callback.answer(t("buy.chat_undetermined", lang), show_alert=True)
        return

    # Step 3 — atomically debit the wallet. The callback-query id makes the ref
    # unique per tap so a Telegram redelivery of the same tap is deduped.
    spend_ref = f"buy:{callback.id}"
    async with get_conn() as conn:
        spent = await wallet_service.try_spend(
            conn, user.id, price.stars, ref=spend_ref
        )
    if not spent:
        await callback.answer(t("wallet.insufficient", lang), show_alert=True)
        return

    # Recover the debit txn id for the synthetic payment / a potential refund.
    async with get_conn() as conn:
        spend_txn = await wallet_repo.get_by_ref(conn, spend_ref)
    txn_id = spend_txn.id if spend_txn is not None else 0
    synthetic_charge_id = f"wallet:{txn_id}"

    # Step 4 — provision (xui-first). On failure, refund and bail out.
    xui = await get_xui_client()
    sub = None
    try:
        async with get_conn() as conn:
            sub = await subs_service.create_or_extend(
                conn=conn,
                xui=xui,
                user=user,
                plan=plan,
                promo=promo,
                inbound_id=int(inbound_id),
                extend_sub_id=extend_sub_id,
            )
    except XuiError as exc:
        logger.error(
            "cb_pay_from_balance: xui provisioning failed for user {} txn {}: {}; "
            "refunding wallet",
            user.id,
            txn_id,
            exc,
        )
        async with get_conn() as conn:
            await wallet_service.credit(
                conn,
                user.id,
                price.stars,
                type="refund",
                ref=f"refund:{txn_id}",
            )
        await state.clear()
        if callback.message is not None:
            await callback.message.answer(t("wallet.pay_failed", lang))
        await callback.answer()
        return

    # Step 5 — synthetic payment row so stats / total_stars count the spend.
    async with get_conn() as conn:
        try:
            await payments_repo.create(
                conn,
                user_id=user.id,
                subscription_id=sub.id if sub is not None else None,
                telegram_charge_id=synthetic_charge_id,
                stars_amount=price.stars,
                plan_id=plan.id,
                promo_id=promo.id if promo is not None else None,
            )
        except aiosqlite.IntegrityError:
            logger.info(
                "cb_pay_from_balance: duplicate synthetic payment {} — fine",
                synthetic_charge_id,
            )

    # Step 6 — promo redemption (best-effort, like on_successful_payment).
    if sub is not None and promo is not None:
        async with get_conn() as conn:
            ok = await promos_service.apply(
                conn,
                promo_id=promo.id,
                user_id=user.id,
                subscription_id=sub.id,
            )
        if not ok:
            logger.warning(
                "cb_pay_from_balance: promo {} apply failed for user {} sub {}",
                promo.id,
                user.id,
                sub.id,
            )

    await state.clear()
    if sub is not None:
        await deliver_keys(
            bot, xui, chat_id=chat_id, sub=sub,
            header=t("wallet.paid_from_balance_header", lang),
            lang=lang,
        )
    await callback.answer()


# ---------------------------------------------------------------------- #
# Pre-checkout
# ---------------------------------------------------------------------- #


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery, bot: Bot) -> None:
    """Re-validate plan + promo and answer the pre-checkout query.

    Telegram requires this to be answered within ~10 seconds. We keep
    the checks read-only (no writes!) so a partial failure can't leak a
    half-applied promo. Error messages are localized from the buyer's
    Telegram ``language_code`` (the only signal available before the DB
    lookup).
    """
    lang = resolve_lang(
        query.from_user.language_code if query.from_user is not None else None
    )
    try:
        ctx = billing.parse_invoice_payload(query.invoice_payload)
    except ValueError as exc:
        logger.warning("pre_checkout: bad payload {!r}: {}", query.invoice_payload, exc)
        await bot.answer_pre_checkout_query(
            query.id, ok=False, error_message=t("buy.precheckout_bad_order", lang)
        )
        return

    # ``ctx.kind`` is the extension point: "buy" is handled below (current
    # one-off purchase / extend flow). "topup" (Ф2), "gift" (Ф3) and "sub"
    # (Ф4) will branch here as those phases land. Until then any non-"buy"
    # kind reaches the buy flow below and is validated as a normal purchase.
    plan_id = ctx.plan_id
    promo_id = ctx.promo_id
    inbound_id = ctx.inbound_id
    sub_id = ctx.sub_id

    async with get_conn() as conn:
        plan = await _fetch_plan(conn, plan_id)
        promo = await _fetch_promo(conn, promo_id) if promo_id else None
        allowed_inbounds = (
            await plans_repo.get_inbounds(conn, plan_id) if plan is not None else []
        )

    if not _plan_is_buyable(plan):
        await bot.answer_pre_checkout_query(
            query.id, ok=False, error_message=t("buy.precheckout_plan_gone", lang)
        )
        return
    if promo_id and not _promo_is_usable(promo):
        await bot.answer_pre_checkout_query(
            query.id,
            ok=False,
            error_message=t("buy.precheckout_promo_invalid", lang),
        )
        return

    # Extend flow: validate ownership of sub_id, skip allow-list check
    # (an existing sub may live on an inbound that's no longer attached
    # to any plan).
    if int(sub_id) > 0:
        tg_id = query.from_user.id if query.from_user is not None else None
        if tg_id is None:
            await bot.answer_pre_checkout_query(
                query.id,
                ok=False,
                error_message=t("buy.precheckout_user_undetermined", lang),
            )
            return
        async with get_conn() as conn:
            buyer = await users_repo.get_by_tg_id(conn, int(tg_id))
            sub = await subs_repo.get(conn, int(sub_id)) if buyer is not None else None
        if (
            buyer is None
            or sub is None
            or sub.user_id != buyer.id
            or sub.status != "active"
        ):
            logger.warning(
                "pre_checkout: extend rejected (tg_id={}, sub_id={})",
                tg_id,
                sub_id,
            )
            await bot.answer_pre_checkout_query(
                query.id,
                ok=False,
                error_message=t("buy.precheckout_sub_unavailable", lang),
            )
            return
        await bot.answer_pre_checkout_query(query.id, ok=True)
        return

    # New-subscription flow — original allow-list check.
    if int(inbound_id) not in allowed_inbounds:
        logger.warning(
            "pre_checkout: inbound_id={} not in plan {} allow-list {}",
            inbound_id,
            plan_id,
            allowed_inbounds,
        )
        await bot.answer_pre_checkout_query(
            query.id,
            ok=False,
            error_message=t("buy.precheckout_inbound_gone", lang),
        )
        return

    await bot.answer_pre_checkout_query(query.id, ok=True)


# ---------------------------------------------------------------------- #
# Successful payment — finalise everything
# ---------------------------------------------------------------------- #


async def _credit_topup(
    message: Message,
    user: User,
    charge_id: str,
    total_amount: int,
    topup_stars: int,
    lang: str,
) -> None:
    """Finalise a wallet top-up (``kind="topup"``) — idempotent.

    Two layers of idempotency keep the balance correct even if Telegram retries
    the ``successful_payment`` update:

    * ``payments.telegram_charge_id`` is UNIQUE — the payment row is recorded
      at most once (a duplicate insert raises ``IntegrityError``, swallowed).
    * ``wallet.credit`` uses the deterministic ref ``topup:<charge_id>`` (the
      partial-unique ``idx_wallet_ref``) — the balance is credited at most once
      regardless of how many times this runs.

    We credit the *actual* amount Telegram charged (``total_amount``) rather
    than the payload's ``topup_stars`` if they disagree, so the balance always
    matches the money received; a mismatch is logged at WARNING for auditing.
    """
    amount = int(total_amount) if total_amount > 0 else int(topup_stars)
    if topup_stars and total_amount and int(topup_stars) != int(total_amount):
        logger.warning(
            "topup: payload amount {} != charged amount {} (charge {}); "
            "crediting charged amount",
            topup_stars,
            total_amount,
            charge_id,
        )

    # Record the payment (real telegram_charge_id) for stats / total_stars.
    async with get_conn() as conn:
        try:
            await payments_repo.create(
                conn,
                user_id=user.id,
                subscription_id=None,
                telegram_charge_id=charge_id,
                stars_amount=amount,
                plan_id=None,
                promo_id=None,
            )
        except aiosqlite.IntegrityError:
            # Duplicate charge — already recorded by an earlier run / racing
            # worker. The wallet credit below is independently idempotent.
            logger.info("topup: duplicate payment for charge {} — fine", charge_id)

    # Credit the wallet exactly once (deterministic ref).
    async with get_conn() as conn:
        credited = await wallet_service.credit(
            conn,
            user.id,
            amount,
            type="topup",
            ref=f"topup:{charge_id}",
        )
    if credited:
        async with get_conn() as conn:
            new_balance = await wallet_repo.balance(conn, user.id)
        await message.answer(
            t("wallet.topup_success", lang, stars=amount, balance=new_balance)
        )
    else:
        # Already credited (replay) — stay quiet to avoid double-confirming.
        logger.info(
            "topup: credit for charge {} already applied — skipping confirm",
            charge_id,
        )


async def _mint_gift(
    message: Message,
    bot: Bot,
    user: User,
    charge_id: str,
    total_amount: int,
    ctx_plan_id: int,
    ctx_promo_id: int | None,
    ctx_inbound_id: int,
    lang: str,
) -> None:
    """Finalise a **gift** purchase (``kind="gift"``) — mint a code, not a sub.

    Steps (idempotent — the duplicate ``telegram_charge_id`` is rejected by the
    payment row's UNIQUE constraint, so the gift is minted at most once):

    1. Record the ``payments`` row (real ``telegram_charge_id``). A duplicate
       insert means a redelivery already minted the gift — short-circuit.
    2. Mint a fresh gift code via :func:`app.services.gifts.make_gift_code`,
       linking it to the payment, the plan and the chosen inbound.
    3. DM the *buyer* the code and the ``?start=gift_<code>`` activation link to
       forward to whoever they want to gift.

    The buyer is **not** provisioned a subscription here — the recipient
    redeems the code later (deep-link / «У меня есть подарок»).
    """
    # Step 1 — record the payment first so its UNIQUE charge_id gates the mint.
    payment_id: int | None = None
    async with get_conn() as conn:
        try:
            payment = await payments_repo.create(
                conn,
                user_id=user.id,
                subscription_id=None,
                telegram_charge_id=charge_id,
                stars_amount=total_amount,
                plan_id=ctx_plan_id or None,
                promo_id=ctx_promo_id,
            )
            payment_id = payment.id
        except aiosqlite.IntegrityError:
            # Duplicate charge — the gift was already minted on an earlier run.
            logger.info("gift: duplicate payment for charge {} — skipping mint", charge_id)
            return

    # Step 2 — mint the gift code (inside the not-duplicate branch only).
    async with get_conn() as conn:
        gift = await gifts_service.make_gift_code(
            conn,
            plan_id=ctx_plan_id or None,
            inbound_id=int(ctx_inbound_id),
            buyer_id=user.id,
            payment_id=payment_id,
        )

    # Step 3 — DM the buyer the code + activation deep-link.
    bot_username = await get_bot_username(bot)
    link = f"https://t.me/{bot_username}?start=gift_{gift.code}"
    await message.answer(
        t("gift.minted_dm", lang, code=gift.code, link=link)
    )


def _expiry_ms_from_unix(unix_seconds: int) -> int:
    """Convert a Telegram ``subscription_expiration_date`` (Unix s) to xui ms.

    Telegram's ``SuccessfulPayment.subscription_expiration_date`` is a Unix
    timestamp in **seconds**; 3x-ui's ``expiryTime`` is in **milliseconds**.
    """
    return int(unix_seconds) * 1000


def _datetime_from_unix(unix_seconds: int) -> datetime:
    """Convert a Unix-seconds timestamp to a UTC-aware :class:`datetime`."""
    return datetime.fromtimestamp(int(unix_seconds), tz=UTC)


async def _handle_recurring(
    message: Message,
    bot: Bot,
    user: User,
    charge_id: str,
    total_amount: int,
    ctx: billing.InvoiceContext,
    is_first: bool,
    sub_expiration: int | None,
    lang: str,
) -> None:
    """Finalise a native recurring **Star subscription** payment (``kind='sub'``).

    Two cases, distinguished by ``is_first`` (``successful_payment.is_first_recurring``):

    * **First charge** (``is_first``) → provision a brand-new subscription via
      :func:`app.services.subscriptions.create_or_extend` (``extend_sub_id=None``),
      flag it ``auto_renew=True`` and persist the recurring
      ``telegram_payment_charge_id`` (needed later by
      :meth:`aiogram.Bot.edit_user_star_subscription` to cancel), record the
      payment, then deliver keys.
    * **Subsequent charge** (recurring, not first) → locate the user's active
      native subscription for this plan via
      :func:`app.db.repos.subscriptions.get_active_auto_renew_for`, push its
      ``expires_at`` to Telegram's ``subscription_expiration_date`` (Unix→UTC),
      update the xui client's ``expiryTime`` to match, and record the payment.

    Idempotency: the caller already short-circuited on a duplicate
    ``telegram_payment_charge_id`` (each recurrence has a unique one), and the
    payment insert is additionally guarded by the UNIQUE charge-id constraint.
    """
    plan_id = ctx.plan_id
    inbound_id = ctx.inbound_id

    async with get_conn() as conn:
        plan = await plans_repo.get(conn, plan_id)
    if plan is None:
        logger.error(
            "recurring: plan {} missing for charge {}", plan_id, charge_id
        )
        async with get_conn() as conn:
            try:
                await payments_repo.create(
                    conn,
                    user_id=user.id,
                    subscription_id=None,
                    telegram_charge_id=charge_id,
                    stars_amount=total_amount,
                    plan_id=None,
                    promo_id=None,
                )
            except aiosqlite.IntegrityError:
                pass
        await message.answer(t("buy.payment_plan_deleted", lang))
        return

    xui = await get_xui_client()

    # ---- First recurring charge — provision a fresh subscription. ----
    if is_first:
        sub = None
        try:
            async with get_conn() as conn:
                sub = await subs_service.create_or_extend(
                    conn=conn,
                    xui=xui,
                    user=user,
                    plan=plan,
                    promo=None,
                    inbound_id=int(inbound_id),
                    extend_sub_id=None,
                )
        except XuiError as exc:
            logger.error(
                "recurring(first): xui provisioning failed charge {}: {}",
                charge_id,
                exc,
            )
        if sub is not None:
            async with get_conn() as conn:
                await subs_repo.set_auto_renew(
                    conn, sub.id, True, tg_sub_charge_id=charge_id
                )
        async with get_conn() as conn:
            try:
                await payments_repo.create(
                    conn,
                    user_id=user.id,
                    subscription_id=sub.id if sub is not None else None,
                    telegram_charge_id=charge_id,
                    stars_amount=total_amount,
                    plan_id=plan.id,
                    promo_id=None,
                )
            except aiosqlite.IntegrityError:
                logger.info("recurring(first): duplicate payment {} — fine", charge_id)
        if sub is not None:
            await deliver_keys(
                bot, xui, chat_id=message.chat.id, sub=sub,
                header=t("buy.payment_success_header", lang),
                lang=lang,
            )
        else:
            await message.answer(t("buy.payment_provision_failed", lang))
        return

    # ---- Subsequent recurring charge — extend the existing subscription. ----
    async with get_conn() as conn:
        sub = await subs_repo.get_active_auto_renew_for(conn, user.id, plan.id)
    if sub is None:
        logger.warning(
            "recurring(subsequent): no active auto_renew sub for user {} plan {} "
            "(charge {}); recording payment only",
            user.id,
            plan.id,
            charge_id,
        )
        async with get_conn() as conn:
            try:
                await payments_repo.create(
                    conn,
                    user_id=user.id,
                    subscription_id=None,
                    telegram_charge_id=charge_id,
                    stars_amount=total_amount,
                    plan_id=plan.id,
                    promo_id=None,
                )
            except aiosqlite.IntegrityError:
                pass
        return

    # Extend to Telegram's reported expiration date (authoritative for native
    # subscriptions). Fall back to +plan.days if Telegram omitted the field.
    if sub_expiration is not None:
        new_expiry = _datetime_from_unix(sub_expiration)
    else:
        from datetime import timedelta

        new_expiry = datetime.now(UTC).replace(microsecond=0) + timedelta(
            days=int(plan.days)
        )
    try:
        await update_client(
            xui,
            email=sub.xui_client_email,
            expiryTime=_expiry_ms_from_unix(int(new_expiry.timestamp())),
            enable=True,
        )
    except XuiError as exc:
        logger.error(
            "recurring(subsequent): xui update_client failed sub {} charge {}: {}",
            sub.id,
            charge_id,
            exc,
        )
    async with get_conn() as conn:
        await subs_repo.extend(conn, sub.id, new_expiry)
        try:
            await payments_repo.create(
                conn,
                user_id=user.id,
                subscription_id=sub.id,
                telegram_charge_id=charge_id,
                stars_amount=total_amount,
                plan_id=plan.id,
                promo_id=None,
            )
        except aiosqlite.IntegrityError:
            logger.info(
                "recurring(subsequent): duplicate payment {} — fine", charge_id
            )
    await message.answer(
        t(
            "autorenew.renewed_dm",
            lang,
            sub_id=sub.id,
            stars=total_amount,
            date=new_expiry.date().isoformat(),
        )
    )


@router.message(F.successful_payment)
async def on_successful_payment(
    message: Message,
    bot: Bot,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Finalise a paid Stars invoice.

    Steps (idempotent):

    1. Idempotency check: short-circuit if a payment with the same
       ``telegram_payment_charge_id`` already exists.
    2. Parse the invoice payload (``plan_id``, ``promo_id``).
    3. Re-fetch plan + promo (status may have changed; for the payment
       we accept the price Telegram already charged but we still want
       fresh objects for promo apply / subscription creation).
    4. Call :func:`app.services.subscriptions.create_or_extend` (xui +
       db). On :class:`app.xui.XuiError` we record the payment as
       "paid" but skip subscription provisioning — the admin then
       reconciles manually (the user gets an apology message with
       support contact).
    5. Record the payment row.
    6. Redeem the promo (best-effort — failure here doesn't break the
       subscription, just leaves the counter behind).
    7. Deliver vless URI + QR + subscription URL via
       :func:`app.handlers.user._keys.deliver_keys`.
    """
    if user is None or message.successful_payment is None:
        return

    payment = message.successful_payment
    charge_id = payment.telegram_payment_charge_id
    total_amount = int(payment.total_amount)

    # Step 1 — idempotency.
    async with get_conn() as conn:
        already = await payments_repo.get_by_charge_id(conn, charge_id)
    if already is not None:
        logger.info("successful_payment: duplicate charge {}; skipping", charge_id)
        return

    # Step 2 — payload.
    try:
        ctx = billing.parse_invoice_payload(payment.invoice_payload)
    except ValueError as exc:
        logger.error(
            "successful_payment: bad payload {!r}: {}", payment.invoice_payload, exc
        )
        await message.answer(t("buy.payment_unparseable", lang))
        return

    # ``ctx.kind`` is the routing extension point: "topup" credits the wallet
    # (handled below), "gift" mints a gift code (Ф3), "sub" provisions a native
    # recurring Star subscription (Ф4). The current handler implements the
    # "buy" (one-off purchase / extend) path; gift/sub fall through to it until
    # their phase lands.
    if ctx.kind == "topup":
        await _credit_topup(message, user, charge_id, total_amount, ctx.topup, lang)
        return

    # Gift purchase — mint a giftable code instead of provisioning the buyer a
    # subscription. Routed on ``kind="gift"`` (set by ``build_gift_payload``).
    if ctx.kind == "gift" or ctx.gift:
        await _mint_gift(
            message,
            bot,
            user,
            charge_id,
            total_amount,
            ctx.plan_id,
            ctx.promo_id,
            ctx.inbound_id,
            lang,
        )
        return

    # Native recurring Star subscription. Telegram flags every recurring charge
    # with ``is_recurring is True`` (and ``is_first_recurring is True`` on the
    # bootstrap one); ``is_recurring`` is ``Optional[bool]`` and is ``None`` for
    # an ordinary one-off purchase. The ``kind="sub"`` payload independently
    # marks the first charge. We test ``is True`` explicitly (not truthiness) so
    # a one-off payment whose ``is_recurring`` is ``None`` never enters this
    # branch. Routing on either signal covers both the first and the
    # Telegram-issued subsequent charges.
    if payment.is_recurring is True or ctx.kind == "sub":
        await _handle_recurring(
            message,
            bot,
            user,
            charge_id,
            total_amount,
            ctx,
            payment.is_first_recurring is True or payment.is_recurring is not True,
            payment.subscription_expiration_date,
            lang,
        )
        return

    plan_id = ctx.plan_id
    promo_id = ctx.promo_id
    inbound_id = ctx.inbound_id
    sub_id = ctx.sub_id

    # Surface legacy payloads (issued before the inbound-selection
    # rollout) at the handler layer too — parse_invoice_payload already
    # logs at WARNING, but having a second log line here makes the
    # provisioning side of the deploy traceable end-to-end.
    try:
        raw = json.loads(payment.invoice_payload)
        if isinstance(raw, dict) and "i" not in raw:
            logger.warning(
                "successful_payment: legacy payload without 'i' for charge {} — "
                "falling back to settings.XUI_INBOUND_ID={}",
                charge_id,
                settings.XUI_INBOUND_ID,
            )
    except ValueError:
        pass

    # Step 3 — refresh plan + promo.
    async with get_conn() as conn:
        plan = await plans_repo.get(conn, plan_id)
        promo = await promos_repo.get(conn, promo_id) if promo_id else None

    if plan is None:
        logger.error(
            "successful_payment: plan {} missing for charge {}", plan_id, charge_id
        )
        # Still record the payment so the admin knows Telegram got the money.
        async with get_conn() as conn:
            try:
                await payments_repo.create(
                    conn,
                    user_id=user.id,
                    subscription_id=None,
                    telegram_charge_id=charge_id,
                    stars_amount=total_amount,
                    plan_id=None,
                    promo_id=promo_id,
                )
            except aiosqlite.IntegrityError:
                pass  # raced with another worker — fine
        await message.answer(t("buy.payment_plan_deleted", lang))
        return

    # Step 4 — provision (xui-first, db-after).
    xui = await get_xui_client()
    sub = None
    xui_failed = False
    extend_sub_id = int(sub_id) if int(sub_id) > 0 else None
    if extend_sub_id is not None:
        logger.info(
            "successful_payment: extend sub {} (charge {})",
            extend_sub_id,
            charge_id,
        )
    else:
        logger.info(
            "successful_payment: create new sub (charge {})", charge_id
        )
    try:
        async with get_conn() as conn:
            sub = await subs_service.create_or_extend(
                conn=conn,
                xui=xui,
                user=user,
                plan=plan,
                promo=promo,
                inbound_id=int(inbound_id),
                extend_sub_id=extend_sub_id,
            )
    except XuiError as exc:
        xui_failed = True
        logger.error(
            "successful_payment: xui provisioning failed for charge {}: {}",
            charge_id,
            exc,
        )

    # Step 5 — record the payment regardless of xui outcome (Telegram
    # already charged the user). If sub is None the admin will reconcile.
    async with get_conn() as conn:
        try:
            await payments_repo.create(
                conn,
                user_id=user.id,
                subscription_id=sub.id if sub is not None else None,
                telegram_charge_id=charge_id,
                stars_amount=total_amount,
                plan_id=plan.id,
                promo_id=promo.id if promo is not None else None,
            )
        except aiosqlite.IntegrityError:
            # Another worker won the race — already recorded.
            logger.info(
                "successful_payment: duplicate insert for charge {} — fine", charge_id
            )

    # Step 6 — promo redemption (best-effort).
    if sub is not None and promo is not None:
        async with get_conn() as conn:
            ok = await promos_service.apply(
                conn,
                promo_id=promo.id,
                user_id=user.id,
                subscription_id=sub.id,
            )
        if not ok:
            logger.warning(
                "successful_payment: promo {} apply failed (race or invalidated) "
                "for user {} sub {}",
                promo.id,
                user.id,
                sub.id,
            )

    # Step 6b — referral reward. Pays the inviter (if any) on the referred
    # user's first payment. Idempotent: ``try_mark_rewarded`` + the deterministic
    # wallet ref make the bonus land at most once even though this runs after
    # every buy payment. Best-effort — a failure here must not break key
    # delivery (the user already paid).
    try:
        async with get_conn() as conn:
            await referrals_service.reward_referrer_after_first_payment(
                conn, bot, referred=user
            )
    except Exception as exc:  # noqa: BLE001 — reward must never break delivery
        logger.warning(
            "successful_payment: referral reward failed for user {}: {}",
            user.id,
            exc,
        )

    # Step 7 — keys.
    if sub is not None:
        await deliver_keys(
            bot, xui, chat_id=message.chat.id, sub=sub,
            header=t("buy.payment_success_header", lang),
            lang=lang,
        )
    elif xui_failed:
        await message.answer(t("buy.payment_provision_failed", lang))


__all__ = ["router"]
