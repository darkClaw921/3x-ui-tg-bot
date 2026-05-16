"""User help / how-to-connect router.

A single callback (``UserCB(area='help')``) renders a connection guide
that lists three recommended Xray-compatible clients (one per platform)
and walks the user through the three ways to import a configuration:

1. Paste the ``vless://`` URI.
2. Subscribe via the public subscription URL.
3. Scan the QR code that the bot sends after a successful purchase.

The wording is intentionally concise — Telegram's message size limit
(4096 chars) is not a constraint, but bots that wall-of-text users see
worse engagement than ones that lead with the essentials.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.keyboards.user import UserCB, back_to_menu_kb

router = Router(name="user_help")


_HELP_TEXT = (
    "<b>Как подключиться к VPN</b>\n\n"
    "1️⃣ Установите любой клиент с поддержкой VLESS/Reality:\n"
    "• <b>v2rayNG</b> — Android (Play Market / GitHub)\n"
    "• <b>Streisand</b> — iOS / iPadOS (App Store)\n"
    "• <b>Hiddify</b> — Windows / macOS / Linux\n\n"
    "2️⃣ После оплаты бот пришлёт три варианта ключа — используйте любой:\n"
    "• <code>vless://</code> ссылку — скопируйте, в клиенте нажмите "
    "«Импорт из буфера обмена».\n"
    "• Subscription URL — в клиенте «Добавить подписку», вставьте ссылку, "
    "обновите. Удобно тем, что при продлении ничего перенастраивать не "
    "нужно.\n"
    "• QR-код — в клиенте «Сканировать QR-код» (камера).\n\n"
    "3️⃣ Включите подключение в клиенте — иконка статуса станет зелёной.\n\n"
    "Если что-то не работает — напишите администратору."
)


@router.callback_query(UserCB.filter(F.area == "help"))
async def cb_help(callback: CallbackQuery) -> None:
    """Render the connection guide and offer a "back to menu" button."""
    if callback.message is not None:
        await callback.message.edit_text(
            _HELP_TEXT,
            reply_markup=back_to_menu_kb(),
        )
    await callback.answer()


__all__ = ["router"]
