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


async def test_st_price_creates_plan(file_db):
    from app.db.engine import get_conn
    from app.db.repos import plans as plans_repo

    msg = MagicMock()
    msg.text = "100"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"title": "T", "days": 30})
    await plans_mod.st_price(msg, state)
    async with get_conn() as conn:
        all_plans = await plans_repo.list_all(conn)
    assert any(p.title == "T" and p.days == 30 and p.price_stars == 100 for p in all_plans)


async def test_st_price_non_integer(file_db):
    msg = MagicMock()
    msg.text = "x"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"title": "T", "days": 30})
    await plans_mod.st_price(msg, state)
    state.clear.assert_not_awaited()


async def test_st_price_negative(file_db):
    msg = MagicMock()
    msg.text = "-1"
    msg.answer = AsyncMock()
    state = _state()
    state.get_data = AsyncMock(return_value={"title": "T", "days": 30})
    await plans_mod.st_price(msg, state)
    state.clear.assert_not_awaited()


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
