"""FSM state groups for the admin flow (plans + promos + broadcast).

The handlers in :mod:`app.handlers.admin.plans`,
:mod:`app.handlers.admin.promos` and :mod:`app.handlers.admin.broadcast`
drive these state groups with ``MemoryStorage`` (configured in
:mod:`app.main`). State payloads (title, days, price, etc.) are stored via
:meth:`FSMContext.update_data` between transitions.
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class PlanCreate(StatesGroup):
    """Wizard: create a new plan.

    Flow: ``waiting_title`` (text) → ``waiting_days`` (positive int) →
    ``waiting_price`` (non-negative int) → ``waiting_traffic_gb``
    (non-negative int; 0 = unlimited) → ``waiting_inbounds``
    (multi-select via callbacks; empty set = «все доступные») → DB write
    + clear.
    """

    waiting_title = State()
    waiting_days = State()
    waiting_price = State()
    waiting_traffic_gb = State()
    waiting_inbounds = State()


class PlanEdit(StatesGroup):
    """Wizard: edit one field of an existing plan.

    Flow: ``waiting_field`` (callback chooses title/days/price_stars) →
    ``waiting_value`` (text). The chosen field name and target plan id are
    kept in FSM data under ``plan_id`` / ``field``.
    """

    waiting_field = State()
    waiting_value = State()


class AdminSearchUser(StatesGroup):
    """Wizard: find a user by ``tg_id`` or ``@username``.

    Single state — the admin types a digit-only string (interpreted as
    Telegram id) or an ``@handle``/``handle`` (interpreted as username,
    case-insensitive). On hit the handler clears the state and renders
    a user card.
    """

    waiting_query = State()


class PromoCreate(StatesGroup):
    """Wizard: create a new promo code.

    Flow: ``waiting_code`` (text, unique) → ``waiting_type`` (callback:
    percent / flat_stars / free_days) → ``waiting_value`` (int, range
    depends on type) → ``waiting_max_uses`` (int ≥ 0; 0 = unlimited) →
    ``waiting_expires_at`` (``"-"`` / ``"skip"`` for no expiry, otherwise
    ``YYYY-MM-DD``) → DB write + clear.
    """

    waiting_code = State()
    waiting_type = State()
    waiting_value = State()
    waiting_max_uses = State()
    waiting_expires_at = State()


class BroadcastCreate(StatesGroup):
    """Wizard: broadcast a post to every registered user.

    Flow: ``waiting_post`` (the admin sends any message — text, photo,
    video, etc.; its ``chat_id`` + ``message_id`` are stashed in FSM data
    under ``post_chat_id`` / ``post_message_id``) → ``confirming``
    (callback confirms; the stored message is copied to every user via
    :func:`app.services.broadcast.broadcast_message`) → clear.

    The post is never re-parsed or re-rendered — it is delivered verbatim
    with :meth:`aiogram.Bot.copy_message`, so any message type the admin
    can send is supported.
    """

    waiting_post = State()
    confirming = State()


__all__ = [
    "AdminSearchUser",
    "BroadcastCreate",
    "PlanCreate",
    "PlanEdit",
    "PromoCreate",
]
