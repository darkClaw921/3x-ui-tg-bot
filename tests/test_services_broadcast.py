"""Tests for :mod:`app.services.broadcast`."""

from __future__ import annotations

from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import CopyMessage

from app.services.broadcast import BroadcastResult, broadcast_message


def _forbidden() -> TelegramForbiddenError:
    return TelegramForbiddenError(
        method=CopyMessage(chat_id=0, from_chat_id=0, message_id=0),
        message="bot was blocked by the user",
    )


def _retry_after(seconds: int) -> TelegramRetryAfter:
    return TelegramRetryAfter(
        method=CopyMessage(chat_id=0, from_chat_id=0, message_id=0),
        message="Too Many Requests",
        retry_after=seconds,
    )


async def test_broadcast_all_delivered():
    """Every recipient gets a copy; counters reflect a clean run."""
    bot = AsyncMock()
    bot.copy_message = AsyncMock()
    result = await broadcast_message(
        bot, from_chat_id=1, message_id=2, tg_ids=[10, 20, 30], throttle=0
    )
    assert result == BroadcastResult(total=3, sent=3, blocked=0, failed=0)
    assert bot.copy_message.await_count == 3
    # copy_message is always keyword-only with the stored ref.
    first = bot.copy_message.await_args_list[0]
    assert first.kwargs == {"chat_id": 10, "from_chat_id": 1, "message_id": 2}


async def test_broadcast_buckets_blocked_and_failed():
    """Forbidden → blocked; any other error → failed; loop never aborts."""
    def _copy(*, chat_id, from_chat_id, message_id):
        if chat_id == 20:
            raise _forbidden()
        if chat_id == 30:
            raise ValueError("boom")
        return None

    bot = AsyncMock()
    bot.copy_message = AsyncMock(side_effect=_copy)
    result = await broadcast_message(
        bot, from_chat_id=1, message_id=2, tg_ids=[10, 20, 30, 40], throttle=0
    )
    assert result.total == 4
    assert result.sent == 2  # 10, 40
    assert result.blocked == 1  # 20
    assert result.failed == 1  # 30
    assert result.sent + result.blocked + result.failed == result.total


async def test_broadcast_retry_after_then_success():
    """A flood-control error is honoured and the recipient is retried once."""
    calls = {"n": 0}

    def _copy(*, chat_id, from_chat_id, message_id):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _retry_after(0)  # retry_after=0 → asyncio.sleep(0), instant
        return None

    bot = AsyncMock()
    bot.copy_message = AsyncMock(side_effect=_copy)
    result = await broadcast_message(
        bot, from_chat_id=1, message_id=2, tg_ids=[10], throttle=0
    )
    assert result.sent == 1
    assert result.failed == 0
    assert bot.copy_message.await_count == 2  # original + retry


async def test_broadcast_retry_after_then_fail():
    """If the post-flood retry also fails, the recipient counts as failed."""
    def _copy(*, chat_id, from_chat_id, message_id):
        raise _retry_after(0)

    # First raises RetryAfter; the in-handler retry then raises ValueError.
    seq = [_retry_after(0), ValueError("still bad")]

    def _side(*, chat_id, from_chat_id, message_id):
        raise seq.pop(0)

    bot = AsyncMock()
    bot.copy_message = AsyncMock(side_effect=_side)
    result = await broadcast_message(
        bot, from_chat_id=1, message_id=2, tg_ids=[10], throttle=0
    )
    assert result.sent == 0
    assert result.failed == 1


async def test_broadcast_empty_audience():
    """No recipients → no sends, all-zero result."""
    bot = AsyncMock()
    bot.copy_message = AsyncMock()
    result = await broadcast_message(
        bot, from_chat_id=1, message_id=2, tg_ids=[], throttle=0
    )
    assert result == BroadcastResult(total=0, sent=0, blocked=0, failed=0)
    bot.copy_message.assert_not_awaited()
