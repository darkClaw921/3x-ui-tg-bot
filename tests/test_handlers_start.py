"""Tests for :mod:`app.handlers.start`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.db.repos.users import User
from app.handlers.start import cmd_start


def _user(*, is_admin: bool, user_id: int = 1, tg_id: int = 1) -> User:
    return User(
        id=user_id,
        tg_id=tg_id,
        username="u",
        first_name="X",
        is_admin=is_admin,
        created_at="2025",
    )


async def test_start_admin(file_db):
    msg = MagicMock()
    msg.answer = AsyncMock()
    await cmd_start(msg, user=_user(is_admin=True))
    msg.answer.assert_awaited_once()
    kw = msg.answer.call_args.kwargs
    text = msg.answer.call_args.args[0] if msg.answer.call_args.args else kw.get("text", "")
    assert "Админ" in text


async def test_start_user_no_subscription(file_db, make_user):
    """Standard user without sub → shows main user menu."""
    from app.db.engine import get_conn

    async with get_conn() as conn:
        # Use the factory through the same connection.
        from app.db.repos.users import create

        u = await create(conn, tg_id=10, username="x", first_name="X")

    msg = MagicMock()
    msg.answer = AsyncMock()
    await cmd_start(msg, user=u)
    msg.answer.assert_awaited_once()


async def test_start_user_with_subscription(file_db, make_user, make_subscription):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=5)
        await make_subscription(conn, user_id=u.id)

    msg = MagicMock()
    msg.answer = AsyncMock()
    await cmd_start(msg, user=u)
    msg.answer.assert_awaited_once()


async def test_start_user_is_none(file_db):
    """If user is None (middleware failed), still answer."""
    msg = MagicMock()
    msg.answer = AsyncMock()
    await cmd_start(msg, user=None)
    msg.answer.assert_awaited_once()


# --------------------------------------------------------------------------- #
# Deep-link parsing
# --------------------------------------------------------------------------- #


def _cmd(args: str | None):
    c = MagicMock()
    c.args = args
    return c


async def test_parse_deep_link_classifies():
    from app.handlers.start import _parse_deep_link

    assert _parse_deep_link("ref_123") == ("ref", "123")
    assert _parse_deep_link("gift_ABC") == ("gift", "ABC")
    assert _parse_deep_link("ref_") is None
    assert _parse_deep_link("gift_") is None
    assert _parse_deep_link("garbage") is None
    assert _parse_deep_link(None) is None


async def test_start_ref_deep_link_binds(file_db, make_user):
    """``/start ref_<tg>`` binds the new user to the inviter."""
    from app.db.engine import get_conn
    from app.db.repos import referrals as referrals_repo

    async with get_conn() as conn:
        inviter = await make_user(conn, tg_id=111)
        invitee = await make_user(conn, tg_id=222)

    msg = MagicMock()
    msg.answer = AsyncMock()
    bot = AsyncMock()
    await cmd_start(msg, command=_cmd("ref_111"), bot=bot, user=invitee)

    async with get_conn() as conn:
        r = await referrals_repo.get_by_referred(conn, invitee.id)
    assert r is not None
    assert r.referrer_id == inviter.id
    # Greeting still shown for a ref link.
    msg.answer.assert_awaited()


async def test_start_gift_deep_link_redeems(
    file_db, make_user, make_plan, monkeypatch
):
    """``/start gift_<code>`` redeems the gift, delivers keys, no greeting."""
    from app.db.engine import get_conn
    from app.db.repos import gift_codes as gift_repo
    from app.services import gifts as gifts_service
    import app.handlers.start as start_mod

    async with get_conn() as conn:
        buyer = await make_user(conn, tg_id=1)
        recip = await make_user(conn, tg_id=2)
        plan = await make_plan(conn, days=30, inbound_ids=[5])
        gift = await gifts_service.make_gift_code(
            conn, plan_id=plan.id, inbound_id=5, buyer_id=buyer.id
        )

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"id": "uuid", "email": "e"})
    monkeypatch.setattr(start_mod, "get_xui_client", AsyncMock(return_value=xui))
    monkeypatch.setattr(start_mod, "deliver_keys", AsyncMock())

    msg = MagicMock()
    msg.answer = AsyncMock()
    msg.chat = MagicMock(id=2)
    bot = AsyncMock()
    bot.id = 1
    await cmd_start(msg, command=_cmd(f"gift_{gift.code}"), bot=bot, user=recip)

    # Keys delivered; greeting menu NOT sent (early return).
    start_mod.deliver_keys.assert_awaited_once()
    msg.answer.assert_not_awaited()

    async with get_conn() as conn:
        after = await gift_repo.get_by_code(conn, gift.code)
    assert after.status == "redeemed"


async def test_start_gift_deep_link_not_found_still_greets(
    file_db, make_user, monkeypatch
):
    from app.db.engine import get_conn
    import app.handlers.start as start_mod

    async with get_conn() as conn:
        recip = await make_user(conn, tg_id=2)

    monkeypatch.setattr(
        start_mod, "get_xui_client", AsyncMock(return_value=AsyncMock())
    )
    msg = MagicMock()
    msg.answer = AsyncMock()
    msg.chat = MagicMock(id=2)
    bot = AsyncMock()
    bot.id = 1
    await cmd_start(msg, command=_cmd("gift_GIFT-NONE0000"), bot=bot, user=recip)
    # Error message + greeting menu (no early return for a failed redeem).
    assert msg.answer.await_count >= 1


async def test_start_shows_trial_button_when_enabled(
    file_db, make_user, monkeypatch
):
    from app.db.engine import get_conn
    import app.handlers.start as start_mod

    monkeypatch.setattr(start_mod.settings, "TRIAL_DAYS", 3, raising=False)
    async with get_conn() as conn:
        u = await make_user(conn, tg_id=10)

    msg = MagicMock()
    msg.answer = AsyncMock()
    await cmd_start(msg, user=u)
    kb = msg.answer.call_args.kwargs["reply_markup"]
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert any("Пробный" in s for s in labels)

