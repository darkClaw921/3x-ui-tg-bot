"""Admin router aggregator.

Builds a single :class:`aiogram.Router` (``admin_router``) that holds every
admin-flow sub-router (menu / plans / promos / users / stats) and is
gated by :class:`app.middlewares.admin_only.AdminOnlyMiddleware`. The
middleware is applied on the parent router's ``message`` and
``callback_query`` observers, so it propagates to every nested
router/handler — non-admins can never reach plan, promo, users or
stats handlers.

Usage::

    from app.handlers.admin import admin_router
    dp.include_router(admin_router)
"""

from __future__ import annotations

from aiogram import Router

from app.handlers.admin import menu, plans, promos, stats, users
from app.middlewares.admin_only import AdminOnlyMiddleware


def _build_admin_router() -> Router:
    """Return a fully-wired admin router with the gate middleware attached."""
    admin_router = Router(name="admin")
    admin_router.message.middleware(AdminOnlyMiddleware())
    admin_router.callback_query.middleware(AdminOnlyMiddleware())
    admin_router.include_router(menu.router)
    admin_router.include_router(plans.router)
    admin_router.include_router(promos.router)
    admin_router.include_router(users.router)
    admin_router.include_router(stats.router)
    return admin_router


admin_router: Router = _build_admin_router()

__all__ = ["admin_router"]
