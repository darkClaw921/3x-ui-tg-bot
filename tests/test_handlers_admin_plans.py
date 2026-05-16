"""Tests for :mod:`app.handlers.admin.plans`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.handlers.admin import plans as plans_mod
from app.keyboards.admin import PlanCB


def _state():
    s = AsyncMock()
    s.get_data = AsyncMock(return_value={})
    s.update_data = AsyncMock()
    s.set_state = AsyncMock()
    s.clear = AsyncMock()
    return s


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


async def test_st_traffic_gb_creates_plan(file_db):
    """Valid traffic_gb completes the wizard and persists the plan."""
    from app.db.engine import get_conn
    from app.db.repos import plans as plans_repo

    msg = MagicMock()
    msg.text = "50"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"title": "T2", "days": 30, "price": 100})
    await plans_mod.st_traffic_gb(msg, state)
    async with get_conn() as conn:
        all_plans = await plans_repo.list_all(conn)
    assert any(
        p.title == "T2" and p.days == 30 and p.price_stars == 100 and p.traffic_gb == 50
        for p in all_plans
    )
    state.clear.assert_awaited()


async def test_st_traffic_gb_zero_means_unlimited(file_db):
    """``0`` is a valid input and stores as ``traffic_gb=0`` (unlimited)."""
    from app.db.engine import get_conn
    from app.db.repos import plans as plans_repo

    msg = MagicMock()
    msg.text = "0"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"title": "Tz", "days": 30, "price": 100})
    await plans_mod.st_traffic_gb(msg, state)
    async with get_conn() as conn:
        all_plans = await plans_repo.list_all(conn)
    assert any(p.title == "Tz" and p.traffic_gb == 0 for p in all_plans)


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
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await plans_mod.cb_plan_preset(cb, PlanCB(action="preset", field="days", id=30), state)
    state.update_data.assert_awaited_with(days=30)
    state.set_state.assert_awaited()
    cb.message.answer.assert_awaited()


async def test_cb_plan_preset_price(file_db):
    """Price preset writes ``price`` and transitions to ``waiting_traffic_gb``."""
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await plans_mod.cb_plan_preset(cb, PlanCB(action="preset", field="price", id=200), state)
    state.update_data.assert_awaited_with(price=200)
    state.set_state.assert_awaited()
    cb.message.answer.assert_awaited()


async def test_cb_plan_preset_gb_creates_plan(file_db):
    """GB preset is the terminal step — it persists the plan."""
    from app.db.engine import get_conn
    from app.db.repos import plans as plans_repo

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"title": "Pg", "days": 30, "price": 100})
    await plans_mod.cb_plan_preset(cb, PlanCB(action="preset", field="gb", id=100), state)
    state.clear.assert_awaited()
    async with get_conn() as conn:
        all_plans = await plans_repo.list_all(conn)
    assert any(p.title == "Pg" and p.traffic_gb == 100 for p in all_plans)


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
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    await plans_mod.cb_plan_manual(cb, PlanCB(action="manual", field="days"))
    cb.message.answer.assert_awaited()


async def test_cb_plan_manual_price_keeps_state(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    await plans_mod.cb_plan_manual(cb, PlanCB(action="manual", field="price"))
    cb.message.answer.assert_awaited()


async def test_cb_plan_manual_gb_keeps_state(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    await plans_mod.cb_plan_manual(cb, PlanCB(action="manual", field="gb"))
    cb.message.answer.assert_awaited()


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
