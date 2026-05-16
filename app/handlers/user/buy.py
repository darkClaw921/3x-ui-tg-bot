"""Buy-flow: plan selection → optional promo → Stars invoice →
pre_checkout → successful_payment.

Handlers
--------

UI callbacks (FSM-driven):
    * :func:`cb_open`        — ``BuyCB(action='open')``: show the plan list.
    * :func:`cb_pick_plan`   — ``BuyCB(action='plan', plan_id)``: store the
      selected plan and render the confirmation card.
    * :func:`cb_apply_promo` — ``BuyCB(action='apply_promo', plan_id)``:
      prompt the user for a promo code.
    * :func:`msg_promo_code` — message handler bound to
      :class:`BuyFlow.entering_promo`: validate the code and either go
      back to the confirmation card with a discount or re-prompt on error.
    * :func:`cb_confirm`     — ``BuyCB(action='confirm', plan_id, promo_id)``:
      build and send the Stars invoice, then clear the FSM.

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

import aiosqlite
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    Message,
    PreCheckoutQuery,
)
from loguru import logger

from app.db.engine import get_conn
from app.db.repos import payments as payments_repo
from app.db.repos import plans as plans_repo
from app.db.repos import promos as promos_repo
from app.db.repos.plans import Plan
from app.db.repos.promos import Promo
from app.db.repos.users import User
from app.handlers.user._keys import deliver_keys
from app.keyboards.user import BuyCB, confirm_kb, plans_kb
from app.services import billing, promos as promos_service, subscriptions as subs_service
from app.states.user import BuyFlow
from app.xui import XuiError, get_xui_client

router = Router(name="user_buy")


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #


def _format_confirm(plan: Plan, promo: Promo | None) -> str:
    """Render the confirmation card text (HTML).

    Shows the plan, the applied promo (if any), the resulting price and
    any bonus days. The numbers come from :func:`app.services.billing.calc_price`
    so what the user sees matches what gets charged.
    """
    price = billing.calc_price(plan, promo)
    lines = [
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
async def cb_open(callback: CallbackQuery, state: FSMContext) -> None:
    """Open the plan list and enter :class:`BuyFlow.choosing_plan`."""
    await state.clear()
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


@router.callback_query(BuyCB.filter(F.action == "plan"))
async def cb_pick_plan(
    callback: CallbackQuery,
    callback_data: BuyCB,
    state: FSMContext,
) -> None:
    """Store the chosen plan and render the confirmation card.

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

    await state.update_data(plan_id=plan.id, promo_id=promo_id)
    await state.set_state(BuyFlow.confirming)
    if callback.message is not None:
        await callback.message.edit_text(
            _format_confirm(plan, promo),
            reply_markup=confirm_kb(plan.id, promo_id=promo_id),
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

    Stores the active ``plan_id`` so the message handler knows which plan
    to validate the promo against (the per-plan check itself is a no-op
    today — promos apply to any plan — but the architecture is ready for
    plan-scoped promos in the future).
    """
    await state.update_data(plan_id=callback_data.plan_id)
    await state.set_state(BuyFlow.entering_promo)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите промокод одним сообщением:",
            reply_markup=confirm_kb(callback_data.plan_id),
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
            reply_markup=confirm_kb(plan.id),
        )
        return

    await state.update_data(promo_id=result.promo.id)
    await state.set_state(BuyFlow.confirming)
    await message.answer(
        "✅ Промокод применён.\n\n" + _format_confirm(plan, result.promo),
        reply_markup=confirm_kb(plan.id, promo_id=result.promo.id),
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
) -> None:
    """Re-validate, send the Stars invoice, and clear FSM state.

    Re-validation is a defence-in-depth: another admin might have
    deactivated the plan or exhausted the promo between selection and
    confirmation. ``pre_checkout`` will validate again at payment time.
    """
    plan_id = callback_data.plan_id
    promo_id = callback_data.promo_id or 0

    async with get_conn() as conn:
        plan = await _fetch_plan(conn, plan_id)
        promo = await _fetch_promo(conn, promo_id) if promo_id else None

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

    chat_id = callback.message.chat.id if callback.message is not None else None
    if chat_id is None:
        await callback.answer("Не удалось определить чат.", show_alert=True)
        return

    await billing.send_invoice(bot, chat_id=chat_id, plan=plan, promo=promo)
    # The state has done its job — the invoice payload carries plan_id
    # and promo_id through to pre_checkout / successful_payment.
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
        plan_id, promo_id = billing.parse_invoice_payload(query.invoice_payload)
    except ValueError as exc:
        logger.warning("pre_checkout: bad payload {!r}: {}", query.invoice_payload, exc)
        await bot.answer_pre_checkout_query(
            query.id, ok=False, error_message="Некорректный заказ."
        )
        return

    async with get_conn() as conn:
        plan = await _fetch_plan(conn, plan_id)
        promo = await _fetch_promo(conn, promo_id) if promo_id else None

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
        plan_id, promo_id = billing.parse_invoice_payload(payment.invoice_payload)
    except ValueError as exc:
        logger.error(
            "successful_payment: bad payload {!r}: {}", payment.invoice_payload, exc
        )
        await message.answer(
            "Платёж получен, но мы не смогли разобрать заказ. "
            "Свяжитесь с поддержкой — мы вернём средства или активируем подписку вручную."
        )
        return

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
    try:
        async with get_conn() as conn:
            sub = await subs_service.create_or_extend(
                conn=conn, xui=xui, user=user, plan=plan, promo=promo
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
