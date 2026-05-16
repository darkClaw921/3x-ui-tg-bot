"""User-flow router aggregator.

Builds a single :class:`aiogram.Router` (``user_router``) holding every
user-facing sub-router (menu / help / buy / promo). Unlike the admin
parent router, no gate middleware is attached here — the user flow is
open to every Telegram user.

Usage::

    from app.handlers.user import user_router
    dp.include_router(user_router)
"""

from __future__ import annotations

from aiogram import Router

from app.handlers.user import buy, help as help_module, menu, my_subscription, promo


def _build_user_router() -> Router:
    """Return a fully-wired user router with every sub-router included.

    Resolution order: menu first (so ``/menu`` and main-menu callbacks
    short-circuit before more specific buy / promo flows pick up an
    update), then ``my_subscription`` (owns ``UserCB(area='my')`` plus
    the ``SubCB(action='keys')`` re-delivery), buy (carries the heaviest
    set of FSM-bound handlers plus pre_checkout / successful_payment),
    promo, and finally help (a single callback).
    """
    user_router = Router(name="user")
    user_router.include_router(menu.router)
    user_router.include_router(my_subscription.router)
    user_router.include_router(buy.router)
    user_router.include_router(promo.router)
    user_router.include_router(help_module.router)
    return user_router


user_router: Router = _build_user_router()

__all__ = ["user_router"]
