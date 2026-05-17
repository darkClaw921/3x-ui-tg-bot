"""Standalone promo activation flow (free-days bonuses without payment).

This module owns a short FSM (:class:`app.states.user.PromoActivate`)
plus a starter callback. Discount-only promos (``percent`` / ``flat_stars``)
are rejected here with a hint to go through the buy flow instead — they
need a plan to apply against, which only the purchase path provides.

Free-days promos require the user to pick an inbound (server) before
activation: the 3x-ui client is created on the selected inbound, so we
cannot proceed without one. The flow therefore is:

``waiting_code`` → validate code →
``choosing_inbound`` (only for ``free_days``) → ``activate_free_days``

Handlers
--------

* :func:`cb_open`   — ``PromoActCB(action='open')``: enters
  :class:`PromoActivate.waiting_code` and prompts for the code.
* :func:`msg_code`  — message handler bound to
  :class:`PromoActivate.waiting_code`: validates the code, refuses
  non-free-days types, then routes to inbound selection.
* :func:`cb_pick_inbound_for_promo` — ``InboundCB(action='pick')`` in
  :class:`PromoActivate.choosing_inbound`: re-validates the promo
  (race guard), provisions via
  :func:`app.services.subscriptions.activate_free_days`, applies the
  promo and delivers the keys.
* :func:`cb_back_inbound_for_promo` — ``InboundCB(action='back')`` in
  :class:`PromoActivate.choosing_inbound`: returns to code entry.

State separation from the buy flow
----------------------------------

The :class:`app.keyboards.user.InboundCB` factory is shared with the
buy flow (``app.handlers.user.buy``). To prevent handler collisions both
modules filter on their own FSM state — buy handlers bind to
:class:`app.states.user.BuyFlow.choosing_inbound`, promo handlers bind
to :class:`PromoActivate.choosing_inbound`.

Idempotency
-----------

The double activation guard is twofold:

1. :func:`app.services.promos.validate` rejects codes the user has
   already redeemed (one-per-user policy). It runs both when the user
   enters the code AND again right before activation (anti-race).
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
from app.keyboards.user import InboundCB, PromoActCB, cancel_kb, inbound_select_kb
from app.services import promos as promos_service, subscriptions as subs_service
from app.services.inbounds import InboundOption, list_user_inbounds
from app.states.user import PromoActivate
from app.xui import XuiError, get_xui_client

router = Router(name="user_promo")


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #


def _options_to_jsonable(options: list[InboundOption]) -> list[dict]:
    """Serialise :class:`InboundOption` for FSM storage.

    aiogram's FSM storage round-trips data through JSON, so frozen
    dataclasses must be flattened to plain dicts before being stashed.
    Mirrors the helper in ``app.handlers.user.buy``.
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


# ---------------------------------------------------------------------- #
# Entry point
# ---------------------------------------------------------------------- #


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


# ---------------------------------------------------------------------- #
# Code entry — validate and route to inbound selection
# ---------------------------------------------------------------------- #


@router.message(PromoActivate.waiting_code)
async def msg_code(
    message: Message,
    state: FSMContext,
    user: User | None = None,
) -> None:
    """Validate the code, then route to inbound selection for free-days.

    Branching:

    * Code invalid (not found / expired / capacity / already redeemed) —
      show the error and stay in :class:`PromoActivate.waiting_code`.
    * Code is a discount type (``percent`` / ``flat_stars``) — clear the
      state and tell the user to use the buy flow.
    * Code is ``free_days``:
        * Fetch the list of available inbounds from 3x-ui (cached).
        * If the panel is unreachable — apologise, clear the state.
        * If the list is empty — apologise, clear the state.
        * Otherwise stash ``promo_id`` + ``inbound_options`` in the FSM
          and enter :class:`PromoActivate.choosing_inbound`.
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

    # Fetch available inbounds so the user can pick one. The panel may
    # be temporarily unreachable — in that case we don't redeem the
    # promo and ask the user to retry later.
    try:
        xui = await get_xui_client()
        options = await list_user_inbounds(xui)
    except XuiError as exc:
        logger.warning(
            "promo msg_code: failed to list inbounds for user {} promo {}: {}",
            user.id,
            promo.id,
            exc,
        )
        await state.clear()
        await message.answer(
            "Не удалось получить список подключений. Попробуйте позже.",
        )
        return

    if not options:
        await state.clear()
        await message.answer(
            "Нет доступных подключений. Попробуйте позже.",
        )
        return

    await state.update_data(
        promo_id=promo.id,
        inbound_options=_options_to_jsonable(options),
    )
    await state.set_state(PromoActivate.choosing_inbound)
    await message.answer(
        "Выберите подключение для активации промокода:",
        reply_markup=inbound_select_kb(0, options, promo_id=promo.id),
    )


# ---------------------------------------------------------------------- #
# Inbound selection (free-days promo)
# ---------------------------------------------------------------------- #


@router.callback_query(
    PromoActivate.choosing_inbound, InboundCB.filter(F.action == "pick")
)
async def cb_pick_inbound_for_promo(
    callback: CallbackQuery,
    callback_data: InboundCB,
    state: FSMContext,
    bot: Bot,
    user: User | None = None,
) -> None:
    """Activate the free-days promo on the selected inbound.

    Steps:

    1. Pull ``promo_id`` from the FSM (fall back to the callback's
       ``promo_id`` if missing) and ``inbound_id`` from the callback.
    2. Re-validate the promo via :func:`app.services.promos.validate`
       to guard against a race (admin invalidates / another tab redeems
       between code entry and inbound pick).
    3. Verify ``inbound_id`` is one of the options we offered (the
       options snapshot lives in the FSM).
    4. Call :func:`app.services.subscriptions.activate_free_days` with
       the chosen ``inbound_id``.
    5. Best-effort :func:`app.services.promos.apply` (race here is
       acceptable — the subscription is already created).
    6. Deliver keys, clear FSM state.

    Error handling:

    * Promo re-validation fails — show the error, stay in
      :class:`PromoActivate.choosing_inbound` so the user can pick again
      or cancel.
    * ``inbound_id`` not in our offered options — show alert, stay.
    * :class:`XuiError` during provisioning — apologise; the promo is
      NOT redeemed so the user can retry once the panel is back.
    """
    if user is None:
        await callback.answer("Нужно нажать /start, чтобы начать.", show_alert=True)
        return

    data = await state.get_data()
    promo_id = int(data.get("promo_id") or callback_data.promo_id or 0)
    inbound_id = int(callback_data.inbound_id or 0)

    if not promo_id or not inbound_id:
        await callback.answer(
            "Сессия устарела. Введите промокод заново.",
            show_alert=True,
        )
        await state.clear()
        return

    # Re-validate the promo: capacity / expiry / already-redeemed may
    # have changed since the user typed the code.
    async with get_conn() as conn:
        from app.db.repos import promos as promos_repo

        promo = await promos_repo.get(conn, promo_id)
        if promo is None:
            await callback.answer(
                "Промокод больше недоступен.", show_alert=True
            )
            await state.clear()
            return
        result = await promos_service.validate(
            conn, code=promo.code, user_id=user.id, plan=None
        )

    if not result.is_valid or result.promo is None:
        await callback.answer(
            result.error or "Промокод стал недействителен.",
            show_alert=True,
        )
        # Keep the user in the inbound-selection step? No — the promo
        # is dead so there's nothing to activate. Clear the state.
        await state.clear()
        if callback.message is not None:
            await callback.message.edit_text(
                (result.error or "Промокод стал недействителен.")
                + " Попробуйте другой код.",
            )
        return

    promo = result.promo
    if promo.type != "free_days":
        # Defence-in-depth — the type couldn't change normally, but
        # never trust callback data alone.
        await state.clear()
        await callback.answer(
            "Этот промокод нужно применять при покупке тарифа.",
            show_alert=True,
        )
        return

    # Verify the inbound is one we actually offered. The options
    # snapshot in the FSM is authoritative here — if someone crafted a
    # callback with an arbitrary inbound_id we reject it.
    raw_options = data.get("inbound_options") or []
    offered_ids = {int(it.get("id", 0)) for it in raw_options if isinstance(it, dict)}
    if offered_ids and inbound_id not in offered_ids:
        await callback.answer(
            "Подключение недоступно. Выберите из списка.",
            show_alert=True,
        )
        return

    # xui-first via the service. If the panel call fails the promo is
    # NOT redeemed and the user can retry once the panel is back.
    xui = await get_xui_client()
    try:
        async with get_conn() as conn:
            sub = await subs_service.activate_free_days(
                conn=conn, xui=xui, user=user, promo=promo, inbound_id=inbound_id
            )
    except XuiError as exc:
        logger.error(
            "free_days: xui provisioning failed for user {} promo {} inbound {}: {}",
            user.id,
            promo.id,
            inbound_id,
            exc,
        )
        await callback.answer()
        if callback.message is not None:
            await callback.message.edit_text(
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
    chat_id = callback.message.chat.id if callback.message is not None else None
    if chat_id is None:
        await callback.answer("Промокод активирован.", show_alert=True)
        return
    await deliver_keys(
        bot,
        xui,
        chat_id=chat_id,
        sub=sub,
        header=f"✅ Промокод <code>{promo.code}</code> активирован.",
    )
    await callback.answer()


@router.callback_query(
    PromoActivate.choosing_inbound, InboundCB.filter(F.action == "back")
)
async def cb_back_inbound_for_promo(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """Return from the inbound-selection step back to code entry.

    Clears the cached ``promo_id`` and ``inbound_options`` (the user
    might type a different code next).
    """
    await state.set_state(PromoActivate.waiting_code)
    await state.update_data(promo_id=0, inbound_options=None)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите промокод одним сообщением:",
            reply_markup=cancel_kb(),
        )
    await callback.answer()


__all__ = ["router"]
