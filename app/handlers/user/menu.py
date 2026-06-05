"""User main-menu router.

Handlers
--------

* :func:`cmd_menu` — ``/menu`` command: show the main user menu.
* :func:`cb_menu` — callback ``UserCB(area='menu')``: edit the message
  back to the main menu (used as the universal "Back" target across
  the user flow).
* :func:`cb_cancel` — callback ``UserCB(area='cancel')``: clear any
  active FSM state and return to the main menu.

The active-subscription check is delegated to
:func:`app.db.repos.subscriptions.get_active_for_user` so the "Моя
подписка" button gets priority placement when applicable. See
:func:`app.keyboards.user.user_main_menu`.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import settings
from app.db.engine import get_conn
from app.db.repos import subscriptions as subs_repo
from app.db.repos.users import User
from app.i18n import DEFAULT_LANG, t
from app.keyboards.user import UserCB, user_main_menu

router = Router(name="user_menu")


async def _has_active_subscription(user_db_id: int) -> bool:
    """Return ``True`` iff the user has at least one active subscription.

    Uses :func:`app.db.repos.subscriptions.get_active_for_user`. The query
    is cheap (single indexed SELECT) so it's acceptable to run on every
    main-menu render.
    """
    async with get_conn() as conn:
        sub = await subs_repo.get_active_for_user(conn, user_db_id)
    return sub is not None


async def _can_trial(user_db_id: int) -> bool:
    """Return ``True`` iff the «🎁 Пробный период» button should be shown.

    The trial is offered only when the feature is enabled
    (:data:`app.config.settings.TRIAL_DAYS` > 0) **and** the user has not
    already claimed a trial (:func:`app.db.repos.subscriptions.has_trial`). A
    single cheap SELECT guards the latter; the former is a config read.
    """
    if int(settings.TRIAL_DAYS) <= 0:
        return False
    async with get_conn() as conn:
        return not await subs_repo.has_trial(conn, user_db_id)


async def _send_main_menu(
    message: Message,
    user: User | None,
    *,
    edit: bool,
    lang: str = DEFAULT_LANG,
) -> None:
    """Render the user main menu (either edit current message or send new)."""
    has_sub = False
    can_trial = False
    if user is not None:
        has_sub = await _has_active_subscription(user.id)
        can_trial = await _can_trial(user.id)
    kb = user_main_menu(has_subscription=has_sub, can_trial=can_trial)
    greeting = t("menu.greeting", lang)
    if edit:
        await message.edit_text(greeting, reply_markup=kb)
    else:
        await message.answer(greeting, reply_markup=kb)


@router.message(Command("menu"))
async def cmd_menu(
    message: Message, user: User | None = None, lang: str = DEFAULT_LANG
) -> None:
    """Show the user main menu in response to ``/menu``."""
    await _send_main_menu(message, user, edit=False, lang=lang)


@router.callback_query(UserCB.filter(F.area == "menu"))
async def cb_menu(
    callback: CallbackQuery, user: User | None = None, lang: str = DEFAULT_LANG
) -> None:
    """Edit the current message back to the user main menu.

    Used as the canonical "Back" callback across every user sub-flow.
    """
    if callback.message is not None:
        await _send_main_menu(callback.message, user, edit=True, lang=lang)
    await callback.answer()


@router.callback_query(UserCB.filter(F.area == "cancel"))
async def cb_cancel(
    callback: CallbackQuery,
    state: FSMContext,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Cancel any active wizard and return to the main menu."""
    await state.clear()
    if callback.message is not None:
        await _send_main_menu(callback.message, user, edit=True, lang=lang)
    await callback.answer(t("menu.cancelled", lang))


__all__ = ["router"]
