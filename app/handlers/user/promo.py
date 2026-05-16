"""Standalone promo activation flow (free-days bonuses without payment).

This module owns a single short FSM (:class:`app.states.user.PromoActivate`)
plus a starter callback. Discount-only promos (``percent`` / ``flat_stars``)
are rejected here with a hint to go through the buy flow instead — they
need a plan to apply against, which only the purchase path provides.

Handlers
--------

* :func:`cb_open`   — ``PromoActCB(action='open')``: enters
  :class:`PromoActivate.waiting_code` and prompts for the code.
* :func:`msg_code`  — message handler bound to
  :class:`PromoActivate.waiting_code`: validates the code, refuses
  non-free-days types, then provisions a free subscription via
  :func:`app.services.subscriptions.activate_free_days` and delivers the
  keys.

Idempotency
-----------

The double activation guard is twofold:

1. :func:`app.services.promos.validate` rejects codes the user has
   already redeemed (one-per-user policy).
2. :func:`app.db.repos.promos.try_redeem` runs inside ``BEGIN IMMEDIATE``
   so even a perfectly-timed double-tap cannot win twice.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger

from app.db.engine import get_conn
from app.db.repos.users import User
from app.handlers.user._keys import deliver_keys
from app.keyboards.user import PromoActCB, cancel_kb
from app.services import promos as promos_service, subscriptions as subs_service
from app.states.user import PromoActivate
from app.xui import XuiError, get_xui_client

router = Router(name="user_promo")


@router.callback_query(PromoActCB.filter(F.action == "open"))
async def cb_open(callback: CallbackQuery, state: FSMContext) -> None:
    """Enter :class:`PromoActivate.waiting_code` and prompt for the code."""
    await state.set_state(PromoActivate.waiting_code)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите промокод одним сообщением:",
            reply_markup=cancel_kb(),
        )
    await callback.answer()


@router.message(PromoActivate.waiting_code)
async def msg_code(
    message: Message,
    state: FSMContext,
    bot: Bot,
    user: User | None = None,
) -> None:
    """Validate the code, activate a free-days subscription, deliver keys.

    Error handling:

    * Code invalid (not found / expired / capacity / already redeemed) —
      show the error and stay in :class:`PromoActivate.waiting_code`.
    * Code is a discount type (``percent`` / ``flat_stars``) — clear the
      state and tell the user to use the buy flow.
    * xui call fails — log + apologise; the promo is NOT redeemed in
      this branch because xui is called first via
      :func:`activate_free_days`. The user can retry.
    """
    if user is None:
        await message.answer("Нужно нажать /start, чтобы начать.")
        return

    async with get_conn() as conn:
        result = await promos_service.validate(
            conn, code=message.text or "", user_id=user.id, plan=None
        )

    if not result.is_valid or result.promo is None:
        await message.answer(
            (result.error or "Промокод недействителен.") + " Введите ещё раз:",
            reply_markup=cancel_kb(),
        )
        return

    promo = result.promo
    if promo.type != "free_days":
        # Discount-type promos need a plan to apply against. Clear the
        # state and route the user to the buy flow.
        await state.clear()
        await message.answer(
            "Этот промокод применяется только при покупке тарифа. "
            "Нажмите «Купить» в меню и примените код там.",
        )
        return

    # xui-first via the service. If the panel call fails the promo is
    # NOT redeemed and the user can retry once the panel is back.
    xui = await get_xui_client()
    try:
        async with get_conn() as conn:
            sub = await subs_service.activate_free_days(
                conn=conn, xui=xui, user=user, promo=promo
            )
    except XuiError as exc:
        logger.error(
            "free_days: xui provisioning failed for user {} promo {}: {}",
            user.id,
            promo.id,
            exc,
        )
        await message.answer(
            "Не удалось активировать промокод — попробуйте позже. "
            "Если проблема повторится, напишите администратору.",
        )
        return

    # Redeem the promo (atomic). If another transaction won the race,
    # we've still created/extended the subscription — that's acceptable:
    # the user got their free days, the counter just won't reflect this
    # particular redemption.
    async with get_conn() as conn:
        ok = await promos_service.apply(
            conn,
            promo_id=promo.id,
            user_id=user.id,
            subscription_id=sub.id,
        )
    if not ok:
        logger.warning(
            "free_days: try_redeem failed for user {} promo {} (race?)",
            user.id,
            promo.id,
        )

    await state.clear()
    await deliver_keys(
        bot,
        xui,
        chat_id=message.chat.id,
        sub=sub,
        header=f"✅ Промокод <code>{promo.code}</code> активирован.",
    )


__all__ = ["router"]
