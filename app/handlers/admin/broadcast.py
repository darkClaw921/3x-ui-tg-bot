"""Admin broadcast: fan a single post out to every registered user.

The router exposed here lives under the admin parent router (see
:mod:`app.handlers.admin.__init__`) and therefore inherits the
``AdminOnlyMiddleware`` gate — no per-handler ``is_admin`` checks needed.

Flow (:class:`app.states.admin.BroadcastCreate`)
------------------------------------------------

1. ``cb_open`` — ``AdminCB(area='broadcast', action='open')`` from the main
   menu. Enters :attr:`BroadcastCreate.waiting_post` and asks the admin to
   send the post.
2. ``st_post`` — any message in ``waiting_post``. Stashes the post's
   ``chat_id`` + ``message_id`` in FSM data (the message itself is never
   re-parsed — it is copied verbatim later), counts the audience and shows
   a confirmation screen.
3. ``cb_send`` — ``AdminCB(area='broadcast', action='send')`` in
   ``confirming``. Copies the stored post to every user via
   :func:`app.services.broadcast.broadcast_message` and reports the result.

Cancellation at any step is handled by the shared
:func:`app.handlers.admin.menu.cancel_fsm` (the «✖ Отмена» button reuses
``AdminCB(area='main', action='cancel')``).
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db.engine import get_conn
from app.db.repos import users as users_repo
from app.keyboards.admin import (
    AdminCB,
    back_to_main_kb,
    broadcast_confirm_kb,
    cancel_kb,
)
from app.logger import logger
from app.services.broadcast import broadcast_message
from app.states.admin import BroadcastCreate

router = Router(name="admin_broadcast")


_PROMPT = (
    "📣 <b>Рассылка</b>\n\n"
    "Отправьте сообщение, которое нужно разослать всем пользователям. "
    "Это может быть текст, фото, видео или любой другой пост — он будет "
    "доставлен в точности как вы его пришлёте."
)


@router.callback_query(AdminCB.filter((F.area == "broadcast") & (F.action == "open")))
async def cb_open(callback: CallbackQuery, state: FSMContext) -> None:
    """Entry point from the admin main menu — ask for the post to broadcast."""
    await state.set_state(BroadcastCreate.waiting_post)
    if callback.message is not None:
        await callback.message.edit_text(_PROMPT, reply_markup=cancel_kb())
    await callback.answer()


@router.message(BroadcastCreate.waiting_post)
async def st_post(message: Message, state: FSMContext) -> None:
    """Accept the post, count the audience and show the confirmation screen.

    The post message is referenced by ``(chat_id, message_id)`` so it can be
    copied verbatim on confirmation — we never read or reconstruct its
    content here.
    """
    async with get_conn() as conn:
        tg_ids = await users_repo.list_all_tg_ids(conn)

    await state.update_data(
        post_chat_id=message.chat.id,
        post_message_id=message.message_id,
    )
    await state.set_state(BroadcastCreate.confirming)
    await message.answer(
        f"Пост принят. Разослать его <b>{len(tg_ids)}</b> пользовател{_plural(len(tg_ids))}?",
        reply_markup=broadcast_confirm_kb(),
    )


@router.callback_query(
    BroadcastCreate.confirming,
    AdminCB.filter((F.area == "broadcast") & (F.action == "send")),
)
async def cb_send(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    """Copy the stored post to every user and report the result.

    The callback is answered immediately and the confirmation message is
    switched to a «рассылка запущена» note before the (potentially long)
    fan-out loop so the inline spinner never hangs.
    """
    data = await state.get_data()
    post_chat_id = data.get("post_chat_id")
    post_message_id = data.get("post_message_id")
    if post_chat_id is None or post_message_id is None:
        await state.clear()
        await callback.answer("Пост не найден, начните заново.", show_alert=True)
        if callback.message is not None:
            await callback.message.edit_text(
                "Не удалось найти пост для рассылки. Попробуйте снова.",
                reply_markup=back_to_main_kb(),
            )
        return

    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text("⏳ Рассылка запущена…")

    async with get_conn() as conn:
        tg_ids = await users_repo.list_all_tg_ids(conn)

    logger.info("broadcast: starting fan-out to {} users", len(tg_ids))
    result = await broadcast_message(
        bot,
        from_chat_id=int(post_chat_id),
        message_id=int(post_message_id),
        tg_ids=tg_ids,
    )
    await state.clear()

    summary = (
        "✅ <b>Рассылка завершена</b>\n\n"
        f"Получателей: {result.total}\n"
        f"Доставлено: {result.sent}\n"
        f"Заблокировали бота: {result.blocked}\n"
        f"Ошибок: {result.failed}"
    )
    if callback.message is not None:
        await callback.message.edit_text(summary, reply_markup=back_to_main_kb())


def _plural(n: int) -> str:
    """Russian plural ending for «пользовател-» (ю / ям) by count.

    1 пользователю; 2/5/… пользователям. We only need the dative endings
    used in the confirmation prompt.
    """
    return "ю" if n % 10 == 1 and n % 100 != 11 else "ям"


__all__ = ["router"]
