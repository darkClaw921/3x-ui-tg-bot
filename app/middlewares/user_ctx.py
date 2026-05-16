"""Middleware that loads-or-creates the ``users`` row for every update.

Attached to ``dp.update.outer_middleware`` so it runs **before** every router,
handler and filter. The resolved :class:`app.db.repos.users.User` is exposed
via ``data['user']`` for any handler that wants it.

Why outer middleware? aiogram dispatches updates through routers and filters;
inner middlewares fire only when a handler is actually matched. We want the
user record materialised even if no handler picks the update up — e.g. so
the next /start or /admin can rely on the row existing — and we want a single
place to bridge ``from_user`` to our domain user.

For update types without ``from_user`` (chat_member, channel_post, …) the
middleware simply passes through without touching the DB.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, User as TgUser
from loguru import logger

from app.db.engine import get_conn
from app.db.repos import users as users_repo


def _extract_tg_user(event: TelegramObject) -> TgUser | None:
    """Return the originating ``from_user`` for any update-bearing object.

    Falls through unknown update types (poll updates etc.) by returning
    ``None`` — the middleware will then pass control on without writing.
    """
    # The outer middleware receives the raw ``Update``; inspect every field
    # that can carry a ``from_user`` and return the first that does.
    if isinstance(event, Update):
        for attr in (
            "message",
            "edited_message",
            "channel_post",
            "edited_channel_post",
            "callback_query",
            "inline_query",
            "chosen_inline_result",
            "shipping_query",
            "pre_checkout_query",
            "poll_answer",
            "my_chat_member",
            "chat_member",
            "chat_join_request",
        ):
            value = getattr(event, attr, None)
            if value is not None:
                from_user = getattr(value, "from_user", None)
                if from_user is not None:
                    return from_user
        return None

    # Defensive: some test harnesses pass a Message directly.
    return getattr(event, "from_user", None)


class UserContextMiddleware(BaseMiddleware):
    """Inject the resolved domain ``User`` into handler data.

    On every update:

    1. Find the originating Telegram user (if any).
    2. Open a connection via :func:`app.db.engine.get_conn`.
    3. Call :func:`app.db.repos.users.get_or_create` — idempotent; also
       reconciles ``is_admin`` with ``settings.ADMIN_IDS``.
    4. Place the resulting :class:`app.db.repos.users.User` into
       ``data['user']``.

    Errors at the DB layer are logged and swallowed: the update still
    propagates with ``data['user'] = None`` so handlers can degrade
    gracefully (typically by replying with a generic error message).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = _extract_tg_user(event)
        if tg_user is None:
            data["user"] = None
            return await handler(event, data)

        try:
            async with get_conn() as conn:
                user = await users_repo.get_or_create(
                    conn,
                    tg_id=tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name,
                )
            data["user"] = user
        except Exception as exc:  # pragma: no cover — defensive logging
            logger.exception(f"UserContextMiddleware failed for tg_id={tg_user.id}: {exc}")
            data["user"] = None

        return await handler(event, data)


__all__ = ["UserContextMiddleware"]
