"""Tests for :mod:`app.handlers.user.referral` — the invite screen."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app import bot_meta
from app.handlers.user import referral as referral_handler


def _make_bot(username="thebot"):
    bot = AsyncMock()
    bot.id = 1
    bot.get_me = AsyncMock(return_value=MagicMock(username=username))
    return bot


def test_build_ref_link():
    assert (
        referral_handler._build_ref_link("thebot", 42)
        == "https://t.me/thebot?start=ref_42"
    )


async def test_cb_open_no_user_alerts(file_db):
    cb = MagicMock()
    cb.bot = _make_bot()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await referral_handler.cb_open(cb, user=None, lang="ru")
    cb.message.edit_text.assert_not_awaited()
    assert cb.answer.call_args.kwargs.get("show_alert") is True


async def test_cb_open_shows_link_and_count(file_db, make_user, monkeypatch):
    from app.db.engine import get_conn
    from app.db.repos import referrals as referrals_repo

    bot_meta.clear_cache()
    monkeypatch.setattr(
        referral_handler.settings, "REFERRAL_BONUS_STARS", 50, raising=False
    )
    async with get_conn() as conn:
        inviter = await make_user(conn, tg_id=111)
        a = await make_user(conn, tg_id=2)
        b = await make_user(conn, tg_id=3)
        await referrals_repo.create_pending(
            conn, referrer_id=inviter.id, referred_id=a.id
        )
        await referrals_repo.create_pending(
            conn, referrer_id=inviter.id, referred_id=b.id
        )

    cb = MagicMock()
    cb.bot = _make_bot()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await referral_handler.cb_open(cb, user=inviter, lang="ru")

    text = cb.message.edit_text.call_args.args[0]
    assert "start=ref_111" in text
    assert "2" in text  # count
    assert "50" in text  # bonus advertised


async def test_cb_open_no_bonus_copy(file_db, make_user, monkeypatch):
    from app.db.engine import get_conn

    bot_meta.clear_cache()
    monkeypatch.setattr(
        referral_handler.settings, "REFERRAL_BONUS_STARS", 0, raising=False
    )
    async with get_conn() as conn:
        inviter = await make_user(conn, tg_id=111)

    cb = MagicMock()
    cb.bot = _make_bot()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await referral_handler.cb_open(cb, user=inviter, lang="en")
    text = cb.message.edit_text.call_args.args[0]
    assert "start=ref_111" in text
