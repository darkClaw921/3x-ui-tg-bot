"""``/admin`` command + main-menu navigation callbacks.

The router exposed here lives under the admin parent router (see
:mod:`app.handlers.admin.__init__`) and therefore inherits the
``AdminOnlyMiddleware`` gate — no per-handler ``is_admin`` checks needed.

Handlers
--------

* :func:`cmd_admin` — ``/admin``: replies with the main admin menu.
* :func:`open_main` — callback ``AdminCB(area=main, action=back|open)`` and
  any sub-area ``back`` press; edits the current message back to the main
  menu so the dialog tree feels stable instead of leaking new messages.
* :func:`cancel_fsm` — ``AdminCB(area=*, action=cancel)``: clears any FSM
  state and returns to the main menu. Used as a single canonical cancel
  button across every wizard.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.admin import AdminCB, admin_main_menu

router = Router(name="admin_menu")


_GREETING = "Админ-меню. Выберите раздел:"


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    """Respond to ``/admin`` with the top-level admin menu."""
    await message.answer(_GREETING, reply_markup=admin_main_menu())


@router.callback_query(AdminCB.filter((F.area == "main") & (F.action.in_({"open", "back"}))))
async def open_main(callback: CallbackQuery) -> None:
    """Edit the current message back to the main admin menu."""
    if callback.message is not None:
        await callback.message.edit_text(_GREETING, reply_markup=admin_main_menu())
    await callback.answer()


@router.callback_query(AdminCB.filter(F.action == "cancel"))
async def cancel_fsm(callback: CallbackQuery, state: FSMContext) -> None:
    """Clear any active FSM state and return to the admin main menu."""
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text(
            "Отменено. " + _GREETING,
            reply_markup=admin_main_menu(),
        )
    await callback.answer("Отменено")


__all__ = ["router"]
