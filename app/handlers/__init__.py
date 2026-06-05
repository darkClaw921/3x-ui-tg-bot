"""Aggregates and registers all aiogram routers on a :class:`Dispatcher`.

New routers should be imported here and attached inside :func:`register_routers`.

Two dispatcher-level *outer* middlewares are wired here. The
:class:`app.middlewares.blocked.BlockedUserMiddleware` runs first so an
admin-blocked user is dropped before anything else; the
:class:`app.middlewares.user_ctx.UserContextMiddleware` runs second so every
surviving update has ``data['user']`` populated before any handler runs.
"""

from __future__ import annotations

from aiogram import Dispatcher

from app.handlers import start
from app.handlers.admin import admin_router
from app.handlers.user import user_router
from app.middlewares.blocked import BlockedUserMiddleware
from app.middlewares.user_ctx import UserContextMiddleware


def register_routers(dp: Dispatcher) -> None:
    """Attach every handler router (and shared middlewares) to the dispatcher.

    Order:

    1. Outer middleware ``BlockedUserMiddleware`` on ``dp.update`` so an
       admin-blocked user's update is consumed before any handler, filter or
       the user-context lookup runs (admins are never blocked).
    2. Outer middleware ``UserContextMiddleware`` on ``dp.update`` so every
       surviving update — message / callback / inline / pre_checkout / … —
       has the domain user resolved before routing. Registered **after**
       ``BlockedUserMiddleware``; aiogram runs outer middlewares in
       registration order, so the block check fires first.
    3. Routers in handler-resolution order. ``start`` first so ``/start``
       wins regardless of state; ``admin_router`` second (covers ``/admin``
       + every admin callback, gated by ``AdminOnlyMiddleware``);
       ``user_router`` last so it catches every user-flow callback and
       message that did not match the admin gate.
    """
    dp.update.outer_middleware(BlockedUserMiddleware())
    dp.update.outer_middleware(UserContextMiddleware())

    dp.include_router(start.router)
    dp.include_router(admin_router)
    dp.include_router(user_router)


__all__ = ["register_routers"]
