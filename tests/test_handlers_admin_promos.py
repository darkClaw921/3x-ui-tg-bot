"""Tests for :mod:`app.handlers.admin.promos`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.handlers.admin import promos as promos_mod
from app.keyboards.admin import PromoCB


def _state(data=None):
    s = AsyncMock()
    s.get_data = AsyncMock(return_value=data or {})
    s.update_data = AsyncMock()
    s.set_state = AsyncMock()
    s.clear = AsyncMock()
    return s


def test_parse_expires_at_skip():
    out = promos_mod._parse_expires_at("-")
    assert out is None
    out = promos_mod._parse_expires_at("skip")
    assert out is None
    out = promos_mod._parse_expires_at("нет")
    assert out is None


def test_parse_expires_at_invalid():
    assert promos_mod._parse_expires_at("not-a-date") is False


def test_parse_expires_at_valid():
    out = promos_mod._parse_expires_at("2099-01-15")
    assert isinstance(out, str)
    assert "2099-01-15" in out


def test_promo_is_active():
    from app.db.repos.promos import Promo

    no_exp = Promo(
        id=1, code="X", type="percent", value=10, max_uses=0, used_count=0,
        expires_at=None, created_at="2025", created_by=None,
    )
    assert promos_mod._promo_is_active(no_exp) is True


def test_promo_is_active_past_expires():
    from app.db.repos.promos import Promo

    p = Promo(
        id=1, code="X", type="percent", value=10, max_uses=0, used_count=0,
        expires_at="2000-01-01 00:00:00", created_at="2025", created_by=None,
    )
    assert promos_mod._promo_is_active(p) is False


async def test_cb_list(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await promos_mod.cb_list(cb, _state())
    cb.message.edit_text.assert_awaited()


async def test_cb_card_existing(file_db, make_promo):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        p = await make_promo(conn, code="X")

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await promos_mod.cb_card(cb, PromoCB(action="card", id=p.id))
    cb.message.edit_text.assert_awaited()


async def test_cb_card_missing(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await promos_mod.cb_card(cb, PromoCB(action="card", id=999))
    cb.message.edit_text.assert_awaited()


async def test_cb_deactivate(file_db, make_promo):
    from app.db.engine import get_conn
    from app.db.repos import promos as promos_repo

    async with get_conn() as conn:
        p = await make_promo(conn, code="X")

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await promos_mod.cb_deactivate(cb, PromoCB(action="deactivate", id=p.id))
    async with get_conn() as conn:
        fresh = await promos_repo.get(conn, p.id)
    assert fresh.expires_at is not None


async def test_cb_redemptions_empty(file_db, make_promo):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        p = await make_promo(conn, code="X")

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await promos_mod.cb_redemptions(cb, PromoCB(action="redemptions", id=p.id))
    cb.message.edit_text.assert_awaited()


async def test_cb_redemptions_with_history(file_db, make_user, make_promo):
    from app.db.engine import get_conn
    from app.db.repos import promos as promos_repo

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        p = await make_promo(conn, code="X")
        await promos_repo.try_redeem(
            conn, promo_id=p.id, user_id=u.id, subscription_id=None
        )

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await promos_mod.cb_redemptions(cb, PromoCB(action="redemptions", id=p.id))
    cb.message.edit_text.assert_awaited()


async def test_cb_create_starts_fsm(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await promos_mod.cb_create(cb, state)
    state.set_state.assert_awaited()


async def test_st_code_empty(file_db):
    msg = MagicMock()
    msg.text = " "
    msg.answer = AsyncMock()
    state = _state()
    await promos_mod.st_code(msg, state)
    state.update_data.assert_not_awaited()


async def test_st_code_with_space(file_db):
    msg = MagicMock()
    msg.text = "BAD CODE"
    msg.answer = AsyncMock()
    state = _state()
    await promos_mod.st_code(msg, state)
    state.update_data.assert_not_awaited()


async def test_st_code_collision(file_db, make_promo):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        await make_promo(conn, code="DUP")

    msg = MagicMock()
    msg.text = "DUP"
    msg.answer = AsyncMock()
    state = _state()
    await promos_mod.st_code(msg, state)
    state.update_data.assert_not_awaited()


async def test_st_code_ok(file_db):
    msg = MagicMock()
    msg.text = "NEW"
    msg.answer = AsyncMock()
    state = _state()
    await promos_mod.st_code(msg, state)
    state.update_data.assert_awaited()
    state.set_state.assert_awaited()


async def test_cb_type_known(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = _state()
    await promos_mod.cb_type(cb, PromoCB(action="type", field="percent"), state)
    state.update_data.assert_awaited()


async def test_cb_type_unknown(file_db):
    cb = MagicMock()
    cb.answer = AsyncMock()
    state = _state()
    await promos_mod.cb_type(cb, PromoCB(action="type", field="weird"), state)
    cb.answer.assert_awaited_with("Неизвестный тип", show_alert=True)


async def test_st_value_non_integer(file_db):
    msg = MagicMock()
    msg.text = "x"
    msg.answer = AsyncMock()
    state = _state({"type": "percent"})
    await promos_mod.st_value(msg, state)
    state.update_data.assert_not_awaited()


async def test_st_value_percent_out_of_range(file_db):
    msg = MagicMock()
    msg.text = "150"
    msg.answer = AsyncMock()
    state = _state({"type": "percent"})
    await promos_mod.st_value(msg, state)
    state.update_data.assert_not_awaited()


async def test_st_value_flat_stars_zero(file_db):
    msg = MagicMock()
    msg.text = "0"
    msg.answer = AsyncMock()
    state = _state({"type": "flat_stars"})
    await promos_mod.st_value(msg, state)
    state.update_data.assert_not_awaited()


async def test_st_value_ok(file_db):
    msg = MagicMock()
    msg.text = "10"
    msg.answer = AsyncMock()
    state = _state({"type": "percent"})
    await promos_mod.st_value(msg, state)
    state.update_data.assert_awaited()


async def test_st_max_uses_non_integer(file_db):
    msg = MagicMock()
    msg.text = "x"
    msg.answer = AsyncMock()
    state = _state()
    await promos_mod.st_max_uses(msg, state)
    state.update_data.assert_not_awaited()


async def test_st_max_uses_negative(file_db):
    msg = MagicMock()
    msg.text = "-1"
    msg.answer = AsyncMock()
    state = _state()
    await promos_mod.st_max_uses(msg, state)
    state.update_data.assert_not_awaited()


async def test_st_max_uses_zero_unlimited(file_db):
    msg = MagicMock()
    msg.text = "0"
    msg.answer = AsyncMock()
    state = _state()
    await promos_mod.st_max_uses(msg, state)
    state.update_data.assert_awaited()


async def test_st_expires_at_bad_input(file_db, make_user):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)

    msg = MagicMock()
    msg.text = "not-a-date"
    msg.answer = AsyncMock()
    state = _state({"code": "C", "type": "percent", "value": 10, "max_uses": 0})
    await promos_mod.st_expires_at(msg, state, user=u)
    state.clear.assert_not_awaited()


async def test_st_expires_at_skip(file_db, make_user):
    from app.db.engine import get_conn
    from app.db.repos import promos as promos_repo

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)

    msg = MagicMock()
    msg.text = "-"
    msg.answer = AsyncMock()
    state = _state({"code": "FREE1", "type": "free_days", "value": 7, "max_uses": 0})
    await promos_mod.st_expires_at(msg, state, user=u)
    state.clear.assert_awaited()
    async with get_conn() as conn:
        promo = await promos_repo.get_by_code(conn, "FREE1")
    assert promo is not None
    assert promo.expires_at is None


async def test_st_expires_at_with_date(file_db, make_user):
    from app.db.engine import get_conn
    from app.db.repos import promos as promos_repo

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)

    msg = MagicMock()
    msg.text = "2099-01-15"
    msg.answer = AsyncMock()
    state = _state({"code": "C99", "type": "percent", "value": 10, "max_uses": 5})
    await promos_mod.st_expires_at(msg, state, user=u)
    state.clear.assert_awaited()
    async with get_conn() as conn:
        promo = await promos_repo.get_by_code(conn, "C99")
    assert promo is not None
    assert promo.expires_at and "2099-01-15" in promo.expires_at


async def test_st_expires_at_integrity_error(file_db, make_user, make_promo):
    """If a concurrent write produces a duplicate code, the handler clears state."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        await make_promo(conn, code="DUP2")

    msg = MagicMock()
    msg.text = "-"
    msg.answer = AsyncMock()
    state = _state({"code": "DUP2", "type": "percent", "value": 10, "max_uses": 0})
    await promos_mod.st_expires_at(msg, state, user=u)
    state.clear.assert_awaited()


# ---------------------------------------------------------------------------
# Preset / manual callbacks for the create wizard
# ---------------------------------------------------------------------------


async def test_cb_promo_preset_value_percent(file_db):
    """Value preset (percent type) writes ``value`` and moves to max_uses."""
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    state = _state({"type": "percent"})
    await promos_mod.cb_promo_preset(
        cb, PromoCB(action="preset", field="value", id=10), state
    )
    state.update_data.assert_awaited_with(value=10)
    state.set_state.assert_awaited()
    cb.message.answer.assert_awaited()


async def test_cb_promo_preset_value_flat_stars(file_db):
    """Value preset (flat_stars type) writes ``value`` regardless of type."""
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    state = _state({"type": "flat_stars"})
    await promos_mod.cb_promo_preset(
        cb, PromoCB(action="preset", field="value", id=100), state
    )
    state.update_data.assert_awaited_with(value=100)
    state.set_state.assert_awaited()


async def test_cb_promo_preset_value_free_days(file_db):
    """Value preset (free_days type) writes ``value`` regardless of type."""
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    state = _state({"type": "free_days"})
    await promos_mod.cb_promo_preset(
        cb, PromoCB(action="preset", field="value", id=7), state
    )
    state.update_data.assert_awaited_with(value=7)
    state.set_state.assert_awaited()


async def test_cb_promo_preset_max_uses_zero_unlimited(file_db):
    """max_uses preset id=0 writes 0 (unlimited) and moves to expires."""
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    state = _state({"type": "percent", "value": 10})
    await promos_mod.cb_promo_preset(
        cb, PromoCB(action="preset", field="max_uses", id=0), state
    )
    state.update_data.assert_awaited_with(max_uses=0)
    state.set_state.assert_awaited()


async def test_cb_promo_preset_max_uses_finite(file_db):
    """max_uses preset id>0 writes the value and moves to expires."""
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    state = _state({"type": "percent", "value": 10})
    await promos_mod.cb_promo_preset(
        cb, PromoCB(action="preset", field="max_uses", id=50), state
    )
    state.update_data.assert_awaited_with(max_uses=50)
    state.set_state.assert_awaited()


async def test_cb_promo_preset_expires_zero_creates_with_none(file_db, make_user):
    """expires preset id=0 → expires_at=None and promo is created."""
    from app.db.engine import get_conn
    from app.db.repos import promos as promos_repo

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    state = _state(
        {"code": "PE0", "type": "percent", "value": 10, "max_uses": 0}
    )
    await promos_mod.cb_promo_preset(
        cb, PromoCB(action="preset", field="expires", id=0), state, user=u
    )
    state.clear.assert_awaited()
    async with get_conn() as conn:
        promo = await promos_repo.get_by_code(conn, "PE0")
    assert promo is not None
    assert promo.expires_at is None


async def test_cb_promo_preset_expires_30days_iso(file_db, make_user):
    """expires preset id=30 → ISO string ~ now+30 days."""
    from datetime import UTC, datetime, timedelta

    from app.db.engine import get_conn
    from app.db.repos import promos as promos_repo

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    state = _state(
        {"code": "PE30", "type": "percent", "value": 10, "max_uses": 5}
    )
    before = datetime.now(UTC)
    await promos_mod.cb_promo_preset(
        cb, PromoCB(action="preset", field="expires", id=30), state, user=u
    )
    after = datetime.now(UTC)
    state.clear.assert_awaited()
    async with get_conn() as conn:
        promo = await promos_repo.get_by_code(conn, "PE30")
    assert promo is not None
    assert promo.expires_at is not None
    # Parse the stored ISO string (format: "YYYY-MM-DD HH:MM:SS+00:00")
    stored = datetime.fromisoformat(promo.expires_at)
    expected_lo = (before + timedelta(days=30)).replace(
        hour=23, minute=59, second=59, microsecond=0
    )
    expected_hi = (after + timedelta(days=30)).replace(
        hour=23, minute=59, second=59, microsecond=0
    )
    # Allow a small drift window in case the seconds wrap during execution.
    assert (expected_lo - timedelta(seconds=2)) <= stored <= (
        expected_hi + timedelta(seconds=2)
    )


async def test_cb_promo_preset_unknown_field(file_db):
    cb = MagicMock()
    cb.answer = AsyncMock()
    state = _state()
    await promos_mod.cb_promo_preset(
        cb, PromoCB(action="preset", field="weird", id=1), state
    )
    cb.answer.assert_awaited_with("Неизвестный шаг", show_alert=True)


async def test_cb_promo_manual_value(file_db):
    """Manual button prompts text input without touching state."""
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    await promos_mod.cb_promo_manual(cb, PromoCB(action="manual", field="value"))
    cb.message.answer.assert_awaited()


async def test_cb_promo_manual_max_uses(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    await promos_mod.cb_promo_manual(cb, PromoCB(action="manual", field="max_uses"))
    cb.message.answer.assert_awaited()


async def test_cb_promo_manual_expires(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    await promos_mod.cb_promo_manual(cb, PromoCB(action="manual", field="expires"))
    cb.message.answer.assert_awaited()


async def test_cb_promo_manual_unknown_field(file_db):
    cb = MagicMock()
    cb.answer = AsyncMock()
    await promos_mod.cb_promo_manual(cb, PromoCB(action="manual", field="weird"))
    cb.answer.assert_awaited_with("Неизвестный шаг", show_alert=True)


def test_expires_days_to_iso_zero_is_none():
    """``_expires_days_to_iso(0)`` returns ``None`` (бессрочно)."""
    assert promos_mod._expires_days_to_iso(0) is None


def test_expires_days_to_iso_positive_returns_iso():
    """``_expires_days_to_iso(N)`` returns ISO string anchored at 23:59:59 UTC."""
    out = promos_mod._expires_days_to_iso(7)
    assert isinstance(out, str)
    # Same separator/format as ``_parse_expires_at``: "YYYY-MM-DD HH:MM:SS+00:00".
    from datetime import datetime as _dt

    parsed = _dt.fromisoformat(out)
    assert (parsed.hour, parsed.minute, parsed.second) == (23, 59, 59)
