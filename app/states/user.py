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


class TrialFlow(StatesGroup):
    """Wizard: activate the free trial subscription.

    Flow: ``choosing_inbound`` (callback chooses an inbound/server for the
    trial client) → state cleared once the trial is provisioned (or the user
    cancels). There is no plan step — the trial's duration / traffic come from
    :data:`app.config.settings.TRIAL_DAYS` / ``TRIAL_TRAFFIC_GB`` — and no
    extend branch (a trial is always a brand-new subscription).
    """

    choosing_inbound = State()


class GiftRedeem(StatesGroup):
    """Wizard: redeem a gift code typed by the recipient.

    Flow: ``waiting_code`` (text input of a ``GIFT-…`` code) → the code is
    validated and redeemed via :func:`app.services.gifts.redeem_gift`, then the
    state is cleared. The deep-link path (``/start gift_<code>``) bypasses this
    FSM entirely — it redeems directly from :func:`app.handlers.start.cmd_start`.
    """

    waiting_code = State()


class SupportFlow(StatesGroup):
    """Wizard: write a support ticket message (create or follow-up).

    Single state — ``writing``: the «❓ Поддержка» button enters it and the
    user's next text message is recorded as a ticket message via
    :func:`app.services.tickets.open_ticket` (which reuses the user's existing
    open ticket or creates a fresh one), the admins are notified, and the state
    is cleared. A user replying to an admin's answer re-enters this same state
    from the support screen.
    """

    writing = State()


__all__ = ["BuyFlow", "GiftRedeem", "PromoActivate", "SupportFlow", "TrialFlow"]
