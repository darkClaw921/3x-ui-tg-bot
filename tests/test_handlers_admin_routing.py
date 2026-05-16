"""Routing-coverage test: every button on every admin keyboard MUST have a handler.

Background
----------

Direct unit tests like ``test_handlers_admin_plans.py`` call handler functions
by name. They catch logic bugs inside a handler but cannot detect a missing
route — e.g. the case where the admin main-menu emits
``AdminCB(area="plans", action="open")`` but no handler is registered for it.
In that case the bot silently logs "Update ... is not handled" and the button
appears dead from the user's perspective.

This test walks every callback button produced by the admin-side keyboard
factories in :mod:`app.keyboards.admin`, asks the ``admin_router`` whether
*any* of its (recursively-included) sub-routers has a callback handler whose
filter chain matches that exact ``callback_data`` string, and fails if none
does. It only exercises *routing* — handlers are never invoked, so no
Telegram API calls or DB writes happen.
"""

from __future__ import annotations

from collections.abc import Iterable

import pytest
from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, User as TgUser

from app.db.repos.plans import Plan
from app.db.repos.promos import Promo
from app.handlers.admin import admin_router
from app.keyboards.admin import (
    admin_main_menu,
    cancel_kb,
    plan_card_kb,
    plan_edit_fields_kb,
    plans_list_kb,
    promo_card_kb,
    promo_type_kb,
    promos_list_kb,
    stats_kb,
    user_card_kb,
)
from app.states.admin import PromoCreate


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _walk(router: Router) -> Iterable[Router]:
    """Yield ``router`` and every router it (recursively) includes."""
    yield router
    for sub in router.sub_routers:
        yield from _walk(sub)


def _all_buttons(kb: InlineKeyboardMarkup) -> list[tuple[str, str]]:
    """Return ``(button_text, callback_data)`` for every button on ``kb``.

    Skips URL / switch_inline buttons — only callback buttons can ever
    be ambiguously unrouted.
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

    Uses aiogram's :meth:`HandlerObject.check` which runs the handler's
    filter chain (CallbackData parsers, magic filters, state filters, …)
    against the synthesised event. ``raw_state`` mirrors what
    ``FSMContextMiddleware`` would normally inject — keyboards that only
    appear inside a wizard (e.g. :func:`promo_type_kb`) have handlers
    gated on that state, so the test must supply it explicitly.
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
# Keyboard fixtures: realistic-shape sample plans/promos
# --------------------------------------------------------------------------- #


def _sample_plan(plan_id: int = 7, *, is_active: bool = True) -> Plan:
    return Plan(
        id=plan_id,
        title="1 месяц",
        days=30,
        price_stars=100,
        traffic_gb=0,
        is_active=is_active,
        created_at="2026-01-01 00:00:00",
    )


def _sample_promo(promo_id: int = 3) -> Promo:
    return Promo(
        id=promo_id,
        code="DEMO",
        type="percent",
        value=10,
        max_uses=0,
        used_count=0,
        expires_at=None,
        created_at="2026-01-01 00:00:00",
        created_by=None,
    )


def _all_admin_keyboards() -> list[tuple[str, InlineKeyboardMarkup, str | None]]:
    """Every admin keyboard variant the bot can render, with the FSM state
    each one is shown under (or ``None`` for stateless screens).

    Each tuple is ``(pytest_id, keyboard, raw_state)``.
    """
    return [
        ("admin_main_menu", admin_main_menu(), None),
        ("cancel_kb", cancel_kb(), None),
        # Plans
        ("plans_list_kb(empty)", plans_list_kb([]), None),
        ("plans_list_kb(one_plan)", plans_list_kb([_sample_plan()]), None),
        ("plan_card_kb(active)", plan_card_kb(7, is_active=True), None),
        ("plan_card_kb(inactive)", plan_card_kb(7, is_active=False), None),
        ("plan_edit_fields_kb", plan_edit_fields_kb(7), None),
        # Promos
        ("promos_list_kb(empty)", promos_list_kb([]), None),
        ("promos_list_kb(one_promo)", promos_list_kb([_sample_promo()]), None),
        # The type chooser only appears inside the create-promo wizard, after
        # the user submits a code; its handler is state-gated on
        # PromoCreate.waiting_type.
        ("promo_type_kb", promo_type_kb(), PromoCreate.waiting_type.state),
        ("promo_card_kb(active)", promo_card_kb(3, is_active=True), None),
        ("promo_card_kb(inactive)", promo_card_kb(3, is_active=False), None),
        # Users — exercise every conditional branch
        ("user_card_kb(no_active_sub,user)", user_card_kb(42, active_sub_id=None, is_admin=False), None),
        ("user_card_kb(with_sub,admin)", user_card_kb(42, active_sub_id=99, is_admin=True), None),
        # Stats — try every active_period the UI can pass
        ("stats_kb(7d)", stats_kb(active_period="7d"), None),
        ("stats_kb(30d)", stats_kb(active_period="30d"), None),
        ("stats_kb(all)", stats_kb(active_period="all"), None),
    ]


# --------------------------------------------------------------------------- #
# The actual coverage test
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("kb_name", "keyboard", "raw_state"),
    _all_admin_keyboards(),
    ids=[name for name, _, _ in _all_admin_keyboards()],
)
async def test_every_admin_button_is_routed(
    kb_name: str,
    keyboard: InlineKeyboardMarkup,
    raw_state: str | None,
) -> None:
    """Every callback button on every admin keyboard must be routable.

    Regression: ``AdminCB(area="plans"|"promos", action="open")`` had no
    handler — clicking «📋 Тарифы» / «🎟 Промокоды» from the main admin
    menu silently did nothing. This test would have failed in that state.
    """
    missing: list[tuple[str, str]] = []
    for text, data in _all_buttons(keyboard):
        if not await _has_matching_handler(admin_router, data, raw_state=raw_state):
            missing.append((text, data))

    assert not missing, (
        f"No admin handler matches these buttons on keyboard '{kb_name}' "
        f"(raw_state={raw_state!r}): "
        + ", ".join(f"{text!r} -> {data!r}" for text, data in missing)
    )


async def test_admin_main_menu_specifically_routes_plans_and_promos() -> None:
    """Explicit regression check for the two buttons that were broken.

    Pinned as its own test (not just inside the parametrised suite) so a
    refactor that accidentally drops the «Тарифы» / «Промокоды» entry-
    point handlers gives an obvious, named failure.
    """
    main_menu_buttons = {data for _, data in _all_buttons(admin_main_menu())}
    assert "adm:plans:open" in main_menu_buttons, "expected the plans entry button"
    assert "adm:promos:open" in main_menu_buttons, "expected the promos entry button"

    assert await _has_matching_handler(admin_router, "adm:plans:open"), (
        "AdminCB(area='plans', action='open') is not routed — "
        "regression of the 'admin can't open Тарифы' bug"
    )
    assert await _has_matching_handler(admin_router, "adm:promos:open"), (
        "AdminCB(area='promos', action='open') is not routed — "
        "regression of the 'admin can't open Промокоды' bug"
    )
