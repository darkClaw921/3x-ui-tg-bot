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


class AdminTicketReply(StatesGroup):
    """Wizard: admin replies to a support ticket.

    Single state — ``writing``: the «✍ Ответить» button on a ticket card enters
    it (stashing ``ticket_id`` in FSM data) and the admin's next text message is
    recorded via :func:`app.services.tickets.reply_admin` (status → 'answered')
    and relayed to the ticket owner. The state is cleared afterwards.
    """

    writing = State()


class AdminGrantSub(StatesGroup):
    """Wizard: manually grant / extend a subscription for a user.

    Flow: ``waiting_plan`` (callback picks a plan from the active list —
    ``PlanCB(action='card', id=<plan_id>)`` reuse) → ``waiting_days`` (text:
    a positive int for a custom term, or ``"-"`` to take the plan's natural
    ``days``) → provision via
    :func:`app.services.subscriptions.grant_subscription` (xui-first) + clear.

    The target ``user_id``, chosen ``plan_id`` and resolved ``inbound_id`` are
    stashed in FSM data between transitions.
    """

    waiting_plan = State()
    waiting_days = State()


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
    "AdminGrantSub",
    "AdminSearchUser",
    "AdminTicketReply",
    "BroadcastCreate",
    "PlanCreate",
    "PlanEdit",
    "PromoCreate",
]
