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

from app.i18n import DEFAULT_LANG, t
from app.keyboards.user import UserCB, back_to_menu_kb

router = Router(name="user_help")


@router.callback_query(UserCB.filter(F.area == "help"))
async def cb_help(callback: CallbackQuery, lang: str = DEFAULT_LANG) -> None:
    """Render the connection guide and offer a "back to menu" button.

    The guide text is localized via :func:`app.i18n.t` (``help.text``); the
    ``lang`` keyword is injected by :class:`app.middlewares.user_ctx`.
    """
    if callback.message is not None:
        await callback.message.edit_text(
            t("help.text", lang),
            reply_markup=back_to_menu_kb(),
        )
    await callback.answer()


__all__ = ["router"]
