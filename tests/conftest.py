"""Shared pytest fixtures for the 3x-ui-tg-bot tests.

The bot's :mod:`app.config` instantiates the :class:`Settings` singleton at
module-import time, so we need to ensure required env vars are set *before*
the very first ``import app.*`` happens. This file is loaded by pytest
before any test module, so we do it here at the top of the module.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

# --- Configure environment BEFORE any app.* import ------------------------ #
os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "1,2")
os.environ.setdefault("XUI_BASE_URL", "http://xui.test")
os.environ.setdefault("XUI_USERNAME", "admin")
os.environ.setdefault("XUI_PASSWORD", "pwd")
os.environ.setdefault("XUI_INBOUND_ID", "1")
os.environ.setdefault("XUI_SERVER_HOST", "vpn.test")
os.environ.setdefault("XUI_SUB_BASE_URL", "https://sub.test/sub")
os.environ.setdefault("XUI_VERIFY_SSL", "false")
os.environ.setdefault("DB_PATH", ":memory:")
os.environ.setdefault("LOG_LEVEL", "DEBUG")

import aiosqlite  # noqa: E402
import pytest  # noqa: E402


# Path to schema.sql relative to this file.
_SCHEMA_PATH = Path(__file__).parent.parent / "app" / "db" / "schema.sql"


# ------------------------------------------------------------------------- #
# Settings patcher
# ------------------------------------------------------------------------- #


@pytest.fixture
def monkey_settings(monkeypatch: pytest.MonkeyPatch):
    """Yield a callable that patches `app.config.settings` attributes."""
    from app.config import settings

    def patch(**kwargs: Any) -> None:
        for k, v in kwargs.items():
            monkeypatch.setattr(settings, k, v, raising=False)

    return patch


# ------------------------------------------------------------------------- #
# DB fixtures
# ------------------------------------------------------------------------- #


@pytest.fixture
def tmp_db_path(tmp_path):
    """Return a path to a temporary, file-backed SQLite database."""
    return tmp_path / "test.db"


async def _build_schema(conn: aiosqlite.Connection) -> None:
    """Apply schema.sql + migrations to a connection (idempotent)."""
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON;")
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")
    await conn.executescript(schema)
    # Apply lightweight in-engine migrations too (so we exercise the same
    # code paths the live bot uses).
    from app.db.engine import _apply_migrations

    await _apply_migrations(conn)
    await conn.commit()


@pytest.fixture
async def db_conn():
    """Yield a fresh in-memory aiosqlite connection with the bot's schema."""
    conn = await aiosqlite.connect(":memory:")
    try:
        await _build_schema(conn)
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def file_db(tmp_db_path, monkeypatch):
    """Yield a file-backed DB path + monkeypatch settings.DB_PATH to it.

    Some scheduler / handler tests need to call ``get_conn()`` which reads
    settings.DB_PATH — using a file ensures every fresh connection talks to
    the same database.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "DB_PATH", str(tmp_db_path), raising=False)

    # Initialise schema.
    async with aiosqlite.connect(tmp_db_path) as conn:
        await _build_schema(conn)
    return tmp_db_path


# ------------------------------------------------------------------------- #
# Factories
# ------------------------------------------------------------------------- #


@pytest.fixture
def make_user():
    """Factory: insert a user row and return the :class:`User` dataclass."""
    from app.db.repos.users import create as users_create

    async def _make(
        conn: aiosqlite.Connection,
        *,
        tg_id: int = 100,
        username: str | None = "tester",
        first_name: str | None = "Tester",
        is_admin: bool = False,
    ):
        return await users_create(
            conn,
            tg_id=tg_id,
            username=username,
            first_name=first_name,
            is_admin=is_admin,
        )

    return _make


@pytest.fixture
def make_plan():
    """Factory: create a plan row, with at least one attached inbound.

    Mirrors the production behaviour where every active plan has at least
    one inbound (enforced by the migration backfill in
    :func:`app.db.engine._apply_migrations`). Pass ``inbound_ids=None`` to
    fall back to ``[settings.XUI_INBOUND_ID]``; pass an explicit list to
    attach a custom set (use ``[]`` to skip attachment entirely, which is
    only useful for negative-path tests).
    """
    from app.config import settings
    from app.db.repos.plans import create as plans_create
    from app.db.repos.plans import set_inbounds

    async def _make(
        conn: aiosqlite.Connection,
        *,
        title: str = "1 месяц",
        days: int = 30,
        price_stars: int = 100,
        traffic_gb: int = 0,
        inbound_ids: list[int] | None = None,
    ):
        plan = await plans_create(
            conn,
            title=title,
            days=days,
            price_stars=price_stars,
            traffic_gb=traffic_gb,
        )
        if inbound_ids is None:
            inbound_ids = [int(settings.XUI_INBOUND_ID)]
        if inbound_ids:
            await set_inbounds(conn, plan.id, inbound_ids)
        return plan

    return _make


@pytest.fixture
def make_promo():
    """Factory: create a promo row."""
    from app.db.repos.promos import create as promos_create

    async def _make(
        conn: aiosqlite.Connection,
        *,
        code: str = "PROMO1",
        type: str = "percent",
        value: int = 10,
        max_uses: int = 0,
        expires_at: str | None = None,
        created_by: int | None = None,
    ):
        return await promos_create(
            conn,
            code=code,
            type=type,  # type: ignore[arg-type]
            value=value,
            max_uses=max_uses,
            expires_at=expires_at,
            created_by=created_by,
        )

    return _make


@pytest.fixture
def make_subscription():
    """Factory: create a subscription row."""
    from app.db.repos.subscriptions import create as subs_create

    async def _make(
        conn: aiosqlite.Connection,
        *,
        user_id: int,
        xui_inbound_id: int = 1,
        xui_client_uuid: str = "uuid-1",
        xui_client_email: str = "tg_100_aaa",
        xui_sub_id: str = "subid1",
        expires_at: datetime | str | None = None,
        plan_id: int | None = None,
    ):
        if expires_at is None:
            expires_at = datetime.now(UTC) + timedelta(days=30)
        return await subs_create(
            conn,
            user_id=user_id,
            xui_inbound_id=xui_inbound_id,
            xui_client_uuid=xui_client_uuid,
            xui_client_email=xui_client_email,
            xui_sub_id=xui_sub_id,
            expires_at=expires_at,
            plan_id=plan_id,
        )

    return _make


# ------------------------------------------------------------------------- #
# Telegram / XUI mocks
# ------------------------------------------------------------------------- #


@pytest.fixture
def mock_bot():
    """Return an AsyncMock standing in for :class:`aiogram.Bot`."""
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    bot.send_photo = AsyncMock(return_value=MagicMock(message_id=2))
    bot.send_invoice = AsyncMock(return_value=MagicMock(message_id=3))
    bot.answer_pre_checkout_query = AsyncMock(return_value=True)
    return bot


@pytest.fixture
def mock_xui_client():
    """Return an AsyncMock with the XuiClient surface used by the codebase."""
    client = AsyncMock()
    client.request_json = AsyncMock(return_value=None)
    client.request = AsyncMock()
    client.login = AsyncMock()
    client.close = AsyncMock()
    return client
