"""Outer middleware that drops updates from admin-blocked users.

Registered on ``dp.update.outer_middleware`` **before**
:class:`app.middlewares.user_ctx.UserContextMiddleware` so a banned user's
update is rejected before any handler, filter or the user-context lookup runs.

The check is deliberately self-contained: it resolves the originating Telegram
user from the raw :class:`aiogram.types.Update` (reusing
:func:`app.middlewares.user_ctx._extract_tg_user`) and queries
:func:`app.db.repos.users.is_blocked` by ``tg_id`` directly, so it does **not**
depend on ``data['user']`` being populated yet. This keeps the middleware
ordering simple: blocked first, user-context second.

Admins are never blocked — membership is checked against the freshly-read
:data:`app.config.settings.ADMIN_IDS` so a misconfigured ban on an admin id can
never lock an admin out of the bot.

A blocked user gets a short, default-language refusal (a message reply or a
callback alert) and the update is consumed (``handler`` is not invoked). DB
errors are logged and swallowed — on failure the update is allowed through so a
transient DB hiccup never silently bricks the whole bot.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from loguru import logger

from app.config import settings
from app.db.engine import get_conn
from app.db.repos import users as users_repo
from app.i18n import DEFAULT_LANG, t
from app.middlewares.user_ctx import _extract_tg_user


class BlockedUserMiddleware(BaseMiddleware):
    """Reject updates from blocked (banned) users; admins always pass."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = _extract_tg_user(event)
        if tg_user is None:
            # Update without an originating user (poll updates etc.) — pass.
            return await handler(event, data)

        # Admins are never blocked.
        if tg_user.id in set(settings.ADMIN_IDS):
            return await handler(event, data)

        try:
            async with get_conn() as conn:
                blocked = await users_repo.is_blocked(conn, tg_user.id)
        except Exception as exc:  # pragma: no cover — defensive: fail-open
            logger.warning(
                "BlockedUserMiddleware: is_blocked lookup failed for "
                "tg_id={}: {}",
                tg_user.id,
                exc,
            )
            return await handler(event, data)

        if not blocked:
            return await handler(event, data)

        # Refuse and consume the update.
        await self._refuse(event)
        return None

    @staticmethod
    async def _refuse(event: TelegramObject) -> None:
        """Send a short, default-language refusal for the blocked user."""
        refusal = t("blocked.refused", DEFAULT_LANG)
        inner = event
        # The outer middleware receives the raw Update; surface the carried
        # message / callback so we can answer it.
        message = getattr(event, "message", None)
        callback = getattr(event, "callback_query", None)
        if isinstance(callback, CallbackQuery):
            await callback.answer(refusal, show_alert=True)
            return
        if isinstance(message, Message):
            await message.answer(refusal)
            return
        # Defensive: a test harness may pass a Message / CallbackQuery directly.
        if isinstance(inner, CallbackQuery):
            await inner.answer(refusal, show_alert=True)
        elif isinstance(inner, Message):
            await inner.answer(refusal)


__all__ = ["BlockedUserMiddleware"]
