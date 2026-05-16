"""Test register_routers in app.handlers and app.handlers.admin/__init__."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.handlers import register_routers


def test_register_routers_attaches_to_dispatcher():
    """register_routers must include the start router and admin/user trees."""
    from aiogram import Dispatcher

    dp = Dispatcher()
    register_routers(dp)
    # If we got here without exceptions, the routers loaded successfully.
    # Sanity check: at least one sub-router is attached.
    assert len(dp.sub_routers) > 0
