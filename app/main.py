"""Application entry point.

Run with ``python -m app.main``. Builds the aiogram :class:`Bot` and
:class:`Dispatcher`, registers all routers, starts the APScheduler
background jobs (expire-check / reminders / traffic snapshots) and starts
long polling.

Lifecycle:

1. ``setup_logging()`` — loguru sinks.
2. ``init_db()`` — apply ``schema.sql`` + lightweight column migrations.
3. Build :class:`Bot` + :class:`Dispatcher`.
4. ``setup_scheduler(bot).start()`` — three cron jobs.
5. ``dp.start_polling(bot)`` — main loop.
6. On exit: shut the scheduler down, close the xui http client, close
   the bot session.
"""

from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from app.config import settings
from app.db.engine import init_db
from app.handlers import register_routers
from app.logger import setup_logging
from app.scheduler import setup_scheduler
from app.xui import close_xui_client


async def main() -> None:
    """Configure logging, build the bot/dispatcher/scheduler, and start polling."""
    setup_logging()
    logger.info("Starting tg-vpn-bot…")

    await init_db()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    register_routers(dp)

    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("scheduler started")

    try:
        await dp.start_polling(bot)
    finally:
        # ``wait=False``: do not block shutdown if a long job is still running
        # — the process is about to exit anyway and any in-flight DB writes
        # are committed per-statement.
        try:
            scheduler.shutdown(wait=False)
            logger.info("scheduler stopped")
        except Exception as exc:  # noqa: BLE001 — shutdown best-effort
            logger.warning("scheduler shutdown error: {}", exc)

        try:
            await close_xui_client()
        except Exception as exc:  # noqa: BLE001
            logger.warning("xui client close error: {}", exc)

        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        # Graceful shutdown — no traceback on Ctrl+C.
        pass
