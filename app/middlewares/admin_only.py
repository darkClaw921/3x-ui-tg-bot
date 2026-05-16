"""Gate router middleware: only :data:`settings.ADMIN_IDS` may proceed.

Attached to the admin router (``admin_router.message.middleware`` and
``admin_router.callback_query.middleware``) so every admin-flow handler is
implicitly protected. Non-admin updates receive a short refusal reply and
``handler`` is **not** invoked — the update is consumed.

Membership is checked against ``event.from_user.id`` and the freshly-read
``settings.ADMIN_IDS`` so editing the env-file (and reloading the bot) takes
effect without code changes. We also accept a ``user`` injected by
:class:`app.middlewares.user_ctx.UserContextMiddleware` and prefer its
``is_admin`` flag when present — that flag is reconciled with
``ADMIN_IDS`` on every update.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config import settings
from app.db.repos.users import User


_ACCESS_DENIED = "Доступ запрещён."


class AdminOnlyMiddleware(BaseMiddleware):
    """Reject non-admin updates with a polite message and stop propagation."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if self._is_admin(event, data):
            return await handler(event, data)

        # Refuse and consume the update.
        if isinstance(event, Message):
            await event.answer(_ACCESS_DENIED)
        elif isinstance(event, CallbackQuery):
            await event.answer(_ACCESS_DENIED, show_alert=True)
        return None

    @staticmethod
    def _is_admin(event: TelegramObject, data: dict[str, Any]) -> bool:
        """Return ``True`` iff the originating Telegram user is an admin.

        Preference order:

        1. ``data['user']`` (a :class:`User`) — already reconciled with
           ``settings.ADMIN_IDS`` by :class:`UserContextMiddleware`.
        2. Raw ``event.from_user.id`` ∈ ``settings.ADMIN_IDS`` as a fallback
           if the user-context middleware is not active (e.g. in tests).
        """
        user = data.get("user")
        if isinstance(user, User):
            return user.is_admin

        from_user = getattr(event, "from_user", None)
        if from_user is None:
            return False
        return from_user.id in set(settings.ADMIN_IDS)


__all__ = ["AdminOnlyMiddleware"]
