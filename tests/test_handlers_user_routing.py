"""Routing-coverage test: every button on every user-facing keyboard
MUST have a handler.

Mirror of ``test_handlers_admin_routing.py`` but for the ``user_router``.
Background and motivation are the same: per-handler unit tests catch
logic bugs, but they cannot detect a *missing route* (a button whose
callback nobody registered). When that happens aiogram silently logs
"Update ... is not handled" and the button appears dead in the UI.

This test walks every callback button produced by every factory in
:mod:`app.keyboards.user`, exercising every conditional branch (e.g.
``user_main_menu(has_subscription=True)`` vs ``False``, single- vs
multi-inbound flows, with/without promo on the confirmation card), and
asserts that *some* handler under ``user_router`` accepts the resulting
``callback_data``.

State-bound keyboards are tested under the state they actually appear
in. The inbound-select keyboard is shared by two flows — the buy flow
(:class:`BuyFlow.choosing_inbound`) and the standalone free-days promo
flow (:class:`PromoActivate.choosing_inbound`) — so it gets exercised
once per state.

Only *routing* is exercised: handlers are never invoked, so no Telegram
API calls, DB writes, or 3x-ui requests happen.
"""

from __future__ import annotations

from collections.abc import Iterable

import pytest
from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, User as TgUser

from app.db.repos.plans import Plan
from app.handlers.user import user_router
from app.keyboards.user import (
    back_to_menu_kb,
    cancel_kb,
    confirm_kb,
    inbound_select_kb,
    plans_kb,
    subscription_kb,
    user_main_menu,
)
from app.services.inbounds import InboundOption
from app.states.user import BuyFlow, PromoActivate


# --------------------------------------------------------------------------- #
# Helpers (intentionally a near-copy of the admin variant — we want the two
# routing suites to stay independent, not to share a fragile common base).
# --------------------------------------------------------------------------- #


def _walk(router: Router) -> Iterable[Router]:
    """Yield ``router`` and every router it (recursively) includes."""
    yield router
    for sub in router.sub_routers:
        yield from _walk(sub)


def _all_buttons(kb: InlineKeyboardMarkup) -> list[tuple[str, str]]:
    """Return ``(button_text, callback_data)`` for every callback button.

    URL / switch_inline buttons are skipped — they cannot be "unrouted",
    so they are out of scope for this test.
    """
    out: list[tuple[str, str]] = []
    for row in kb.inline_keyboard:
        for btn in row:
            if btn.callback_data is not None:
                out.append((btn.text, btn.callback_data))
    return out


async def _has_matching_handler(
    router: Router,
    callback_data: str,
    *,
    raw_state: str | None = None,
) -> bool:
    """True iff some handler in ``router`` (recursive) accepts this callback.

    Uses aiogram's :meth:`HandlerObject.check` so the full filter chain
    (CallbackData parsers, magic filters, state filters) runs against
    the synthesised event. ``raw_state`` mirrors what
    :class:`aiogram.fsm.middleware.FSMContextMiddleware` would inject —
    state-gated handlers (inbound pick/back in the buy and promo flows)
    only match when this is set to the appropriate state name.
    """
    cq = CallbackQuery(
        id="t",
        from_user=TgUser(id=1, is_bot=False, first_name="tester"),
        chat_instance="ci",
        data=callback_data,
    )
    for r in _walk(router):
        for handler in r.callback_query.handlers:
            ok, _ = await handler.check(cq, raw_state=raw_state)
            if ok:
                return True
    return False


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _sample_plan(plan_id: int = 7) -> Plan:
    return Plan(
        id=plan_id,
        title="1 месяц",
        days=30,
        price_stars=100,
        traffic_gb=0,
        is_active=True,
        created_at="2026-01-01 00:00:00",
    )


def _sample_inbound_options() -> list[InboundOption]:
    """Two inbounds — enough to exercise every button on the select keyboard."""
    return [
        InboundOption(id=1, remark="Германия", port=443, enabled=True),
        InboundOption(id=2, remark="Нидерланды", port=8443, enabled=True),
    ]


def _all_user_keyboards() -> list[tuple[str, InlineKeyboardMarkup, str | None]]:
    """Every user-facing keyboard variant the bot can render, paired with
    the FSM state each one is shown under (or ``None`` for stateless
    screens).

    Each tuple is ``(pytest_id, keyboard, raw_state)``.
    """
    inbound_opts = _sample_inbound_options()
    return [
        # Top-level menu — both ordering branches (`Купить` first vs
        # `Моя подписка` first) must be fully routable.
        (
            "user_main_menu(no_subscription)",
            user_main_menu(has_subscription=False),
            None,
        ),
        (
            "user_main_menu(has_subscription)",
            user_main_menu(has_subscription=True),
            None,
        ),
        ("back_to_menu_kb", back_to_menu_kb(), None),
        ("cancel_kb", cancel_kb(), None),
        # Plan list. The empty-list case still includes the «◀ В меню»
        # footer button, so it must remain routable.
        ("plans_kb(empty)", plans_kb([]), None),
        ("plans_kb(one_plan)", plans_kb([_sample_plan()]), None),
        # Inbound select — same keyboard shape, but two state contexts:
        # the buy flow (``plan_id``>0, ``promo_id``=0) and the free-days
        # promo flow (``plan_id``=0, ``promo_id``>0). Both are state-
        # gated so we run each under its own state.
        (
            "inbound_select_kb(buy_flow)",
            inbound_select_kb(plan_id=7, options=inbound_opts, promo_id=0),
            BuyFlow.choosing_inbound.state,
        ),
        (
            "inbound_select_kb(promo_flow)",
            inbound_select_kb(plan_id=0, options=inbound_opts, promo_id=5),
            PromoActivate.choosing_inbound.state,
        ),
        # Confirmation card. ``promo_id=0`` shows «Применить промокод»,
        # ``promo_id>0`` hides it — both branches must be routable.
        # ``inbound_id`` is just a payload field but verifying it travels
        # through the route is part of the contract.
        (
            "confirm_kb(no_promo,with_inbound)",
            confirm_kb(plan_id=7, promo_id=0, inbound_id=1),
            None,
        ),
        (
            "confirm_kb(with_promo,with_inbound)",
            confirm_kb(plan_id=7, promo_id=5, inbound_id=1),
            None,
        ),
        # Subscription card.
        ("subscription_kb", subscription_kb(sub_id=42), None),
    ]


# --------------------------------------------------------------------------- #
# Coverage test
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("kb_name", "keyboard", "raw_state"),
    _all_user_keyboards(),
    ids=[name for name, _, _ in _all_user_keyboards()],
)
async def test_every_user_button_is_routed(
    kb_name: str,
    keyboard: InlineKeyboardMarkup,
    raw_state: str | None,
) -> None:
    """Every callback button on every user-facing keyboard must be routable.

    A failure here means a button is dead from the user's perspective:
    tapping it does nothing visible and the bot just logs an unhandled
    update. The fix is almost always either a missing
    ``@router.callback_query(...)`` registration or a state filter that
    is too narrow.
    """
    missing: list[tuple[str, str]] = []
    for text, data in _all_buttons(keyboard):
        if not await _has_matching_handler(user_router, data, raw_state=raw_state):
            missing.append((text, data))

    assert not missing, (
        f"No user handler matches these buttons on keyboard '{kb_name}' "
        f"(raw_state={raw_state!r}): "
        + ", ".join(f"{text!r} -> {data!r}" for text, data in missing)
    )


# --------------------------------------------------------------------------- #
# Pinned regressions for high-value paths
# --------------------------------------------------------------------------- #


async def test_user_main_menu_entry_points_are_routed() -> None:
    """The four entry-points from the user main menu must each reach a
    handler — regression guard for the kind of bug that broke admin
    «Тарифы» / «Промокоды» entry buttons.
    """
    assert await _has_matching_handler(user_router, "ub:open:0:0:0:0"), (
        "BuyCB(action='open') is not routed — «🛒 Купить» would be dead"
    )
    assert await _has_matching_handler(user_router, "u:my"), (
        "UserCB(area='my') is not routed — «📦 Моя подписка» would be dead"
    )
    assert await _has_matching_handler(user_router, "up:open:0:0"), (
        "PromoActCB(action='open') is not routed — "
        "«🎟 Активировать промокод» would be dead"
    )
    assert await _has_matching_handler(user_router, "u:help"), (
        "UserCB(area='help') is not routed — «❓ Помощь» would be dead"
    )


async def test_inbound_select_routes_in_both_flows() -> None:
    """The inbound-select keyboard is shared by the buy flow and the
    free-days promo flow. Its ``pick`` / ``back`` callbacks must route
    *under each state* — a missing state filter on either flow would
    make the keyboard half-dead.
    """
    pick_payload = "inb:pick:7:0:1"
    back_payload = "inb:back:7:0:0"

    # Buy-flow state.
    assert await _has_matching_handler(
        user_router, pick_payload, raw_state=BuyFlow.choosing_inbound.state
    ), "InboundCB(action='pick') not routed under BuyFlow.choosing_inbound"
    assert await _has_matching_handler(
        user_router, back_payload, raw_state=BuyFlow.choosing_inbound.state
    ), "InboundCB(action='back') not routed under BuyFlow.choosing_inbound"

    # Promo-flow state — same callbacks, different state.
    promo_pick = "inb:pick:0:5:1"
    promo_back = "inb:back:0:5:0"
    assert await _has_matching_handler(
        user_router, promo_pick, raw_state=PromoActivate.choosing_inbound.state
    ), "InboundCB(action='pick') not routed under PromoActivate.choosing_inbound"
    assert await _has_matching_handler(
        user_router, promo_back, raw_state=PromoActivate.choosing_inbound.state
    ), "InboundCB(action='back') not routed under PromoActivate.choosing_inbound"


async def test_confirm_kb_threads_inbound_id_through_routing() -> None:
    """The Stars-invoice confirm button carries ``inbound_id`` in the
    payload. Sanity-check that the route still matches when the field
    is non-zero — guards against a future ``F.inbound_id == 0`` filter
    being added by accident.
    """
    assert await _has_matching_handler(user_router, "ub:confirm:7:0:1:0"), (
        "BuyCB(action='confirm', inbound_id=1) is not routed"
    )
    assert await _has_matching_handler(user_router, "ub:apply_promo:7:0:1:0"), (
        "BuyCB(action='apply_promo', inbound_id=1) is not routed"
    )
    # Extend confirm: payload carries non-zero sub_id and must still route.
    assert await _has_matching_handler(user_router, "ub:confirm:7:0:1:42"), (
        "BuyCB(action='confirm', sub_id=42) is not routed"
    )
    # Action-screen entry callbacks must route from any state (no state filter).
    assert await _has_matching_handler(user_router, "ub:extend:0:0:0:42"), (
        "BuyCB(action='extend', sub_id=42) is not routed — extend entry would be dead"
    )
    assert await _has_matching_handler(user_router, "ub:new:0:0:0:0"), (
        "BuyCB(action='new') is not routed — new-sub entry would be dead"
    )
    # Promo-flow action screen — extend/new live under
    # PromoActivate.choosing_action so the route must accept both the
    # callback payload AND the state.
    assert await _has_matching_handler(
        user_router,
        "up:extend:0:42",
        raw_state=PromoActivate.choosing_action.state,
    ), (
        "PromoActCB(action='extend', sub_id=42) is not routed under "
        "PromoActivate.choosing_action — free-days extend would be dead"
    )
    assert await _has_matching_handler(
        user_router,
        "up:new:0:0",
        raw_state=PromoActivate.choosing_action.state,
    ), (
        "PromoActCB(action='new') is not routed under "
        "PromoActivate.choosing_action — free-days new-sub branch would be dead"
    )
