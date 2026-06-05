"""Fan-out a single post to the whole user base (admin broadcast).

The admin sends one message to the bot; this service copies it verbatim to
every registered user via :meth:`aiogram.Bot.copy_message`. ``copy_message``
is used (not ``forward_message`` / re-rendering) because it:

* preserves any content type the admin can send — text, photo, video,
  document, album item, formatting, inline-URL buttons — without the bot
  having to parse or reconstruct it;
* delivers the post as a *native* message (no «Forwarded from» header), so
  to the recipient it looks like a normal channel-style announcement.

Delivery is best-effort and resilient: a user who blocked the bot, deleted
their chat or was deactivated must not abort the run. Errors are bucketed
into ``blocked`` (the user is gone — :class:`TelegramForbiddenError`) and
``failed`` (anything else), and the loop always continues.

Telegram enforces a soft limit of ~30 messages/second to distinct chats.
A small ``throttle`` sleep between sends keeps us under it; explicit
:class:`TelegramRetryAfter` (flood control) is honoured by sleeping for the
server-suggested interval and retrying that single recipient once.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from app.logger import logger


@dataclass(slots=True, frozen=True)
class BroadcastResult:
    """Outcome of a broadcast run.

    * ``total`` — number of recipients attempted.
    * ``sent`` — successfully delivered copies.
    * ``blocked`` — recipients who blocked the bot / are unreachable
      (:class:`TelegramForbiddenError`); expected attrition, not a fault.
    * ``failed`` — any other delivery error (logged individually).

    Invariant: ``sent + blocked + failed == total``.
    """

    total: int
    sent: int
    blocked: int
    failed: int


async def broadcast_message(
    bot: Bot,
    *,
    from_chat_id: int,
    message_id: int,
    tg_ids: Sequence[int],
    throttle: float = 0.05,
) -> BroadcastResult:
    """Copy ``message_id`` from ``from_chat_id`` to every id in ``tg_ids``.

    Args:
        bot: the active :class:`aiogram.Bot`.
        from_chat_id: chat the original post lives in (the admin's private
            chat with the bot).
        message_id: id of the post to copy.
        tg_ids: recipient Telegram ids.
        throttle: seconds to sleep between sends (rate-limit guard). Pass
            ``0`` to disable (used by tests).

    Returns:
        A :class:`BroadcastResult` with per-bucket counters.
    """
    sent = 0
    blocked = 0
    failed = 0

    for tg_id in tg_ids:
        try:
            await bot.copy_message(
                chat_id=tg_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
            )
            sent += 1
        except TelegramForbiddenError:
            # Blocked the bot / deactivated / never started a chat.
            blocked += 1
        except TelegramRetryAfter as exc:
            # Flood control — wait the server-suggested interval and retry
            # this single recipient once before giving up on it.
            logger.warning(
                "broadcast: flood control, sleeping {}s (tg_id={})",
                exc.retry_after,
                tg_id,
            )
            await asyncio.sleep(exc.retry_after)
            try:
                await bot.copy_message(
                    chat_id=tg_id,
                    from_chat_id=from_chat_id,
                    message_id=message_id,
                )
                sent += 1
            except Exception as retry_exc:  # noqa: BLE001 — best-effort
                failed += 1
                logger.warning(
                    "broadcast: retry after flood failed tg_id={}: {}",
                    tg_id,
                    retry_exc,
                )
        except Exception as exc:  # noqa: BLE001 — one bad chat must not abort
            failed += 1
            logger.warning("broadcast: copy_message failed tg_id={}: {}", tg_id, exc)

        if throttle:
            await asyncio.sleep(throttle)

    logger.info(
        "broadcast: done total={} sent={} blocked={} failed={}",
        len(tg_ids),
        sent,
        blocked,
        failed,
    )
    return BroadcastResult(
        total=len(tg_ids),
        sent=sent,
        blocked=blocked,
        failed=failed,
    )


__all__ = ["BroadcastResult", "broadcast_message"]
