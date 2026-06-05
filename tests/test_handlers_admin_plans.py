"""Tests for :mod:`app.handlers.admin.plans`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.handlers.admin import plans as plans_mod
from app.keyboards.admin import PlanCB
from app.services.inbounds import InboundOption
from app.xui import XuiError


def _state(data: dict | None = None):
    s = AsyncMock()
    s.get_data = AsyncMock(return_value=data or {})
    s.update_data = AsyncMock()
    s.set_state = AsyncMock()
    s.clear = AsyncMock()
    return s


def _stub_inbounds(*ids: int) -> list[InboundOption]:
    """Build an `InboundOption` list with the given ids."""
    return [
        InboundOption(id=i, remark=f"srv-{i}", port=443 + i, enabled=True)
        for i in ids
    ]


@pytest.fixture(autouse=True)
def _clear_inbounds_cache():
    from app.services import inbounds as inb

    inb.clear_cache()
    yield
    inb.clear_cache()


async def test_cb_list_empty(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await plans_mod.cb_list(cb, _state())
    cb.message.edit_text.assert_awaited()


async def test_cb_list_with_plans(file_db, make_plan):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        await make_plan(conn)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await plans_mod.cb_list(cb, _state())
    cb.message.edit_text.assert_awaited()


async def test_cb_card_existing(file_db, make_plan):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        plan = await make_plan(conn)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await plans_mod.cb_card(cb, PlanCB(action="card", id=plan.id))
    cb.message.edit_text.assert_awaited()


async def test_cb_card_missing(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await plans_mod.cb_card(cb, PlanCB(action="card", id=999))
    cb.message.edit_text.assert_awaited()


async def test_cb_edit_menu(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await plans_mod.cb_edit_menu(cb, PlanCB(action="edit_menu", id=1))
    cb.message.edit_text.assert_awaited()


async def test_cb_deactivate(file_db, make_plan):
    from app.db.engine import get_conn
    from app.db.repos import plans as plans_repo

    async with get_conn() as conn:
        plan = await make_plan(conn)
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await plans_mod.cb_deactivate(cb, PlanCB(action="deactivate", id=plan.id))
    async with get_conn() as conn:
        fresh = await plans_repo.get(conn, plan.id)
    assert fresh.is_active is False


async def test_cb_create_starts_fsm(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await plans_mod.cb_create(cb, state)
    state.set_state.assert_awaited()


async def test_st_title_empty(file_db):
    msg = MagicMock()
    msg.text = "   "
    msg.answer = AsyncMock()
    state = _state()
    await plans_mod.st_title(msg, state)
    msg.answer.assert_awaited()


async def test_st_title_valid(file_db):
    msg = MagicMock()
    msg.text = "Pro 1mo"
    msg.answer = AsyncMock()
    state = _state()
    await plans_mod.st_title(msg, state)
    state.update_data.assert_awaited()
    state.set_state.assert_awaited()


async def test_st_days_non_integer(file_db):
    msg = MagicMock()
    msg.text = "abc"
    msg.answer = AsyncMock()
    state = _state()
    await plans_mod.st_days(msg, state)
    state.update_data.assert_not_awaited()


async def test_st_days_negative(file_db):
    msg = MagicMock()
    msg.text = "-5"
    msg.answer = AsyncMock()
    state = _state()
    await plans_mod.st_days(msg, state)
    state.update_data.assert_not_awaited()


async def test_st_days_valid(file_db):
    msg = MagicMock()
    msg.text = "30"
    msg.answer = AsyncMock()
    state = _state()
    await plans_mod.st_days(msg, state)
    state.update_data.assert_awaited()
    state.set_state.assert_awaited()


async def test_st_price_moves_to_traffic_gb(file_db):
    """Valid price stores FSM data and transitions to ``waiting_traffic_gb``.

    Plan creation is now deferred to ``st_traffic_gb`` / ``cb_plan_preset``,
    so this step must NOT touch the DB.
    """
    from app.db.engine import get_conn
    from app.db.repos import plans as plans_repo

    msg = MagicMock()
    msg.text = "100"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"title": "T", "days": 30})
    await plans_mod.st_price(msg, state)
    state.update_data.assert_awaited_with(price=100)
    state.set_state.assert_awaited()
    async with get_conn() as conn:
        all_plans = await plans_repo.list_all(conn)
    assert not any(p.title == "T" for p in all_plans)


async def test_st_price_non_integer(file_db):
    msg = MagicMock()
    msg.text = "x"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"title": "T", "days": 30})
    await plans_mod.st_price(msg, state)
    state.clear.assert_not_awaited()
    state.set_state.assert_not_awaited()


async def test_st_price_negative(file_db):
    msg = MagicMock()
    msg.text = "-1"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"title": "T", "days": 30})
    await plans_mod.st_price(msg, state)
    state.clear.assert_not_awaited()
    state.set_state.assert_not_awaited()


async def test_st_traffic_gb_advances_to_inbounds(file_db, monkeypatch):
    """Valid traffic_gb stores the value and enters the inbound multi-select step.

    Plan creation is now deferred to :func:`cb_inbounds_done`, so this step
    must NOT touch the ``plans`` table.
    """
    from app.db.engine import get_conn
    from app.db.repos import plans as plans_repo

    monkeypatch.setattr(
        plans_mod, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    monkeypatch.setattr(
        plans_mod, "list_user_inbounds",
        AsyncMock(return_value=_stub_inbounds(1, 2)),
    )

    msg = MagicMock()
    msg.text = "50"
    msg.answer = AsyncMock()
    state = _state({"title": "T2", "days": 30, "price": 100})
    await plans_mod.st_traffic_gb(msg, state)
    # traffic_gb stored, state transitioned to waiting_inbounds.
    state.set_state.assert_awaited()
    # No plan persisted yet.
    async with get_conn() as conn:
        all_plans = await plans_repo.list_all(conn)
    assert not any(p.title == "T2" for p in all_plans)


async def test_st_traffic_gb_zero_advances_to_inbounds(file_db, monkeypatch):
    """``0`` is a valid input and advances to the inbound step without creating a plan."""
    from app.db.engine import get_conn
    from app.db.repos import plans as plans_repo

    monkeypatch.setattr(
        plans_mod, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    monkeypatch.setattr(
        plans_mod, "list_user_inbounds",
        AsyncMock(return_value=_stub_inbounds(1)),
    )

    msg = MagicMock()
    msg.text = "0"
    msg.answer = AsyncMock()
    state = _state({"title": "Tz", "days": 30, "price": 100})
    await plans_mod.st_traffic_gb(msg, state)
    state.set_state.assert_awaited()
    async with get_conn() as conn:
        all_plans = await plans_repo.list_all(conn)
    assert not any(p.title == "Tz" for p in all_plans)


async def test_st_traffic_gb_non_integer(file_db):
    """Non-integer keeps state intact and re-asks with the preset keyboard."""
    msg = MagicMock()
    msg.text = "abc"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"title": "T", "days": 30, "price": 100})
    await plans_mod.st_traffic_gb(msg, state)
    state.clear.assert_not_awaited()
    msg.answer.assert_awaited()


async def test_st_traffic_gb_negative(file_db):
    """Negative integer is rejected without persisting anything."""
    msg = MagicMock()
    msg.text = "-3"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"title": "T", "days": 30, "price": 100})
    await plans_mod.st_traffic_gb(msg, state)
    state.clear.assert_not_awaited()
    msg.answer.assert_awaited()


# ---------------------------------------------------------------------------
# Preset / manual callbacks for the create wizard
# ---------------------------------------------------------------------------


async def test_cb_plan_preset_days(file_db):
    """Days preset writes ``days`` and transitions to ``waiting_price``."""
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await plans_mod.cb_plan_preset(cb, PlanCB(action="preset", field="days", id=30), state)
    state.update_data.assert_awaited_with(days=30)
    state.set_state.assert_awaited()
    cb.message.edit_text.assert_awaited()


async def test_cb_plan_preset_price(file_db):
    """Price preset writes ``price`` and transitions to ``waiting_traffic_gb``."""
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await plans_mod.cb_plan_preset(cb, PlanCB(action="preset", field="price", id=200), state)
    state.update_data.assert_awaited_with(price=200)
    state.set_state.assert_awaited()
    cb.message.edit_text.assert_awaited()


async def test_cb_plan_preset_gb_advances_to_inbounds(file_db, monkeypatch):
    """GB preset stores traffic_gb and hands off to the inbound multi-select step.

    Plan creation is deferred to :func:`cb_inbounds_done`, so this step
    no longer touches the ``plans`` table.
    """
    from app.db.engine import get_conn
    from app.db.repos import plans as plans_repo

    monkeypatch.setattr(
        plans_mod, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    monkeypatch.setattr(
        plans_mod, "list_user_inbounds",
        AsyncMock(return_value=_stub_inbounds(1, 2)),
    )

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state({"title": "Pg", "days": 30, "price": 100})
    await plans_mod.cb_plan_preset(cb, PlanCB(action="preset", field="gb", id=100), state)
    # No plan persisted yet — that happens after inbound confirmation.
    async with get_conn() as conn:
        all_plans = await plans_repo.list_all(conn)
    assert not any(p.title == "Pg" for p in all_plans)
    # Wizard advanced to waiting_inbounds.
    state.set_state.assert_awaited()


async def test_cb_plan_preset_unknown_field(file_db):
    cb = MagicMock()
    cb.answer = AsyncMock()
    state = _state()
    await plans_mod.cb_plan_preset(cb, PlanCB(action="preset", field="weird", id=1), state)
    cb.answer.assert_awaited_with("Неизвестный шаг", show_alert=True)


async def test_cb_plan_manual_days_keeps_state(file_db):
    """Manual button prompts text input without changing state."""
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await plans_mod.cb_plan_manual(cb, PlanCB(action="manual", field="days"))
    cb.message.edit_text.assert_awaited()


async def test_cb_plan_manual_price_keeps_state(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await plans_mod.cb_plan_manual(cb, PlanCB(action="manual", field="price"))
    cb.message.edit_text.assert_awaited()


async def test_cb_plan_manual_gb_keeps_state(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await plans_mod.cb_plan_manual(cb, PlanCB(action="manual", field="gb"))
    cb.message.edit_text.assert_awaited()


async def test_cb_plan_manual_unknown_field(file_db):
    cb = MagicMock()
    cb.answer = AsyncMock()
    await plans_mod.cb_plan_manual(cb, PlanCB(action="manual", field="weird"))
    cb.answer.assert_awaited_with("Неизвестный шаг", show_alert=True)


async def test_cb_edit_known_field(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await plans_mod.cb_edit(cb, PlanCB(action="edit", id=1, field="title"), state)
    state.set_state.assert_awaited()


async def test_cb_edit_unknown_field(file_db):
    cb = MagicMock()
    cb.answer = AsyncMock()
    state = _state()
    await plans_mod.cb_edit(cb, PlanCB(action="edit", id=1, field="evil"), state)
    cb.answer.assert_awaited_with("Неизвестное поле", show_alert=True)


async def test_st_edit_value_title(file_db, make_plan):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        plan = await make_plan(conn)

    msg = MagicMock()
    msg.text = "new"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"field": "title", "plan_id": plan.id})
    await plans_mod.st_edit_value(msg, state)
    state.clear.assert_awaited()


async def test_st_edit_value_empty_title(file_db, make_plan):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        plan = await make_plan(conn)

    msg = MagicMock()
    msg.text = " "
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"field": "title", "plan_id": plan.id})
    await plans_mod.st_edit_value(msg, state)
    state.clear.assert_not_awaited()


async def test_st_edit_value_bad_int(file_db, make_plan):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        plan = await make_plan(conn)

    msg = MagicMock()
    msg.text = "abc"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"field": "days", "plan_id": plan.id})
    await plans_mod.st_edit_value(msg, state)
    state.clear.assert_not_awaited()


async def test_st_edit_value_days_zero(file_db, make_plan):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        plan = await make_plan(conn)
    msg = MagicMock()
    msg.text = "0"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"field": "days", "plan_id": plan.id})
    await plans_mod.st_edit_value(msg, state)
    state.clear.assert_not_awaited()


async def test_st_edit_value_price_negative(file_db, make_plan):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        plan = await make_plan(conn)
    msg = MagicMock()
    msg.text = "-1"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"field": "price_stars", "plan_id": plan.id})
    await plans_mod.st_edit_value(msg, state)
    state.clear.assert_not_awaited()


async def test_st_edit_value_missing_plan(file_db):
    msg = MagicMock()
    msg.text = "new"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"field": "title", "plan_id": 999})
    await plans_mod.st_edit_value(msg, state)
    state.clear.assert_awaited()


async def test_st_edit_value_price_valid(file_db, make_plan):
    from app.db.engine import get_conn
    from app.db.repos import plans as plans_repo

    async with get_conn() as conn:
        plan = await make_plan(conn)

    msg = MagicMock()
    msg.text = "777"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"field": "price_stars", "plan_id": plan.id})
    await plans_mod.st_edit_value(msg, state)
    async with get_conn() as conn:
        fresh = await plans_repo.get(conn, plan.id)
    assert fresh.price_stars == 777


async def test_cb_edit_traffic_gb_field_is_accepted(file_db):
    """``traffic_gb`` is a known editable field and triggers the prompt."""
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await plans_mod.cb_edit(cb, PlanCB(action="edit", id=1, field="traffic_gb"), state)
    state.set_state.assert_awaited()
    state.update_data.assert_awaited()


async def test_st_edit_value_traffic_gb_valid(file_db, make_plan):
    """Editing traffic_gb to a positive integer persists the new value."""
    from app.db.engine import get_conn
    from app.db.repos import plans as plans_repo

    async with get_conn() as conn:
        plan = await make_plan(conn)

    msg = MagicMock()
    msg.text = "250"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"field": "traffic_gb", "plan_id": plan.id})
    await plans_mod.st_edit_value(msg, state)
    async with get_conn() as conn:
        fresh = await plans_repo.get(conn, plan.id)
    assert fresh.traffic_gb == 250


async def test_st_edit_value_traffic_gb_zero(file_db, make_plan):
    """``0`` is a valid traffic_gb value (means «без лимита»)."""
    from app.db.engine import get_conn
    from app.db.repos import plans as plans_repo

    async with get_conn() as conn:
        plan = await make_plan(conn, traffic_gb=100)

    msg = MagicMock()
    msg.text = "0"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"field": "traffic_gb", "plan_id": plan.id})
    await plans_mod.st_edit_value(msg, state)
    async with get_conn() as conn:
        fresh = await plans_repo.get(conn, plan.id)
    assert fresh.traffic_gb == 0


async def test_st_edit_value_traffic_gb_negative(file_db, make_plan):
    """Negative input keeps state intact."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        plan = await make_plan(conn)
    msg = MagicMock()
    msg.text = "-1"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"field": "traffic_gb", "plan_id": plan.id})
    await plans_mod.st_edit_value(msg, state)
    state.clear.assert_not_awaited()


# ---------------------------------------------------------------------------
# Inbound multi-select wizard step (create mode)
# ---------------------------------------------------------------------------


async def test_enter_inbounds_step_xui_unavailable(file_db, monkeypatch):
    """When the panel is unreachable on entry to the inbounds step, the
    wizard stays put and the user gets an error message."""
    monkeypatch.setattr(
        plans_mod, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    monkeypatch.setattr(
        plans_mod, "list_user_inbounds",
        AsyncMock(side_effect=XuiError("down")),
    )

    msg = MagicMock()
    msg.answer = AsyncMock()
    state = _state()
    await plans_mod._enter_inbounds_step(msg, state)
    state.set_state.assert_not_awaited()
    msg.answer.assert_awaited()


async def test_enter_inbounds_step_empty_inbounds(file_db, monkeypatch):
    """An empty list of panel inbounds aborts the wizard with a hint."""
    monkeypatch.setattr(
        plans_mod, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    monkeypatch.setattr(plans_mod, "list_user_inbounds", AsyncMock(return_value=[]))

    msg = MagicMock()
    msg.answer = AsyncMock()
    state = _state()
    await plans_mod._enter_inbounds_step(msg, state)
    state.set_state.assert_not_awaited()


async def test_cb_toggle_inbound_xor(file_db):
    """Tapping the same row twice toggles selection on then off."""
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.answer = AsyncMock()

    # First tap: id 1 not selected → becomes selected.
    state = _state(
        {
            "selected_inbounds": [],
            "inbound_options": [
                {"id": 1, "remark": "DE", "port": 443, "enabled": True},
                {"id": 2, "remark": "NL", "port": 444, "enabled": True},
            ],
        }
    )
    await plans_mod.cb_toggle_inbound(cb, PlanCB(action="toggle_inbound", id=1), state)
    last = state.update_data.await_args.kwargs
    assert last["selected_inbounds"] == [1]

    # Second tap: id 1 already selected → becomes unselected.
    state2 = _state(
        {
            "selected_inbounds": [1],
            "inbound_options": [
                {"id": 1, "remark": "DE", "port": 443, "enabled": True},
                {"id": 2, "remark": "NL", "port": 444, "enabled": True},
            ],
        }
    )
    await plans_mod.cb_toggle_inbound(cb, PlanCB(action="toggle_inbound", id=1), state2)
    last2 = state2.update_data.await_args.kwargs
    assert last2["selected_inbounds"] == []


async def test_cb_inbounds_done_empty_alert(file_db):
    """`inbounds_done` with no selection shows an alert and stays put."""
    cb = MagicMock()
    cb.answer = AsyncMock()
    state = _state({"selected_inbounds": []})
    await plans_mod.cb_inbounds_done(cb, state)
    cb.answer.assert_awaited()
    assert cb.answer.call_args.kwargs.get("show_alert") is True
    state.clear.assert_not_awaited()


async def test_cb_inbounds_done_creates_plan(file_db):
    """`inbounds_done` (create mode) persists the plan + attaches inbounds."""
    from app.db.engine import get_conn
    from app.db.repos import plans as plans_repo

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state(
        {
            "title": "Created",
            "days": 30,
            "price": 100,
            "traffic_gb": 50,
            "selected_inbounds": [1, 2],
            "inbound_options": [
                {"id": 1, "remark": "DE", "port": 443, "enabled": True},
                {"id": 2, "remark": "NL", "port": 444, "enabled": True},
            ],
        }
    )
    await plans_mod.cb_inbounds_done(cb, state)
    async with get_conn() as conn:
        all_plans = await plans_repo.list_all(conn)
        created = next(p for p in all_plans if p.title == "Created")
        attached = await plans_repo.get_inbounds(conn, created.id)
    assert created.days == 30
    assert created.price_stars == 100
    assert created.traffic_gb == 50
    assert attached == [1, 2]
    state.clear.assert_awaited()


async def test_cb_inbounds_done_edit_mode(file_db, make_plan):
    """`inbounds_done` (edit mode) calls `set_inbounds` on the existing plan."""
    from app.db.engine import get_conn
    from app.db.repos import plans as plans_repo

    async with get_conn() as conn:
        plan = await make_plan(conn, inbound_ids=[1])

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state(
        {
            "editing_plan_id": plan.id,
            "selected_inbounds": [3, 4],
            "inbound_options": [
                {"id": 3, "remark": "x", "port": 1, "enabled": True},
                {"id": 4, "remark": "y", "port": 2, "enabled": True},
            ],
        }
    )
    await plans_mod.cb_inbounds_done(cb, state)
    async with get_conn() as conn:
        attached = await plans_repo.get_inbounds(conn, plan.id)
    assert attached == [3, 4]
    state.clear.assert_awaited()


# ---------------------------------------------------------------------------
# Edit field='inbounds' — load current set into multi-select
# ---------------------------------------------------------------------------


async def test_cb_edit_inbounds_preloads_current(file_db, make_plan, monkeypatch):
    """Opening the inbounds editor pre-selects the plan's current set."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        plan = await make_plan(conn, inbound_ids=[2, 5])

    monkeypatch.setattr(
        plans_mod, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    monkeypatch.setattr(
        plans_mod, "list_user_inbounds",
        AsyncMock(return_value=_stub_inbounds(1, 2, 3, 5)),
    )

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await plans_mod.cb_edit_inbounds(
        cb, PlanCB(action="edit", id=plan.id, field="inbounds"), state
    )
    state.set_state.assert_awaited()
    last = state.update_data.await_args.kwargs
    assert last["editing_plan_id"] == plan.id
    # selected_inbounds is the plan's current set.
    assert sorted(last["selected_inbounds"]) == [2, 5]


async def test_cb_edit_inbounds_unknown_plan(file_db, monkeypatch):
    """Editing inbounds for a missing plan returns an alert."""
    cb = MagicMock()
    cb.answer = AsyncMock()
    state = _state()
    await plans_mod.cb_edit_inbounds(
        cb, PlanCB(action="edit", id=99999, field="inbounds"), state
    )
    cb.answer.assert_awaited()
    assert cb.answer.call_args.kwargs.get("show_alert") is True


async def test_cb_edit_inbounds_xui_unavailable(file_db, make_plan, monkeypatch):
    """Panel error during edit-inbounds aborts with an alert, no state change."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        plan = await make_plan(conn)

    monkeypatch.setattr(
        plans_mod, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    monkeypatch.setattr(
        plans_mod, "list_user_inbounds",
        AsyncMock(side_effect=XuiError("down")),
    )

    cb = MagicMock()
    cb.message = MagicMock()
    cb.answer = AsyncMock()
    state = _state()
    await plans_mod.cb_edit_inbounds(
        cb, PlanCB(action="edit", id=plan.id, field="inbounds"), state
    )
    cb.answer.assert_awaited()
    assert cb.answer.call_args.kwargs.get("show_alert") is True
    state.set_state.assert_not_awaited()


async def test_cb_edit_inbounds_empty_panel(file_db, make_plan, monkeypatch):
    """An empty panel inbound list aborts with an alert."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        plan = await make_plan(conn)

    monkeypatch.setattr(
        plans_mod, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    monkeypatch.setattr(plans_mod, "list_user_inbounds", AsyncMock(return_value=[]))

    cb = MagicMock()
    cb.message = MagicMock()
    cb.answer = AsyncMock()
    state = _state()
    await plans_mod.cb_edit_inbounds(
        cb, PlanCB(action="edit", id=plan.id, field="inbounds"), state
    )
    cb.answer.assert_awaited()


# ---------------------------------------------------------------------------
# Card rendering — _format_plan inbounds line
# ---------------------------------------------------------------------------


def test_format_plan_with_remarks():
    """Card body includes the «Подключения» line with resolved remarks."""
    from app.db.repos.plans import Plan

    plan = Plan(id=1, title="T", days=30, price_stars=100, traffic_gb=0,
                is_active=True, created_at="2025")
    text = plans_mod._format_plan(plan, {1: "DE", 2: "NL"})
    assert "Подключения" in text
    assert "DE" in text
    assert "NL" in text


def test_format_plan_with_missing_remark():
    """An inbound id present on the plan but missing from the panel response is
    rendered as ``id=NN (удалён)``."""
    from app.db.repos.plans import Plan

    plan = Plan(id=1, title="T", days=30, price_stars=100, traffic_gb=0,
                is_active=True, created_at="2025")
    text = plans_mod._format_plan(plan, {7: ""})
    assert "id=7" in text
    assert "удалён" in text


def test_format_plan_no_inbound_remarks_arg():
    """No remarks arg → the «Подключения» line is omitted entirely."""
    from app.db.repos.plans import Plan

    plan = Plan(id=1, title="T", days=30, price_stars=100, traffic_gb=0,
                is_active=True, created_at="2025")
    text = plans_mod._format_plan(plan, None)
    assert "Подключения" not in text


def test_format_plan_empty_remarks_dict():
    """An empty remarks dict still renders the «не настроены» hint."""
    from app.db.repos.plans import Plan

    plan = Plan(id=1, title="T", days=30, price_stars=100, traffic_gb=0,
                is_active=True, created_at="2025")
    text = plans_mod._format_plan(plan, {})
    assert "не настроены" in text
