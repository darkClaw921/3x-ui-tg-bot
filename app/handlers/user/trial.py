"""Free-trial activation flow.

A one-per-user free trial: the «🎁 Пробный период» button (shown by
:func:`app.keyboards.user.user_main_menu` only when ``can_trial``) starts this
short wizard. There is no plan step — the trial's length / traffic come from
:data:`app.config.settings.TRIAL_DAYS` / ``TRIAL_TRAFFIC_GB`` — only an inbound
(server) must be picked, after which
:func:`app.services.subscriptions.activate_trial` provisions a brand-new trial
subscription and the keys are delivered.

Handlers
--------

* :func:`cb_open` — ``TrialCB(action='open')``: re-checks the feature is enabled
  and the user has not already claimed a trial, then either auto-activates (one
  inbound) or enters :class:`app.states.user.TrialFlow.choosing_inbound`.
* :func:`cb_pick_inbound` — ``InboundCB(action='pick')`` bound to
  :class:`TrialFlow.choosing_inbound`: validates the picked inbound was offered,
  activates the trial and delivers keys.
* :func:`cb_back_inbound` — ``InboundCB(action='back')`` in the trial state:
  cancels back to the main menu.

The shared :class:`app.keyboards.user.InboundCB` factory is reused; the state
filter (:class:`TrialFlow.choosing_inbound`) keeps these handlers from colliding
with the buy / promo inbound steps.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from loguru import logger

from app.config import settings
from app.db.engine import get_conn
from app.db.repos import subscriptions as subs_repo
from app.db.repos.users import User
from app.handlers.user._keys import deliver_keys
from app.i18n import DEFAULT_LANG, t
from app.keyboards.user import InboundCB, TrialCB, inbound_select_kb
from app.services import subscriptions as subs_service
from app.services.inbounds import InboundOption, list_user_inbounds
from app.states.user import TrialFlow
from app.xui import XuiError, get_xui_client

router = Router(name="user_trial")


def _options_to_jsonable(options: list[InboundOption]) -> list[dict]:
    """Serialise :class:`InboundOption` for FSM storage (JSON round-trip)."""
    return [
        {"id": o.id, "remark": o.remark, "port": o.port, "enabled": o.enabled}
        for o in options
    ]


async def _trial_enabled_for(user: User) -> bool:
    """Return ``True`` iff ``user`` may still activate a trial.

    Mirrors the menu's gate: the feature must be enabled
    (:data:`app.config.settings.TRIAL_DAYS` > 0) and the user must not already
    hold a trial.
    """
    if int(settings.TRIAL_DAYS) <= 0:
        return False
    async with get_conn() as conn:
        return not await subs_repo.has_trial(conn, user.id)


async def _activate_and_deliver(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    user: User,
    inbound_id: int,
    lang: str,
) -> None:
    """Provision the trial on ``inbound_id`` and deliver the keys.

    Shared tail of the auto-activate (single inbound) and the explicit
    inbound-pick branches. Maps
    :class:`app.services.subscriptions.TrialAlreadyUsedError` to a localized
    alert and :class:`app.xui.XuiError` to an apology, clearing the FSM in both
    error cases so the user is not stuck mid-wizard.
    """
    xui = await get_xui_client()
    try:
        async with get_conn() as conn:
            sub = await subs_service.activate_trial(
                conn,
                xui,
                user,
                inbound_id=int(inbound_id),
                days=int(settings.TRIAL_DAYS),
                traffic_gb=int(settings.TRIAL_TRAFFIC_GB),
            )
    except subs_service.TrialAlreadyUsedError:
        await state.clear()
        await callback.answer(t("trial.already_used", lang), show_alert=True)
        return
    except XuiError as exc:
        logger.error(
            "trial: xui provisioning failed for user {} inbound {}: {}",
            user.id,
            inbound_id,
            exc,
        )
        await state.clear()
        if callback.message is not None:
            await callback.message.edit_text(t("trial.activation_failed", lang))
        await callback.answer()
        return

    await state.clear()
    chat_id = callback.message.chat.id if callback.message is not None else None
    if chat_id is None:
        await callback.answer()
        return
    await deliver_keys(
        bot,
        xui,
        chat_id=chat_id,
        sub=sub,
        header=t("trial.header_activated", lang, days=int(settings.TRIAL_DAYS)),
        lang=lang,
    )
    await callback.answer()


@router.callback_query(TrialCB.filter(F.action == "open"))
async def cb_open(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Start the trial wizard: pick an inbound (or auto-activate on one).

    Re-checks the feature gate (defence-in-depth — the button could be tapped
    from a stale keyboard after the feature was disabled or the trial already
    claimed). When exactly one inbound is available the inbound step is skipped
    and the trial is activated immediately; otherwise the selection keyboard is
    shown under :class:`TrialFlow.choosing_inbound`.
    """
    if user is None:
        await callback.answer(t("trial.need_start", lang), show_alert=True)
        return
    if int(settings.TRIAL_DAYS) <= 0:
        await callback.answer(t("trial.disabled", lang), show_alert=True)
        return
    if not await _trial_enabled_for(user):
        await callback.answer(t("trial.already_used", lang), show_alert=True)
        return

    try:
        xui = await get_xui_client()
        options = await list_user_inbounds(xui)
    except XuiError as exc:
        logger.warning("trial cb_open: list_user_inbounds failed: {}", exc)
        await callback.answer(t("trial.inbounds_unavailable", lang), show_alert=True)
        return

    if not options:
        await callback.answer(t("trial.no_inbounds", lang), show_alert=True)
        return

    if len(options) == 1:
        await _activate_and_deliver(
            callback, state, bot, user, int(options[0].id), lang
        )
        return

    await state.set_state(TrialFlow.choosing_inbound)
    await state.update_data(inbound_options=_options_to_jsonable(options))
    if callback.message is not None:
        await callback.message.edit_text(
            t("trial.choose_inbound", lang),
            reply_markup=inbound_select_kb(0, options, lang=lang),
        )
    await callback.answer()


@router.callback_query(
    TrialFlow.choosing_inbound, InboundCB.filter(F.action == "pick")
)
async def cb_pick_inbound(
    callback: CallbackQuery,
    callback_data: InboundCB,
    state: FSMContext,
    bot: Bot,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Activate the trial on the inbound the user picked.

    Verifies ``inbound_id`` is one of the options offered (the snapshot lives in
    the FSM) to reject a crafted callback, then provisions + delivers.
    """
    if user is None:
        await callback.answer(t("trial.need_start", lang), show_alert=True)
        return

    inbound_id = int(callback_data.inbound_id or 0)
    data = await state.get_data()
    raw_options = data.get("inbound_options") or []
    offered_ids = {int(it.get("id", 0)) for it in raw_options if isinstance(it, dict)}
    if not inbound_id or (offered_ids and inbound_id not in offered_ids):
        await callback.answer(t("trial.no_inbounds", lang), show_alert=True)
        return

    await _activate_and_deliver(callback, state, bot, user, inbound_id, lang)


@router.callback_query(
    TrialFlow.choosing_inbound, InboundCB.filter(F.action == "back")
)
async def cb_back_inbound(
    callback: CallbackQuery,
    state: FSMContext,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Cancel the trial wizard and return to the main menu."""
    await state.clear()
    if callback.message is not None:
        from app.handlers.user.menu import _send_main_menu

        await _send_main_menu(callback.message, user, edit=True, lang=lang)
    await callback.answer()


__all__ = ["router"]
