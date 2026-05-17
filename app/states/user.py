"""FSM state groups for the user-facing flow (purchase + promo activation).

The handlers in :mod:`app.handlers.user.buy` and
:mod:`app.handlers.user.promo` drive these state groups with
``MemoryStorage`` (configured in :mod:`app.main`). State payloads (the
chosen ``plan_id``, an applied ``promo_id``) are stored via
:meth:`FSMContext.update_data` between transitions.
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class BuyFlow(StatesGroup):
    """Wizard: buy a subscription via Stars.

    Flow: ``choosing_action`` (optional — only shown when the user
    already has one or more active subscriptions, lets them pick
    "продлить #N" vs "🆕 Новая подписка") → ``choosing_plan`` (callback
    chooses a plan) → ``choosing_inbound`` (callback chooses an
    inbound/server from the plan's allow-list; skipped automatically
    when only one inbound is available **or** when the user is extending
    an existing subscription — the inbound is then inherited from the
    extended sub) → ``confirming`` (user reviews and either pays or
    applies a promo) → ``entering_promo`` (text input of a promo code) →
    back to ``confirming`` with the promo attached.

    The state is cleared once the invoice is sent — the rest of the flow
    (pre_checkout / successful_payment) lives in stateless Telegram updates
    whose payload carries ``plan_id`` / ``promo_id`` / ``inbound_id`` /
    ``sub_id`` (0 for "create new", >0 for "extend sub #N").
    """

    choosing_action = State()
    choosing_plan = State()
    choosing_inbound = State()
    entering_promo = State()
    confirming = State()


class PromoActivate(StatesGroup):
    """Wizard: activate a standalone promo (typically ``free_days``).

    Flow: ``waiting_code`` (text input) → ``choosing_action`` (optional —
    only shown for ``free_days`` codes when the user already has one or
    more active subscriptions, lets them pick «🔄 Продлить #N» vs
    «🆕 Новая подписка») → ``choosing_inbound`` (callback chooses an
    inbound/server for the free-days subscription; skipped automatically
    when only one inbound is available **or** when the user is extending
    an existing subscription — the inbound is then inherited from the
    extended sub) → state cleared once a subscription is provisioned
    (or the user cancels).
    """

    waiting_code = State()
    choosing_action = State()
    choosing_inbound = State()


__all__ = ["BuyFlow", "PromoActivate"]
