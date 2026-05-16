"""Tests for :mod:`app.logger`."""

from __future__ import annotations

import logging

import pytest

from app.logger import InterceptHandler, setup_logging


def test_setup_logging_runs_without_error():
    setup_logging("DEBUG")
    # Verify aiogram logger has InterceptHandler installed.
    aiogram_logger = logging.getLogger("aiogram")
    assert any(isinstance(h, InterceptHandler) for h in aiogram_logger.handlers)


def test_setup_logging_default_level():
    setup_logging()  # default to settings.LOG_LEVEL
    # Test should reach this line without error.


def test_intercept_handler_emit_known_level():
    handler = InterceptHandler()
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hello", args=(), exc_info=None,
    )
    # Must not raise.
    handler.emit(record)


def test_intercept_handler_emit_unknown_level():
    """An unknown level name falls back to numeric level."""
    handler = InterceptHandler()
    record = logging.LogRecord(
        name="x", level=42, pathname=__file__, lineno=1,
        msg="weird", args=(), exc_info=None,
    )
    # Force levelname to something loguru doesn't know.
    record.levelname = "BANANA"
    handler.emit(record)
