"""Standalone promo activation flow (free-days bonuses without payment).

This module owns a short FSM (:class:`app.states.user.PromoActivate`)
plus a starter callback. Discount-only promos (``percent`` / ``flat_stars``)
are rejected here with a hint to go through the buy flow instead — they
need a plan to apply against, which only the purchase path provides.

Free-days promos require the user to pick an inbound (server) before
activation: the 3x-ui client is created on the selected inbound, so we
cannot proceed without one. The flow therefore is:

``waiting_code`` → validate code →
``choosing_action`` (only for ``free_days`` AND only when the user
already has 1+ active subscriptions) → either
``choosing_inbound`` (new-sub branch) → ``activate_free_days(extend_sub_id=None)``
OR direct ``activate_free_days(extend_sub_id=N)`` (extend branch — the
inbound is inherited from the existing subscription).

Handlers
--------

* :func:`cb_open`   — ``PromoActCB(action='open')``: enters
  :class:`PromoActivate.waiting_code` and prompts for the code.
* :func:`msg_code`  — message handler bound to
  :class:`PromoActivate.waiting_code`: validates the code, refuses
  non-free-days types, then either routes to the action screen
  (:class:`PromoActivate.choosing_action`, when the user has active
  subs) or directly to inbound selection.
* :func:`cb_pick_action_extend_promo` — ``PromoActCB(action='extend')``
  in :class:`PromoActivate.choosing_action`: re-validates the promo +
  ownership of the target sub, then calls
  :func:`app.services.subscriptions.activate_free_days` with
  ``extend_sub_id=N`` (inbound inherited from the existing sub).
* :func:`cb_pick_action_new_promo` — ``PromoActCB(action='new')`` in
  :class:`PromoActivate.choosing_action`: transitions to
  :class:`PromoActivate.choosing_inbound` with the cached inbound
  options (re-fetched if missing).
* :func:`cb_pick_inbound_for_promo` — ``InboundCB(action='pick')`` in
  :class:`PromoActivate.choosing_inbound`: re-validates the promo
  (race guard), provisions via
  :func:`app.services.subscriptions.activate_free_days` (``extend_sub_id=None``),
  applies the promo and delivers the keys.
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
from app.db.repos import subscriptions as subs_repo
from app.db.repos.users import User
from app.handlers.user._keys import deliver_keys
from app.i18n import DEFAULT_LANG, t
from app.keyboards.user import (
    InboundCB,
    PromoActCB,
    cancel_kb,
    inbound_select_kb,
    promo_action_kb,
)
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
async def cb_open(
    callback: CallbackQuery, state: FSMContext, lang: str = DEFAULT_LANG
) -> None:
    """Enter :class:`PromoActivate.waiting_code` and prompt for the code."""
    await state.set_state(PromoActivate.waiting_code)
    if callback.message is not None:
        await callback.message.edit_text(
            t("promo.enter_code", lang),
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
    lang: str = DEFAULT_LANG,
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
        await message.answer(t("promo.need_start", lang))
        return

    async with get_conn() as conn:
        result = await promos_service.validate(
            conn, code=message.text or "", user_id=user.id, plan=None
        )

    if not result.is_valid or result.promo is None:
        await message.answer(
            t(
                "promo.invalid_retry",
                lang,
                error=result.error or t("promo.default_invalid", lang),
            ),
            reply_markup=cancel_kb(),
        )
        return

    promo = result.promo
    if promo.type != "free_days":
        # Discount-type promos need a plan to apply against. Clear the
        # state and route the user to the buy flow.
        await state.clear()
        await message.answer(t("promo.only_on_purchase", lang))
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
        await message.answer(t("promo.inbounds_unavailable", lang))
        return

    if not options:
        await state.clear()
        await message.answer(t("promo.no_inbounds", lang))
        return

    # If the user already has one or more active subscriptions, surface
    # the "продлить vs новая" action screen so the free-days bonus can
    # extend an existing subscription instead of always provisioning a
    # new one. Otherwise fall through to the regular inbound-selection
    # step.
    async with get_conn() as conn:
        active = await subs_repo.list_active_for_user(conn, user.id)

    if active:
        remarks = {o.id: o.remark or f"#{o.id}" for o in options}
        await state.update_data(
            promo_id=promo.id,
            inbound_options=_options_to_jsonable(options),
        )
        await state.set_state(PromoActivate.choosing_action)
        await message.answer(
            t("promo.has_active_choose", lang),
            reply_markup=promo_action_kb(active, remarks),
        )
        return

    await state.update_data(
        promo_id=promo.id,
        inbound_options=_options_to_jsonable(options),
    )
    await state.set_state(PromoActivate.choosing_inbound)
    await message.answer(
        t("promo.choose_inbound", lang),
        reply_markup=inbound_select_kb(0, options, promo_id=promo.id),
    )


# ---------------------------------------------------------------------- #
# Action picker (only shown when the user has 1+ active subscriptions)
# ---------------------------------------------------------------------- #


async def _activate_promo_for_sub(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    user: User,
    promo_id: int,
    extend_sub_id: int | None,
    inbound_id: int,
    lang: str = DEFAULT_LANG,
) -> None:
    """Shared tail used by :func:`cb_pick_action_extend_promo` and the
    single-inbound branch of :func:`cb_pick_action_new_promo`.

    Re-validates the promo (race guard), then calls
    :func:`app.services.subscriptions.activate_free_days` with the
    supplied ``extend_sub_id`` / ``inbound_id``. Applies the promo
    best-effort, delivers keys, clears the FSM. The caller is
    responsible for any ownership / inbound-membership checks specific
    to its branch.
    """
    async with get_conn() as conn:
        from app.db.repos import promos as promos_repo

        promo = await promos_repo.get(conn, promo_id)
        if promo is None:
            await callback.answer(t("promo.no_longer_available", lang), show_alert=True)
            await state.clear()
            return
        result = await promos_service.validate(
            conn, code=promo.code, user_id=user.id, plan=None
        )

    if not result.is_valid or result.promo is None:
        error = result.error or t("promo.became_invalid", lang)
        await callback.answer(error, show_alert=True)
        await state.clear()
        if callback.message is not None:
            await callback.message.edit_text(
                t("promo.became_invalid_retry", lang, error=error),
            )
        return

    promo = result.promo
    if promo.type != "free_days":
        await state.clear()
        await callback.answer(t("promo.apply_on_purchase", lang), show_alert=True)
        return

    xui = await get_xui_client()
    try:
        async with get_conn() as conn:
            sub = await subs_service.activate_free_days(
                conn=conn,
                xui=xui,
                user=user,
                promo=promo,
                inbound_id=inbound_id,
                extend_sub_id=extend_sub_id,
            )
    except XuiError as exc:
        logger.error(
            "free_days(action): xui provisioning failed for user {} promo {} "
            "inbound {} extend_sub_id {}: {}",
            user.id,
            promo.id,
            inbound_id,
            extend_sub_id,
            exc,
        )
        await callback.answer()
        if callback.message is not None:
            await callback.message.edit_text(t("promo.activation_failed", lang))
        return

    async with get_conn() as conn:
        ok = await promos_service.apply(
            conn,
            promo_id=promo.id,
            user_id=user.id,
            subscription_id=sub.id,
        )
    if not ok:
        logger.warning(
            "free_days(action): try_redeem failed for user {} promo {} (race?)",
            user.id,
            promo.id,
        )

    await state.clear()
    chat_id = callback.message.chat.id if callback.message is not None else None
    if chat_id is None:
        await callback.answer(t("promo.activated_alert", lang), show_alert=True)
        return
    if extend_sub_id is not None:
        header = t("promo.header_extended", lang, code=promo.code, sub_id=sub.id)
    else:
        header = t("promo.header_activated", lang, code=promo.code)
    await deliver_keys(
        bot,
        xui,
        chat_id=chat_id,
        sub=sub,
        header=header,
        lang=lang,
    )
    await callback.answer()


@router.callback_query(
    PromoActivate.choosing_action, PromoActCB.filter(F.action == "extend")
)
async def cb_pick_action_extend_promo(
    callback: CallbackQuery,
    callback_data: PromoActCB,
    state: FSMContext,
    bot: Bot,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """User picked "🔄 Продлить #N" on the free-days action screen.

    Re-validates the promo (the user might have redeemed it from another
    tab, the admin might have invalidated it, …), verifies ownership of
    the target subscription, then provisions via
    :func:`app.services.subscriptions.activate_free_days` with
    ``extend_sub_id=N``. The chosen ``inbound_id`` is inherited from the
    existing subscription so the user's existing client keeps the same
    server (and no allow-list check is needed — the inbound may have
    been detached from any plan).
    """
    if user is None:
        await callback.answer(t("promo.need_start", lang), show_alert=True)
        return

    sub_id = int(callback_data.sub_id or 0)
    if sub_id <= 0:
        await callback.answer(t("promo.no_sub_specified", lang), show_alert=True)
        return

    data = await state.get_data()
    promo_id = int(data.get("promo_id") or 0)
    if not promo_id:
        await callback.answer(t("promo.session_expired", lang), show_alert=True)
        await state.clear()
        return

    async with get_conn() as conn:
        sub = await subs_repo.get(conn, sub_id)
    if sub is None or sub.user_id != user.id or sub.status != "active":
        await callback.answer(t("promo.sub_unavailable_extend", lang), show_alert=True)
        return

    await _activate_promo_for_sub(
        callback,
        state,
        bot,
        user,
        promo_id=promo_id,
        extend_sub_id=sub.id,
        inbound_id=int(sub.xui_inbound_id),
        lang=lang,
    )


@router.callback_query(
    PromoActivate.choosing_action, PromoActCB.filter(F.action == "new")
)
async def cb_pick_action_new_promo(
    callback: CallbackQuery,
    state: FSMContext,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """User picked "🆕 Новая подписка" on the free-days action screen.

    Transitions to :class:`PromoActivate.choosing_inbound` and renders
    the inbound-selection keyboard. The inbound options snapshot is
    re-used from the FSM (populated in :func:`msg_code` before the
    action screen was shown) when present; if missing for any reason it
    is re-fetched via :func:`app.services.inbounds.list_user_inbounds`.
    """
    if user is None:
        await callback.answer(t("promo.need_start", lang), show_alert=True)
        return

    data = await state.get_data()
    promo_id = int(data.get("promo_id") or 0)
    if not promo_id:
        await callback.answer(t("promo.session_expired", lang), show_alert=True)
        await state.clear()
        return

    raw_options = data.get("inbound_options") or []
    options: list[InboundOption] = []
    if isinstance(raw_options, list) and raw_options:
        options = _jsonable_to_options(raw_options)

    if not options:
        # Defence-in-depth — options should already be in the FSM from
        # msg_code. Re-fetch best-effort if not.
        try:
            xui = await get_xui_client()
            options = await list_user_inbounds(xui)
        except XuiError as exc:
            logger.warning(
                "cb_pick_action_new_promo: failed to list inbounds for user {} "
                "promo {}: {}",
                user.id,
                promo_id,
                exc,
            )
            await callback.answer(t("promo.inbounds_unavailable", lang), show_alert=True)
            return
        if not options:
            await callback.answer(t("promo.no_inbounds", lang), show_alert=True)
            return
        await state.update_data(inbound_options=_options_to_jsonable(options))

    await state.set_state(PromoActivate.choosing_inbound)
    if callback.message is not None:
        await callback.message.edit_text(
            t("promo.choose_inbound", lang),
            reply_markup=inbound_select_kb(0, options, promo_id=promo_id),
        )
    await callback.answer()


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
    lang: str = DEFAULT_LANG,
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
        await callback.answer(t("promo.need_start", lang), show_alert=True)
        return

    data = await state.get_data()
    promo_id = int(data.get("promo_id") or callback_data.promo_id or 0)
    inbound_id = int(callback_data.inbound_id or 0)

    if not promo_id or not inbound_id:
        await callback.answer(t("promo.session_expired", lang), show_alert=True)
        await state.clear()
        return

    # Re-validate the promo: capacity / expiry / already-redeemed may
    # have changed since the user typed the code.
    async with get_conn() as conn:
        from app.db.repos import promos as promos_repo

        promo = await promos_repo.get(conn, promo_id)
        if promo is None:
            await callback.answer(t("promo.no_longer_available", lang), show_alert=True)
            await state.clear()
            return
        result = await promos_service.validate(
            conn, code=promo.code, user_id=user.id, plan=None
        )

    if not result.is_valid or result.promo is None:
        error = result.error or t("promo.became_invalid", lang)
        await callback.answer(error, show_alert=True)
        # Keep the user in the inbound-selection step? No — the promo
        # is dead so there's nothing to activate. Clear the state.
        await state.clear()
        if callback.message is not None:
            await callback.message.edit_text(
                t("promo.became_invalid_retry", lang, error=error),
            )
        return

    promo = result.promo
    if promo.type != "free_days":
        # Defence-in-depth — the type couldn't change normally, but
        # never trust callback data alone.
        await state.clear()
        await callback.answer(t("promo.apply_on_purchase", lang), show_alert=True)
        return

    # Verify the inbound is one we actually offered. The options
    # snapshot in the FSM is authoritative here — if someone crafted a
    # callback with an arbitrary inbound_id we reject it.
    raw_options = data.get("inbound_options") or []
    offered_ids = {int(it.get("id", 0)) for it in raw_options if isinstance(it, dict)}
    if offered_ids and inbound_id not in offered_ids:
        await callback.answer(t("promo.inbound_unavailable_pick", lang), show_alert=True)
        return

    # xui-first via the service. If the panel call fails the promo is
    # NOT redeemed and the user can retry once the panel is back.
    xui = await get_xui_client()
    try:
        async with get_conn() as conn:
            sub = await subs_service.activate_free_days(
                conn=conn,
                xui=xui,
                user=user,
                promo=promo,
                inbound_id=inbound_id,
                extend_sub_id=None,
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
            await callback.message.edit_text(t("promo.activation_failed", lang))
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
        await callback.answer(t("promo.activated_alert", lang), show_alert=True)
        return
    await deliver_keys(
        bot,
        xui,
        chat_id=chat_id,
        sub=sub,
        header=t("promo.header_activated", lang, code=promo.code),
        lang=lang,
    )
    await callback.answer()


@router.callback_query(
    PromoActivate.choosing_inbound, InboundCB.filter(F.action == "back")
)
async def cb_back_inbound_for_promo(
    callback: CallbackQuery,
    state: FSMContext,
    lang: str = DEFAULT_LANG,
) -> None:
    """Return from the inbound-selection step back to code entry.

    Clears the cached ``promo_id`` and ``inbound_options`` (the user
    might type a different code next).
    """
    await state.set_state(PromoActivate.waiting_code)
    await state.update_data(promo_id=0, inbound_options=None)
    if callback.message is not None:
        await callback.message.edit_text(
            t("promo.enter_code", lang),
            reply_markup=cancel_kb(),
        )
    await callback.answer()


__all__ = ["router"]
