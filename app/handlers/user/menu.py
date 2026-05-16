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

from app.db.engine import get_conn
from app.db.repos import subscriptions as subs_repo
from app.db.repos.users import User
from app.keyboards.user import UserCB, user_main_menu

router = Router(name="user_menu")


_GREETING = "Главное меню. Что делаем?"


async def _has_active_subscription(user_db_id: int) -> bool:
    """Return ``True`` iff the user has at least one active subscription.

    Uses :func:`app.db.repos.subscriptions.get_active_for_user`. The query
    is cheap (single indexed SELECT) so it's acceptable to run on every
    main-menu render.
    """
    async with get_conn() as conn:
        sub = await subs_repo.get_active_for_user(conn, user_db_id)
    return sub is not None


async def _send_main_menu(message: Message, user: User | None, *, edit: bool) -> None:
    """Render the user main menu (either edit current message or send new)."""
    has_sub = False
    if user is not None:
        has_sub = await _has_active_subscription(user.id)
    kb = user_main_menu(has_subscription=has_sub)
    if edit:
        await message.edit_text(_GREETING, reply_markup=kb)
    else:
        await message.answer(_GREETING, reply_markup=kb)


@router.message(Command("menu"))
async def cmd_menu(message: Message, user: User | None = None) -> None:
    """Show the user main menu in response to ``/menu``."""
    await _send_main_menu(message, user, edit=False)


@router.callback_query(UserCB.filter(F.area == "menu"))
async def cb_menu(callback: CallbackQuery, user: User | None = None) -> None:
    """Edit the current message back to the user main menu.

    Used as the canonical "Back" callback across every user sub-flow.
    """
    if callback.message is not None:
        await _send_main_menu(callback.message, user, edit=True)
    await callback.answer()


@router.callback_query(UserCB.filter(F.area == "cancel"))
async def cb_cancel(
    callback: CallbackQuery,
    state: FSMContext,
    user: User | None = None,
) -> None:
    """Cancel any active wizard and return to the main menu."""
    await state.clear()
    if callback.message is not None:
        await _send_main_menu(callback.message, user, edit=True)
    await callback.answer("Отменено")


__all__ = ["router"]
