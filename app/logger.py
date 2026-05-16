"""Loguru-based logging setup.

Importing this module has no side effects. Call :func:`setup_logging` once at
application startup (before creating the bot / dispatcher) to:

* Drop the default loguru sink and install one on ``sys.stderr`` with a
  consistent format (time / level / module / message).
* Route standard-library :mod:`logging` records (used by aiogram, httpx,
  apscheduler and friends) through loguru via :class:`InterceptHandler`.

The desired log level is taken from :data:`app.config.settings.LOG_LEVEL`.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from loguru import logger

from app.config import settings


class InterceptHandler(logging.Handler):
    """Forwards records from the stdlib ``logging`` module to loguru.

    Preserves the original level name when known, falls back to the numeric
    level otherwise. Also walks the frame stack so loguru reports the actual
    caller instead of this handler.
    """

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401 - stdlib signature
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame: Any = logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


def setup_logging(level: str | None = None) -> None:
    """Configure loguru and bridge stdlib logging into it.

    Parameters
    ----------
    level:
        Optional override for the log level. When omitted, uses
        :data:`app.config.settings.LOG_LEVEL`.
    """
    effective_level = (level or settings.LOG_LEVEL).upper()

    logger.remove()
    logger.add(
        sys.stderr,
        level=effective_level,
        format=_LOG_FORMAT,
        backtrace=False,
        diagnose=False,
        enqueue=False,
    )

    # Route stdlib logging through loguru.
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Make popular noisy loggers go through our handler with the same level.
    for noisy in ("aiogram", "aiogram.event", "httpx", "httpcore", "apscheduler"):
        std_logger = logging.getLogger(noisy)
        std_logger.handlers = [InterceptHandler()]
        std_logger.propagate = False
        std_logger.setLevel(effective_level)
