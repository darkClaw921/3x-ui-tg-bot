"""aiogram middlewares used by the bot.

This package houses dispatcher- and router-level middlewares:

* :mod:`app.middlewares.user_ctx` — loads (or creates) the ``users`` row for
  the current Telegram user and exposes it via ``data['user']``. Registered
  as an *outer* middleware on the dispatcher so every update gets a user.
* :mod:`app.middlewares.admin_only` — gates a router behind
  :data:`app.config.settings.ADMIN_IDS`. Attached to the admin router only.
"""

from __future__ import annotations

from app.middlewares.admin_only import AdminOnlyMiddleware
from app.middlewares.user_ctx import UserContextMiddleware

__all__ = ["AdminOnlyMiddleware", "UserContextMiddleware"]
