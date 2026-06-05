"""Tests for :mod:`app.bot_meta` — cached bot username helper."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app import bot_meta


async def test_get_bot_username_caches_per_bot():
    bot_meta.clear_cache()
    bot = AsyncMock()
    bot.id = 1
    bot.get_me = AsyncMock(return_value=MagicMock(username="mybot"))
    assert await bot_meta.get_bot_username(bot) == "mybot"
    # second call uses cache — no extra get_me.
    assert await bot_meta.get_bot_username(bot) == "mybot"
    assert bot.get_me.await_count == 1


async def test_get_bot_username_distinct_bots():
    bot_meta.clear_cache()
    b1 = AsyncMock()
    b1.id = 1
    b1.get_me = AsyncMock(return_value=MagicMock(username="one"))
    b2 = AsyncMock()
    b2.id = 2
    b2.get_me = AsyncMock(return_value=MagicMock(username="two"))
    assert await bot_meta.get_bot_username(b1) == "one"
    assert await bot_meta.get_bot_username(b2) == "two"


async def test_get_bot_username_empty_when_missing():
    bot_meta.clear_cache()
    bot = AsyncMock()
    bot.id = 9
    bot.get_me = AsyncMock(return_value=MagicMock(username=None))
    assert await bot_meta.get_bot_username(bot) == ""
