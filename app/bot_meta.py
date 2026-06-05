"""Cached bot identity helpers.

Several growth features build ``https://t.me/<bot_username>?start=…`` deep-links
(referral invites, gift activation links) and therefore need the bot's
``@username``. :meth:`aiogram.Bot.get_me` is a network round-trip whose result
never changes during a process lifetime, so this module fetches it once and
caches it module-side.

The cache is keyed by the bot's numeric id (``Bot.id``) so a test harness that
swaps in a different mock bot does not get a stale username from a previous one.
"""

from __future__ import annotations

from aiogram import Bot

# Maps Bot.id -> resolved @username. Populated lazily on the first
# :func:`get_bot_username` call per bot.
_username_cache: dict[int, str] = {}


async def get_bot_username(bot: Bot) -> str:
    """Return the bot's ``@username`` (without the ``@``), cached per bot id.

    Calls :meth:`aiogram.Bot.get_me` once and memoises the username keyed by
    ``bot.id``. Subsequent calls for the same bot return the cached value with
    no network call. Falls back to an empty string if the API surprisingly
    returns no username (so callers building a link degrade to a malformed but
    non-crashing URL rather than raising).
    """
    bot_id = getattr(bot, "id", None)
    if bot_id is not None and bot_id in _username_cache:
        return _username_cache[bot_id]

    me = await bot.get_me()
    username = me.username or ""
    if bot_id is not None:
        _username_cache[bot_id] = username
    return username


def clear_cache() -> None:
    """Drop the cached usernames (exposed for tests)."""
    _username_cache.clear()


__all__ = ["clear_cache", "get_bot_username"]
