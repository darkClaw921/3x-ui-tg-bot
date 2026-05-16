"""``/start`` command router.

Branches on the resolved domain user (injected by
:class:`app.middlewares.user_ctx.UserContextMiddleware` into ``data['user']``):

* If the user has ``is_admin=True`` — show the admin main menu so admins land
  straight into management. Mirror of ``/admin``.
* Otherwise — show the user main menu (:func:`app.keyboards.user.user_main_menu`)
  with the "Моя подписка" / "Купить" priority decided by the presence of an
  active subscription.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.db.engine import get_conn
from app.db.repos import subscriptions as subs_repo
from app.db.repos.users import User
from app.keyboards.admin import admin_main_menu
from app.keyboards.user import user_main_menu

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, user: User | None = None) -> None:
    """Greet the user. Admins land in the admin menu, everyone else in the user menu."""
    if user is not None and user.is_admin:
        await message.answer(
            "Админ-меню. Выберите раздел:",
            reply_markup=admin_main_menu(),
        )
        return

    has_sub = False
    if user is not None:
        async with get_conn() as conn:
            existing = await subs_repo.get_active_for_user(conn, user.id)
        has_sub = existing is not None

    await message.answer(
        "Привет! Это бот VPN-подписок. Выберите действие:",
        reply_markup=user_main_menu(has_subscription=has_sub),
    )
