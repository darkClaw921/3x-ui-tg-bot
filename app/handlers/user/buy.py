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
from app.db.repos.plans import Plan
from app.db.repos.promos import Promo
from app.db.repos.subscriptions import Subscription
from app.db.repos.users import User
from app.handlers.user._keys import deliver_keys
from app.keyboards.user import (
    BuyCB,
    InboundCB,
    buy_action_kb,
    confirm_kb,
    inbound_select_kb,
    plans_kb,
)
from app.services import billing, promos as promos_service, subscriptions as subs_service
from app.services.inbounds import InboundOption, list_user_inbounds
from app.states.user import BuyFlow
from app.xui import XuiError, get_xui_client

router = Router(name="user_buy")


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #


def _format_confirm(
    plan: Plan,
    promo: Promo | None,
    inbound_remark: str | None = None,
    extending_sub: Subscription | None = None,
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
    if extending_sub is not None:
        header = (
            f"🔄 <b>Продление подписки #{extending_sub.id}</b>"
            + (f" · {inbound_remark}" if inbound_remark else "")
        )
        new_expiry = _shift_expiry(extending_sub.expires_at, total_days)
        lines = [
            header,
            f"<b>Тариф:</b> {plan.title}",
            f"<b>Срок:</b> {plan.days} дн."
            + (f" + {price.extra_days} бонусных дн." if price.extra_days else ""),
            f"<b>Действует до:</b> {new_expiry}",
        ]
    else:
        header = "🆕 <b>Новая подписка</b>" + (
            f" на {inbound_remark}" if inbound_remark else ""
        )
        lines = [
            header,
            f"<b>Тариф:</b> {plan.title}",
            f"<b>Срок:</b> {plan.days} дн."
            + (f" + {price.extra_days} бонусных дн." if price.extra_days else ""),
        ]
    if promo is not None:
        lines.append(f"<b>Промокод:</b> <code>{promo.code}</code>")
        if promo.type == "percent":
            lines.append(f"<b>Скидка:</b> −{promo.value}%")
        elif promo.type == "flat_stars":
            lines.append(f"<b>Скидка:</b> −{promo.value}⭐")
        elif promo.type == "free_days":
            lines.append(f"<b>Бонус:</b> +{promo.value} дн.")
    lines.append("")
    lines.append(f"<b>К оплате:</b> {price.stars}⭐")
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


def _plan_is_buyable(plan: Plan | None) -> bool:
    """Return ``True`` if a plan exists and is currently active."""
    return plan is not None and plan.is_active


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
                "У вас есть активные подписки. Выберите действие:",
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
            await callback.message.edit_text(
                "Сейчас нет доступных тарифов. Загляните позже.",
            )
        await callback.answer()
        return
    if callback.message is not None:
        await callback.message.edit_text(
            "Выберите тариф:",
            reply_markup=plans_kb(plans),
        )
    await callback.answer()


async def _send_plan_list(
    callback: CallbackQuery,
    state: FSMContext,
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
        await callback.message.edit_text(
            "Сейчас нет доступных тарифов. Загляните позже.",
        )
        return
    await callback.message.edit_text(
        "Выберите тариф:",
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
        await callback.answer("Нужно нажать /start.", show_alert=True)
        return
    sub_id = int(callback_data.sub_id or 0)
    if sub_id <= 0:
        await callback.answer("Подписка не указана.", show_alert=True)
        return

    async with get_conn() as conn:
        sub = await subs_repo.get(conn, sub_id)
    if (
        sub is None
        or sub.user_id != user.id
        or sub.status != "active"
    ):
        await callback.answer(
            "Подписка недоступна для продления.", show_alert=True
        )
        return

    await state.update_data(
        sub_id=sub.id,
        inbound_id=int(sub.xui_inbound_id),
        # Wipe any stale plan/promo from a previous attempt.
        plan_id=0,
        promo_id=0,
        inbound_options=None,
    )
    await _send_plan_list(callback, state)
    await callback.answer()


@router.callback_query(BuyCB.filter(F.action == "new"))
async def cb_pick_action_new(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """User picked "🆕 Новая подписка" — clear FSM and show plans.

    Registered without a state filter so it can be invoked both from the
    action screen and (for symmetry with ``cb_pick_action_extend``) from
    other entry points that want to force "new sub" semantics.
    """
    await state.clear()
    await state.update_data(sub_id=0)
    await _send_plan_list(callback, state)
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
        await callback.answer("Тариф недоступен.", show_alert=True)
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
                    "Подписка недоступна для продления.", show_alert=True
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
        if callback.message is not None:
            await callback.message.edit_text(
                _format_confirm(
                    plan, promo,
                    inbound_remark=remark,
                    extending_sub=extending_sub,
                ),
                reply_markup=confirm_kb(
                    plan.id,
                    promo_id=promo_id,
                    inbound_id=inbound_id,
                    sub_id=sub_id,
                ),
            )
        await callback.answer()
        return

    # ---- New-subscription branch (original logic). ----
    async with get_conn() as conn:
        inbound_ids = await plans_repo.get_inbounds(conn, plan.id)

    if not inbound_ids:
        await callback.answer(
            "У тарифа нет доступных подключений. Обратитесь к администратору.",
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
            inbound_options=None,
        )
        await state.set_state(BuyFlow.confirming)
        if callback.message is not None:
            await callback.message.edit_text(
                _format_confirm(plan, promo, inbound_remark=remark, extending_sub=None),
                reply_markup=confirm_kb(plan.id, promo_id=promo_id, inbound_id=only_inbound_id),
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
            "Не удалось получить список подключений. Попробуйте позже.",
            show_alert=True,
        )
        return

    allowed = set(inbound_ids)
    filtered = [o for o in all_options if o.id in allowed]
    if not filtered:
        await callback.answer(
            "Нет доступных подключений для этого тарифа.",
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
            "Выберите подключение (сервер):",
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
        await callback.answer("Тариф недоступен.", show_alert=True)
        await state.clear()
        return
    assert plan is not None
    if inbound_id not in allowed:
        await callback.answer(
            "Подключение недоступно для этого тарифа.",
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
    await state.update_data(
        plan_id=plan.id, promo_id=promo_id, inbound_id=inbound_id, sub_id=sub_id
    )
    await state.set_state(BuyFlow.confirming)
    if callback.message is not None:
        await callback.message.edit_text(
            _format_confirm(plan, promo, inbound_remark=remark, extending_sub=None),
            reply_markup=confirm_kb(
                plan.id, promo_id=promo_id, inbound_id=inbound_id, sub_id=sub_id
            ),
        )
    await callback.answer()


@router.callback_query(
    BuyFlow.choosing_inbound, InboundCB.filter(F.action == "back")
)
async def cb_pick_inbound_back(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """Return from the inbound-selection step back to the plan list."""
    await state.set_state(BuyFlow.choosing_plan)
    await state.update_data(inbound_id=0, inbound_options=None)
    async with get_conn() as conn:
        plans = await plans_repo.list_active(conn)
    if callback.message is not None:
        if not plans:
            await callback.message.edit_text(
                "Сейчас нет доступных тарифов. Загляните позже.",
            )
        else:
            await callback.message.edit_text(
                "Выберите тариф:",
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
    await state.update_data(
        plan_id=callback_data.plan_id, inbound_id=inbound_id, sub_id=sub_id
    )
    await state.set_state(BuyFlow.entering_promo)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите промокод одним сообщением:",
            reply_markup=confirm_kb(
                callback_data.plan_id, inbound_id=inbound_id, sub_id=sub_id
            ),
        )
    await callback.answer()


@router.message(BuyFlow.entering_promo)
async def msg_promo_code(
    message: Message,
    state: FSMContext,
    user: User | None = None,
) -> None:
    """Validate the typed code and return to the confirmation card.

    On a valid code we store the ``promo_id`` in the FSM and re-render
    the confirmation card with the new total. On an error we show the
    error message and stay in :class:`BuyFlow.entering_promo` so the user
    can try again.
    """
    if user is None:
        await message.answer("Нужно нажать /start, чтобы начать.")
        return

    data = await state.get_data()
    plan_id = int(data.get("plan_id") or 0)
    inbound_id = int(data.get("inbound_id") or 0)
    sub_id = int(data.get("sub_id") or 0)
    async with get_conn() as conn:
        plan = await _fetch_plan(conn, plan_id)
        if not _plan_is_buyable(plan):
            await message.answer("Тариф больше недоступен. Вернитесь в меню.")
            await state.clear()
            return
        assert plan is not None
        result = await promos_service.validate(
            conn, code=message.text or "", user_id=user.id, plan=plan
        )

    if not result.is_valid or result.promo is None:
        await message.answer(
            (result.error or "Промокод недействителен.") + " Введите ещё раз:",
            reply_markup=confirm_kb(plan.id, inbound_id=inbound_id, sub_id=sub_id),
        )
        return

    await state.update_data(
        promo_id=result.promo.id, inbound_id=inbound_id, sub_id=sub_id
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

    await message.answer(
        "✅ Промокод применён.\n\n"
        + _format_confirm(
            plan, result.promo,
            inbound_remark=remark,
            extending_sub=extending_sub,
        ),
        reply_markup=confirm_kb(
            plan.id,
            promo_id=result.promo.id,
            inbound_id=inbound_id,
            sub_id=sub_id,
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
    if not inbound_id or not sub_id:
        # Fallback: the FSM should always have these by this point, but
        # if it doesn't (e.g. a stale keyboard from before the rollout),
        # recover from state data.
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
        await callback.answer("Тариф недоступен.", show_alert=True)
        await state.clear()
        return
    assert plan is not None
    if promo_id and not _promo_is_usable(promo):
        await callback.answer(
            "Промокод стал недействителен, попробуйте ещё раз.",
            show_alert=True,
        )
        promo = None
        promo_id = 0

    # ---- Extend branch — verify ownership, skip allow-list. ----
    if sub_id > 0:
        if user is None:
            await callback.answer("Нужно нажать /start.", show_alert=True)
            return
        async with get_conn() as conn:
            sub = await subs_repo.get(conn, sub_id)
        if sub is None or sub.user_id != user.id or sub.status != "active":
            await callback.answer(
                "Подписка недоступна для продления.", show_alert=True
            )
            await state.clear()
            return
        if not inbound_id:
            inbound_id = int(sub.xui_inbound_id)
        chat_id = callback.message.chat.id if callback.message is not None else None
        if chat_id is None:
            await callback.answer("Не удалось определить чат.", show_alert=True)
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
            "Подключение недоступно для этого тарифа. Выберите другое.",
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
                    "У тарифа сейчас нет доступных подключений. "
                    "Попробуйте позже.",
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
                "Выберите подключение (сервер):",
                reply_markup=inbound_select_kb(plan.id, filtered, promo_id=promo_id),
            )
        return

    chat_id = callback.message.chat.id if callback.message is not None else None
    if chat_id is None:
        await callback.answer("Не удалось определить чат.", show_alert=True)
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
# Pre-checkout
# ---------------------------------------------------------------------- #


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery, bot: Bot) -> None:
    """Re-validate plan + promo and answer the pre-checkout query.

    Telegram requires this to be answered within ~10 seconds. We keep
    the checks read-only (no writes!) so a partial failure can't leak a
    half-applied promo.
    """
    try:
        plan_id, promo_id, inbound_id, sub_id = billing.parse_invoice_payload(
            query.invoice_payload
        )
    except ValueError as exc:
        logger.warning("pre_checkout: bad payload {!r}: {}", query.invoice_payload, exc)
        await bot.answer_pre_checkout_query(
            query.id, ok=False, error_message="Некорректный заказ."
        )
        return

    async with get_conn() as conn:
        plan = await _fetch_plan(conn, plan_id)
        promo = await _fetch_promo(conn, promo_id) if promo_id else None
        allowed_inbounds = (
            await plans_repo.get_inbounds(conn, plan_id) if plan is not None else []
        )

    if not _plan_is_buyable(plan):
        await bot.answer_pre_checkout_query(
            query.id, ok=False, error_message="Тариф больше недоступен."
        )
        return
    if promo_id and not _promo_is_usable(promo):
        await bot.answer_pre_checkout_query(
            query.id,
            ok=False,
            error_message="Промокод стал недействителен.",
        )
        return

    # Extend flow: validate ownership of sub_id, skip allow-list check
    # (an existing sub may live on an inbound that's no longer attached
    # to any plan).
    if int(sub_id) > 0:
        tg_id = query.from_user.id if query.from_user is not None else None
        if tg_id is None:
            await bot.answer_pre_checkout_query(
                query.id, ok=False, error_message="Не удалось определить пользователя."
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
                error_message="Подписка недоступна для продления.",
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
            error_message="Подключение больше недоступно.",
        )
        return

    await bot.answer_pre_checkout_query(query.id, ok=True)


# ---------------------------------------------------------------------- #
# Successful payment — finalise everything
# ---------------------------------------------------------------------- #


@router.message(F.successful_payment)
async def on_successful_payment(
    message: Message,
    bot: Bot,
    user: User | None = None,
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
        plan_id, promo_id, inbound_id, sub_id = billing.parse_invoice_payload(
            payment.invoice_payload
        )
    except ValueError as exc:
        logger.error(
            "successful_payment: bad payload {!r}: {}", payment.invoice_payload, exc
        )
        await message.answer(
            "Платёж получен, но мы не смогли разобрать заказ. "
            "Свяжитесь с поддержкой — мы вернём средства или активируем подписку вручную."
        )
        return

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
        await message.answer(
            "Платёж получен, но тариф удалён. Напишите администратору — мы решим."
        )
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

    # Step 7 — keys.
    if sub is not None:
        await deliver_keys(
            bot, xui, chat_id=message.chat.id, sub=sub,
            header="✅ Оплата прошла. Подписка активна.",
        )
    elif xui_failed:
        await message.answer(
            "Оплата получена, но не удалось активировать ключ в панели VPN. "
            "Мы зафиксировали платёж и в ближайшее время администратор активирует подписку вручную."
        )


__all__ = ["router"]
