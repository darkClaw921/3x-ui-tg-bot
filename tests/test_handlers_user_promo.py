"""Tests for :mod:`app.handlers.user.promo` — standalone promo activation
(free-days bonuses with inbound selection).

Flow:

* ``cb_open``             — enter ``PromoActivate.waiting_code``.
* ``msg_code``            — validate code and, for ``free_days``, transition
  to ``PromoActivate.choosing_inbound`` with the inbound multi-option list.
* ``cb_pick_inbound_for_promo`` — activate the free-days promo on the
  selected inbound.
* ``cb_back_inbound_for_promo`` — go back to code entry.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.handlers.user import promo as promo_mod
from app.keyboards.user import InboundCB, PromoActCB
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


# ---------------------------------------------------------------------- #
# cb_open — prompt for code
# ---------------------------------------------------------------------- #


async def test_cb_open(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await promo_mod.cb_open(cb, state)
    cb.message.edit_text.assert_awaited()
    state.set_state.assert_awaited()


# ---------------------------------------------------------------------- #
# msg_code — validate code + route to inbound select for free_days
# ---------------------------------------------------------------------- #


async def test_msg_code_no_user(file_db):
    msg = MagicMock()
    msg.text = "x"
    msg.answer = AsyncMock()
    state = _state()
    await promo_mod.msg_code(msg, state, user=None)
    msg.answer.assert_awaited()


async def test_msg_code_invalid(file_db, make_user):
    """An unknown code stays in waiting_code and re-prompts the user."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)

    msg = MagicMock()
    msg.text = "BAD"
    msg.answer = AsyncMock()
    state = _state()
    await promo_mod.msg_code(msg, state, user=u)
    msg.answer.assert_awaited()
    state.clear.assert_not_awaited()
    # No state advance — user can re-try.
    state.set_state.assert_not_awaited()


async def test_msg_code_discount_type_routed_to_buy(
    file_db, make_user, make_promo
):
    """percent/flat_stars promos are rejected here with a hint to use buy flow."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        await make_promo(conn, code="DISCOUNT", type="percent", value=10)

    msg = MagicMock()
    msg.text = "discount"
    msg.answer = AsyncMock()
    msg.chat = MagicMock(id=1)
    state = _state()
    await promo_mod.msg_code(msg, state, user=u)
    state.clear.assert_awaited()
    msg.answer.assert_awaited()


async def test_msg_code_free_days_routes_to_choosing_inbound(
    file_db, make_user, make_promo, monkeypatch
):
    """A valid free_days code transitions to choosing_inbound with options."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        promo = await make_promo(conn, code="FREE", type="free_days", value=7)

    monkeypatch.setattr(
        promo_mod, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    monkeypatch.setattr(
        promo_mod, "list_user_inbounds",
        AsyncMock(return_value=_stub_inbounds(1, 2)),
    )

    msg = MagicMock()
    msg.text = "free"
    msg.answer = AsyncMock()
    msg.chat = MagicMock(id=42)
    state = _state()
    await promo_mod.msg_code(msg, state, user=u)

    # State was advanced and the inbound options were stashed.
    state.set_state.assert_awaited()
    last_kwargs = state.update_data.await_args.kwargs
    assert last_kwargs["promo_id"] == promo.id
    assert {o["id"] for o in last_kwargs["inbound_options"]} == {1, 2}
    # The user got a message with the inbound selector.
    msg.answer.assert_awaited()


async def test_msg_code_free_days_xui_failure(
    file_db, make_user, make_promo, monkeypatch
):
    """xui failure → user notified, promo NOT redeemed, state cleared."""
    from app.db.engine import get_conn
    from app.db.repos import promos as promos_repo

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        promo = await make_promo(conn, code="FREE", type="free_days", value=7)

    monkeypatch.setattr(
        promo_mod, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    monkeypatch.setattr(
        promo_mod, "list_user_inbounds",
        AsyncMock(side_effect=XuiError("down")),
    )

    msg = MagicMock()
    msg.text = "free"
    msg.answer = AsyncMock()
    msg.chat = MagicMock(id=42)
    state = _state()
    await promo_mod.msg_code(msg, state, user=u)
    state.clear.assert_awaited()
    msg.answer.assert_awaited()
    # Promo's used_count is unchanged.
    async with get_conn() as conn:
        refreshed = await promos_repo.get(conn, promo.id)
    assert refreshed.used_count == 0


async def test_msg_code_free_days_no_inbounds(
    file_db, make_user, make_promo, monkeypatch
):
    """Empty inbound list → user notified, promo not redeemed."""
    from app.db.engine import get_conn
    from app.db.repos import promos as promos_repo

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        promo = await make_promo(conn, code="FREE", type="free_days", value=7)

    monkeypatch.setattr(
        promo_mod, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    monkeypatch.setattr(promo_mod, "list_user_inbounds", AsyncMock(return_value=[]))

    msg = MagicMock()
    msg.text = "free"
    msg.answer = AsyncMock()
    state = _state()
    await promo_mod.msg_code(msg, state, user=u)
    state.clear.assert_awaited()
    async with get_conn() as conn:
        refreshed = await promos_repo.get(conn, promo.id)
    assert refreshed.used_count == 0


async def test_msg_code_double_activation(
    file_db, make_user, make_promo, monkeypatch
):
    """Re-using a free_days promo for the same user is rejected."""
    from app.db.engine import get_conn
    from app.db.repos import promos as promos_repo

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        promo = await make_promo(conn, code="FREE", type="free_days", value=7)
        # Pre-redeem.
        await promos_repo.try_redeem(
            conn, promo_id=promo.id, user_id=u.id, subscription_id=None
        )

    msg = MagicMock()
    msg.text = "free"
    msg.answer = AsyncMock()
    state = _state()
    await promo_mod.msg_code(msg, state, user=u)
    msg.answer.assert_awaited()
    # State stays in waiting_code so the user can try another code.
    state.clear.assert_not_awaited()


# ---------------------------------------------------------------------- #
# cb_pick_inbound_for_promo — activate free-days on selected inbound
# ---------------------------------------------------------------------- #


async def test_cb_pick_inbound_for_promo_activates(
    file_db, make_user, make_promo, mock_bot, monkeypatch
):
    """Selecting an inbound runs activate_free_days with that inbound_id."""
    from app.db.engine import get_conn
    from app.db.repos import promos as promos_repo

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        promo = await make_promo(conn, code="FREE", type="free_days", value=7)

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"id": "u"})
    monkeypatch.setattr(promo_mod, "get_xui_client", AsyncMock(return_value=xui))
    monkeypatch.setattr(promo_mod, "deliver_keys", AsyncMock())

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.chat = MagicMock(id=42)
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state(
        {
            "promo_id": promo.id,
            "inbound_options": [{"id": 1, "remark": "DE", "port": 443, "enabled": True}],
        }
    )
    await promo_mod.cb_pick_inbound_for_promo(
        cb,
        InboundCB(action="pick", promo_id=promo.id, inbound_id=1),
        state,
        mock_bot,
        user=u,
    )
    # Promo was redeemed.
    async with get_conn() as conn:
        refreshed = await promos_repo.get(conn, promo.id)
    assert refreshed.used_count == 1
    # Keys delivered.
    promo_mod.deliver_keys.assert_awaited()


async def test_cb_pick_inbound_for_promo_no_user(file_db, mock_bot):
    cb = MagicMock()
    cb.answer = AsyncMock()
    state = _state()
    await promo_mod.cb_pick_inbound_for_promo(
        cb, InboundCB(action="pick", promo_id=1, inbound_id=1), state, mock_bot,
        user=None,
    )
    cb.answer.assert_awaited()


async def test_cb_pick_inbound_for_promo_missing_promo_id(file_db, make_user, mock_bot):
    """No promo_id in FSM and no fallback → session-expired alert + clear."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)

    cb = MagicMock()
    cb.answer = AsyncMock()
    state = _state({})
    await promo_mod.cb_pick_inbound_for_promo(
        cb, InboundCB(action="pick", promo_id=0, inbound_id=1), state, mock_bot,
        user=u,
    )
    cb.answer.assert_awaited()
    state.clear.assert_awaited()


async def test_cb_pick_inbound_for_promo_inbound_not_in_options(
    file_db, make_user, make_promo, mock_bot, monkeypatch
):
    """An inbound_id not in the FSM-stored options list is rejected."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        promo = await make_promo(conn, code="FREE", type="free_days", value=7)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.answer = AsyncMock()
    state = _state(
        {
            "promo_id": promo.id,
            "inbound_options": [{"id": 1, "remark": "DE", "port": 443, "enabled": True}],
        }
    )
    await promo_mod.cb_pick_inbound_for_promo(
        cb,
        InboundCB(action="pick", promo_id=promo.id, inbound_id=999),
        state,
        mock_bot,
        user=u,
    )
    cb.answer.assert_awaited()
    assert cb.answer.call_args.kwargs.get("show_alert") is True


async def test_cb_pick_inbound_for_promo_promo_invalidated_race(
    file_db, make_user, make_promo, mock_bot, monkeypatch
):
    """If promo becomes invalid between code entry and inbound pick, error."""
    from app.db.engine import get_conn
    from app.db.repos import promos as promos_repo

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        promo = await make_promo(conn, code="FREE", type="free_days", value=7)
        # Deactivate the promo between message and callback.
        await promos_repo.deactivate(conn, promo.id)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state(
        {
            "promo_id": promo.id,
            "inbound_options": [{"id": 1, "remark": "DE", "port": 443, "enabled": True}],
        }
    )
    await promo_mod.cb_pick_inbound_for_promo(
        cb,
        InboundCB(action="pick", promo_id=promo.id, inbound_id=1),
        state,
        mock_bot,
        user=u,
    )
    cb.answer.assert_awaited()
    state.clear.assert_awaited()
    # used_count not incremented since the race aborted activation.
    async with get_conn() as conn:
        refreshed = await promos_repo.get(conn, promo.id)
    assert refreshed.used_count == 0


async def test_cb_pick_inbound_for_promo_xui_failure(
    file_db, make_user, make_promo, mock_bot, monkeypatch
):
    """xui failure during provisioning → promo NOT redeemed, user notified."""
    from app.db.engine import get_conn
    from app.db.repos import promos as promos_repo

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        promo = await make_promo(conn, code="FREE", type="free_days", value=7)

    xui = AsyncMock()
    xui.request_json = AsyncMock(side_effect=XuiError("down"))
    monkeypatch.setattr(promo_mod, "get_xui_client", AsyncMock(return_value=xui))

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.chat = MagicMock(id=42)
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state(
        {
            "promo_id": promo.id,
            "inbound_options": [{"id": 1, "remark": "DE", "port": 443, "enabled": True}],
        }
    )
    await promo_mod.cb_pick_inbound_for_promo(
        cb,
        InboundCB(action="pick", promo_id=promo.id, inbound_id=1),
        state,
        mock_bot,
        user=u,
    )
    # Promo NOT redeemed.
    async with get_conn() as conn:
        refreshed = await promos_repo.get(conn, promo.id)
    assert refreshed.used_count == 0


# ---------------------------------------------------------------------- #
# cb_back_inbound_for_promo — back to code entry
# ---------------------------------------------------------------------- #


async def test_cb_back_inbound_for_promo(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state({"promo_id": 5})
    await promo_mod.cb_back_inbound_for_promo(cb, state)
    state.set_state.assert_awaited()
    last = state.update_data.await_args.kwargs
    assert last["promo_id"] == 0
    assert last["inbound_options"] is None
    cb.message.edit_text.assert_awaited()
