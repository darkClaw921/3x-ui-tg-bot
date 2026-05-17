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


async def test_promo_msg_code_free_days_no_active_sub_goes_to_inbound_selection(
    file_db, make_user, make_promo, monkeypatch
):
    """No active subs → skip the action screen, go straight to choosing_inbound.

    A valid free_days code transitions to ``PromoActivate.choosing_inbound``
    with the inbound options stashed in the FSM. This is the original
    behaviour preserved after the action-screen rollout for users
    without any active subscription.
    """
    from app.db.engine import get_conn
    from app.states.user import PromoActivate

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

    # State was advanced to choosing_inbound (not choosing_action) and
    # the inbound options were stashed.
    state.set_state.assert_awaited_with(PromoActivate.choosing_inbound)
    last_kwargs = state.update_data.await_args.kwargs
    assert last_kwargs["promo_id"] == promo.id
    assert {o["id"] for o in last_kwargs["inbound_options"]} == {1, 2}
    # The user got a message with the inbound selector.
    msg.answer.assert_awaited()


async def test_promo_msg_code_free_days_shows_action_screen_when_active_sub(
    file_db, make_user, make_promo, make_subscription, monkeypatch
):
    """User has 1+ active subs → render the «продлить vs новая» action screen.

    After validating a ``free_days`` code we load the user's active
    subscriptions; when at least one is found we transition to
    :class:`PromoActivate.choosing_action` and send
    :func:`promo_action_kb` instead of jumping straight to inbound
    selection. The cached inbound options are still stashed so the
    "new sub" branch can re-use them without re-querying the panel.
    """
    from app.db.engine import get_conn
    from app.states.user import PromoActivate

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        promo = await make_promo(conn, code="FREE", type="free_days", value=7)
        await make_subscription(
            conn,
            user_id=u.id,
            xui_inbound_id=1,
            xui_client_email="tg_1_a",
            xui_client_uuid="uuid-a",
            xui_sub_id="sa",
        )

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

    state.set_state.assert_awaited_with(PromoActivate.choosing_action)
    last_kwargs = state.update_data.await_args.kwargs
    assert last_kwargs["promo_id"] == promo.id
    assert {o["id"] for o in last_kwargs["inbound_options"]} == {1, 2}
    msg.answer.assert_awaited()
    # The keyboard sent must be the action-screen keyboard — it carries
    # PromoActCB callbacks (prefix 'up'), not InboundCB (prefix 'inb').
    sent_markup = msg.answer.await_args.kwargs.get("reply_markup")
    assert sent_markup is not None
    all_cb_data = [
        btn.callback_data
        for row in sent_markup.inline_keyboard
        for btn in row
        if btn.callback_data is not None
    ]
    assert any(d.startswith("up:extend") for d in all_cb_data)
    assert any(d.startswith("up:new") for d in all_cb_data)


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
    """Selecting an inbound runs activate_free_days with that inbound_id.

    Also asserts ``extend_sub_id=None`` is passed explicitly — the
    inbound-selection branch is the "create new sub" path of the free-days
    promo flow.
    """
    from app.db.engine import get_conn
    from app.db.repos import promos as promos_repo

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        promo = await make_promo(conn, code="FREE", type="free_days", value=7)

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"id": "u"})
    monkeypatch.setattr(promo_mod, "get_xui_client", AsyncMock(return_value=xui))
    monkeypatch.setattr(promo_mod, "deliver_keys", AsyncMock())
    spy_activate = AsyncMock(wraps=promo_mod.subs_service.activate_free_days)
    monkeypatch.setattr(promo_mod.subs_service, "activate_free_days", spy_activate)

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
    # activate_free_days was called with extend_sub_id=None (new-sub branch).
    spy_activate.assert_awaited_once()
    assert spy_activate.await_args.kwargs.get("extend_sub_id") is None


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


# ---------------------------------------------------------------------- #
# cb_pick_action_extend_promo — extend an existing sub via free_days
# ---------------------------------------------------------------------- #


async def test_cb_pick_action_extend_promo_redeems_specific_sub(
    file_db, make_user, make_promo, make_subscription, mock_bot, monkeypatch
):
    """Extend branch calls activate_free_days with extend_sub_id=N.

    Also verifies the inbound is inherited from the existing
    subscription (not from any FSM-stored options snapshot) and that
    the promo's redemption counter is bumped once activation succeeds.
    """
    from app.db.engine import get_conn
    from app.db.repos import promos as promos_repo

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        promo = await make_promo(conn, code="FREE", type="free_days", value=7)
        sub = await make_subscription(
            conn,
            user_id=u.id,
            xui_inbound_id=5,
            xui_client_email="tg_1_a",
            xui_client_uuid="uuid-a",
            xui_sub_id="sa",
        )

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"id": "u"})
    monkeypatch.setattr(promo_mod, "get_xui_client", AsyncMock(return_value=xui))
    monkeypatch.setattr(promo_mod, "deliver_keys", AsyncMock())
    spy_activate = AsyncMock(wraps=promo_mod.subs_service.activate_free_days)
    monkeypatch.setattr(promo_mod.subs_service, "activate_free_days", spy_activate)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.chat = MagicMock(id=42)
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state({"promo_id": promo.id})
    await promo_mod.cb_pick_action_extend_promo(
        cb,
        PromoActCB(action="extend", sub_id=sub.id),
        state,
        mock_bot,
        user=u,
    )

    spy_activate.assert_awaited_once()
    kwargs = spy_activate.await_args.kwargs
    assert kwargs.get("extend_sub_id") == sub.id
    assert kwargs.get("inbound_id") == 5  # inherited from sub
    # Promo was redeemed.
    async with get_conn() as conn:
        refreshed = await promos_repo.get(conn, promo.id)
    assert refreshed.used_count == 1
    promo_mod.deliver_keys.assert_awaited()


async def test_cb_pick_action_extend_promo_rejects_foreign_sub(
    file_db, make_user, make_promo, make_subscription, mock_bot, monkeypatch
):
    """Caller cannot extend another user's subscription via promo."""
    from app.db.engine import get_conn
    from app.db.repos import promos as promos_repo

    async with get_conn() as conn:
        attacker = await make_user(conn, tg_id=1)
        victim = await make_user(conn, tg_id=2)
        promo = await make_promo(conn, code="FREE", type="free_days", value=7)
        victims_sub = await make_subscription(
            conn,
            user_id=victim.id,
            xui_inbound_id=5,
            xui_client_email="tg_2_v",
            xui_client_uuid="uuid-v",
            xui_sub_id="sv",
        )

    monkeypatch.setattr(promo_mod, "get_xui_client", AsyncMock(return_value=AsyncMock()))
    monkeypatch.setattr(promo_mod, "deliver_keys", AsyncMock())
    spy_activate = AsyncMock(wraps=promo_mod.subs_service.activate_free_days)
    monkeypatch.setattr(promo_mod.subs_service, "activate_free_days", spy_activate)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state({"promo_id": promo.id})
    await promo_mod.cb_pick_action_extend_promo(
        cb,
        PromoActCB(action="extend", sub_id=victims_sub.id),
        state,
        mock_bot,
        user=attacker,
    )

    cb.answer.assert_awaited()
    assert cb.answer.call_args.kwargs.get("show_alert") is True
    spy_activate.assert_not_awaited()
    promo_mod.deliver_keys.assert_not_awaited()
    async with get_conn() as conn:
        refreshed = await promos_repo.get(conn, promo.id)
    assert refreshed.used_count == 0


async def test_cb_pick_action_extend_promo_revalidates_promo(
    file_db, make_user, make_promo, make_subscription, mock_bot, monkeypatch
):
    """Race guard: promo invalidated between msg_code and action-pick.

    The extend handler re-validates the promo right before activation;
    if it has been deactivated (or otherwise made invalid) the FSM is
    cleared, the user gets an alert, and ``activate_free_days`` is
    never called.
    """
    from app.db.engine import get_conn
    from app.db.repos import promos as promos_repo

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        promo = await make_promo(conn, code="FREE", type="free_days", value=7)
        sub = await make_subscription(
            conn,
            user_id=u.id,
            xui_inbound_id=5,
            xui_client_email="tg_1_a",
            xui_client_uuid="uuid-a",
            xui_sub_id="sa",
        )
        await promos_repo.deactivate(conn, promo.id)

    monkeypatch.setattr(promo_mod, "get_xui_client", AsyncMock(return_value=AsyncMock()))
    monkeypatch.setattr(promo_mod, "deliver_keys", AsyncMock())
    spy_activate = AsyncMock(wraps=promo_mod.subs_service.activate_free_days)
    monkeypatch.setattr(promo_mod.subs_service, "activate_free_days", spy_activate)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state({"promo_id": promo.id})
    await promo_mod.cb_pick_action_extend_promo(
        cb,
        PromoActCB(action="extend", sub_id=sub.id),
        state,
        mock_bot,
        user=u,
    )

    cb.answer.assert_awaited()
    state.clear.assert_awaited()
    spy_activate.assert_not_awaited()
    async with get_conn() as conn:
        refreshed = await promos_repo.get(conn, promo.id)
    assert refreshed.used_count == 0


async def test_cb_pick_action_extend_promo_no_user(file_db, mock_bot):
    cb = MagicMock()
    cb.answer = AsyncMock()
    state = _state({"promo_id": 1})
    await promo_mod.cb_pick_action_extend_promo(
        cb,
        PromoActCB(action="extend", sub_id=1),
        state,
        mock_bot,
        user=None,
    )
    cb.answer.assert_awaited()


async def test_cb_pick_action_extend_promo_missing_promo_id(
    file_db, make_user, make_subscription, mock_bot
):
    """Empty FSM (no promo_id) → session-expired alert + clear."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        sub = await make_subscription(
            conn,
            user_id=u.id,
            xui_inbound_id=5,
            xui_client_email="tg_1_a",
            xui_client_uuid="uuid-a",
            xui_sub_id="sa",
        )

    cb = MagicMock()
    cb.answer = AsyncMock()
    state = _state({})
    await promo_mod.cb_pick_action_extend_promo(
        cb,
        PromoActCB(action="extend", sub_id=sub.id),
        state,
        mock_bot,
        user=u,
    )
    cb.answer.assert_awaited()
    state.clear.assert_awaited()


# ---------------------------------------------------------------------- #
# cb_pick_action_new_promo — explicit "new subscription" branch
# ---------------------------------------------------------------------- #


async def test_cb_pick_action_new_promo_goes_to_inbound_selection(
    file_db, make_user, make_promo
):
    """New branch transitions to choosing_inbound and re-uses cached options."""
    from app.db.engine import get_conn
    from app.states.user import PromoActivate

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        promo = await make_promo(conn, code="FREE", type="free_days", value=7)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state(
        {
            "promo_id": promo.id,
            "inbound_options": [
                {"id": 1, "remark": "DE", "port": 443, "enabled": True},
                {"id": 2, "remark": "NL", "port": 444, "enabled": True},
            ],
        }
    )

    await promo_mod.cb_pick_action_new_promo(cb, state, user=u)

    state.set_state.assert_awaited_with(PromoActivate.choosing_inbound)
    cb.message.edit_text.assert_awaited()
    cb.answer.assert_awaited()
    # The keyboard must be the inbound-select keyboard — its callbacks
    # use the InboundCB prefix 'inb'.
    sent_markup = cb.message.edit_text.await_args.kwargs.get("reply_markup")
    assert sent_markup is not None
    all_cb_data = [
        btn.callback_data
        for row in sent_markup.inline_keyboard
        for btn in row
        if btn.callback_data is not None
    ]
    assert any(d.startswith("inb:pick") for d in all_cb_data)


async def test_cb_pick_action_new_promo_refetches_inbounds_when_missing(
    file_db, make_user, make_promo, monkeypatch
):
    """If FSM has no cached options, list_user_inbounds is called."""
    from app.db.engine import get_conn
    from app.states.user import PromoActivate

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        promo = await make_promo(conn, code="FREE", type="free_days", value=7)

    monkeypatch.setattr(
        promo_mod, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    fetcher = AsyncMock(return_value=_stub_inbounds(1, 2))
    monkeypatch.setattr(promo_mod, "list_user_inbounds", fetcher)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state({"promo_id": promo.id})

    await promo_mod.cb_pick_action_new_promo(cb, state, user=u)
    fetcher.assert_awaited()
    state.set_state.assert_awaited_with(PromoActivate.choosing_inbound)


async def test_cb_pick_action_new_promo_missing_promo_id(file_db, make_user):
    """No promo_id in FSM → session-expired alert + clear, no panel call."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)

    cb = MagicMock()
    cb.answer = AsyncMock()
    state = _state({})
    await promo_mod.cb_pick_action_new_promo(cb, state, user=u)
    cb.answer.assert_awaited()
    state.clear.assert_awaited()


async def test_cb_pick_action_new_promo_no_user(file_db):
    cb = MagicMock()
    cb.answer = AsyncMock()
    state = _state({"promo_id": 1})
    await promo_mod.cb_pick_action_new_promo(cb, state, user=None)
    cb.answer.assert_awaited()
