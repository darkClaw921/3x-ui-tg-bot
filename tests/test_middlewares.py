"""Tests for middleware modules."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message, Update
from aiogram.types import User as TgUser

from app.db.repos.users import User
from app.middlewares.admin_only import AdminOnlyMiddleware
from app.middlewares.user_ctx import UserContextMiddleware, _extract_tg_user


def _domain_user(*, is_admin: bool, user_id: int = 1, tg_id: int = 1) -> User:
    return User(
        id=user_id,
        tg_id=tg_id,
        username="u",
        first_name="X",
        is_admin=is_admin,
        created_at="2025",
    )


async def test_admin_only_passes_for_admin_via_user_data():
    mw = AdminOnlyMiddleware()
    handler = AsyncMock(return_value="ok")
    msg = MagicMock(spec=Message)
    data = {"user": _domain_user(is_admin=True)}
    result = await mw(handler, msg, data)
    assert result == "ok"
    handler.assert_awaited()


async def test_admin_only_blocks_non_admin_message():
    mw = AdminOnlyMiddleware()
    handler = AsyncMock()
    msg = MagicMock(spec=Message)
    msg.answer = AsyncMock()
    data = {"user": _domain_user(is_admin=False)}
    result = await mw(handler, msg, data)
    handler.assert_not_awaited()
    msg.answer.assert_awaited_once()
    assert result is None


async def test_admin_only_blocks_non_admin_callback():
    mw = AdminOnlyMiddleware()
    handler = AsyncMock()
    cb = MagicMock(spec=CallbackQuery)
    cb.answer = AsyncMock()
    data = {"user": _domain_user(is_admin=False)}
    await mw(handler, cb, data)
    cb.answer.assert_awaited_once()
    args, kwargs = cb.answer.call_args
    assert kwargs.get("show_alert") is True


async def test_admin_only_fallback_via_from_user(monkey_settings):
    """If 'user' is not in data, fall back to event.from_user.id in ADMIN_IDS."""
    monkey_settings(ADMIN_IDS=[7])
    mw = AdminOnlyMiddleware()
    handler = AsyncMock(return_value="ok")
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock(id=7)
    data = {}
    res = await mw(handler, msg, data)
    assert res == "ok"


async def test_admin_only_no_user_at_all():
    """An event without from_user is rejected silently."""
    mw = AdminOnlyMiddleware()
    handler = AsyncMock()
    obj = MagicMock(spec=Message)
    obj.from_user = None
    obj.answer = AsyncMock()
    data = {}
    res = await mw(handler, obj, data)
    handler.assert_not_awaited()


def test_extract_tg_user_from_message():
    upd = MagicMock(spec=Update)
    # Configure attributes: only message is set, rest None.
    msg = MagicMock()
    msg.from_user = MagicMock(spec=TgUser, id=42, username="u", first_name="X")
    for attr in (
        "message",
        "edited_message",
        "channel_post",
        "edited_channel_post",
        "callback_query",
        "inline_query",
        "chosen_inline_result",
        "shipping_query",
        "pre_checkout_query",
        "poll_answer",
        "my_chat_member",
        "chat_member",
        "chat_join_request",
    ):
        setattr(upd, attr, None)
    upd.message = msg
    out = _extract_tg_user(upd)
    assert out is msg.from_user


def test_extract_tg_user_returns_none_for_empty_update():
    upd = MagicMock(spec=Update)
    for attr in (
        "message",
        "edited_message",
        "channel_post",
        "edited_channel_post",
        "callback_query",
        "inline_query",
        "chosen_inline_result",
        "shipping_query",
        "pre_checkout_query",
        "poll_answer",
        "my_chat_member",
        "chat_member",
        "chat_join_request",
    ):
        setattr(upd, attr, None)
    assert _extract_tg_user(upd) is None


def test_extract_tg_user_fallback_for_direct_message():
    """A test harness may pass a Message directly (no Update wrapper)."""
    msg = MagicMock()
    msg.from_user = "user-obj"
    assert _extract_tg_user(msg) == "user-obj"


async def test_user_ctx_creates_user(file_db):
    """A first-time tg_id triggers a get_or_create insert."""
    mw = UserContextMiddleware()
    handler = AsyncMock(return_value="ok")

    upd = MagicMock(spec=Update)
    upd.message = MagicMock()
    upd.message.from_user = MagicMock(id=123, username="zz", first_name="Z")
    for attr in (
        "edited_message",
        "channel_post",
        "edited_channel_post",
        "callback_query",
        "inline_query",
        "chosen_inline_result",
        "shipping_query",
        "pre_checkout_query",
        "poll_answer",
        "my_chat_member",
        "chat_member",
        "chat_join_request",
    ):
        setattr(upd, attr, None)

    data: dict = {}
    res = await mw(handler, upd, data)
    assert res == "ok"
    assert data["user"] is not None
    assert data["user"].tg_id == 123


async def test_user_ctx_no_from_user(file_db):
    """Update without from_user: data['user']=None and handler still runs."""
    mw = UserContextMiddleware()
    handler = AsyncMock(return_value="ok")
    upd = MagicMock(spec=Update)
    for attr in (
        "message",
        "edited_message",
        "channel_post",
        "edited_channel_post",
        "callback_query",
        "inline_query",
        "chosen_inline_result",
        "shipping_query",
        "pre_checkout_query",
        "poll_answer",
        "my_chat_member",
        "chat_member",
        "chat_join_request",
    ):
        setattr(upd, attr, None)
    data: dict = {}
    res = await mw(handler, upd, data)
    assert res == "ok"
    assert data["user"] is None


async def test_user_ctx_marks_admin(file_db, monkey_settings):
    monkey_settings(ADMIN_IDS=[500])
    mw = UserContextMiddleware()
    handler = AsyncMock(return_value="ok")
    upd = MagicMock(spec=Update)
    upd.message = MagicMock()
    upd.message.from_user = MagicMock(id=500, username="adm", first_name="A")
    for attr in (
        "edited_message",
        "channel_post",
        "edited_channel_post",
        "callback_query",
        "inline_query",
        "chosen_inline_result",
        "shipping_query",
        "pre_checkout_query",
        "poll_answer",
        "my_chat_member",
        "chat_member",
        "chat_join_request",
    ):
        setattr(upd, attr, None)
    data: dict = {}
    await mw(handler, upd, data)
    assert data["user"].is_admin is True
