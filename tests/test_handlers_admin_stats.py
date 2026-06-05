"""Tests for :mod:`app.handlers.admin.stats`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.handlers.admin import stats as stats_mod
from app.keyboards.admin import StatsCB


async def test_cb_open_stats(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await stats_mod.cb_open_stats(cb)
    cb.message.edit_text.assert_awaited()


async def test_cb_period_7d(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await stats_mod.cb_period(cb, StatsCB(action="period", field="7d"))
    cb.message.edit_text.assert_awaited()


async def test_cb_period_all(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await stats_mod.cb_period(cb, StatsCB(action="period", field="all"))
    cb.message.edit_text.assert_awaited()


async def test_cb_period_invalid_falls_back(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await stats_mod.cb_period(cb, StatsCB(action="period", field="weird"))
    cb.message.edit_text.assert_awaited()


async def test_cb_refresh(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await stats_mod.cb_refresh(cb, StatsCB(action="refresh", field="30d"))
    cb.answer.assert_awaited_with("Обновлено")


async def test_build_text_with_data(file_db, make_user, make_subscription, make_promo):
    """Smoke test: build_text generates non-empty output when there's data."""
    from datetime import UTC, datetime, timedelta
    from app.db.engine import get_conn

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        await make_subscription(
            conn, user_id=u.id, expires_at=datetime.now(UTC) + timedelta(days=2)
        )
        await make_promo(conn, code="P1")
    text = await stats_mod._build_text("30d")
    assert "Статистика" in text


async def test_build_text_truncation(file_db, make_user, make_subscription, monkeypatch):
    """If body exceeds 4000 chars, output is truncated with a marker."""
    from datetime import UTC, datetime, timedelta
    from app.db.engine import get_conn

    # Force a huge expiring list by lowering the cap and inserting many subs.
    monkeypatch.setattr(stats_mod, "_MAX_EXPIRING_ROWS", 100)

    async with get_conn() as conn:
        u = await make_user(conn, tg_id=1)
        for i in range(200):
            await make_subscription(
                conn,
                user_id=u.id,
                xui_client_uuid=f"u{i}",
                xui_client_email=f"e{i}",
                expires_at=datetime.now(UTC) + timedelta(days=2),
            )
    text = await stats_mod._build_text("30d")
    # truncation marker present
    assert "обрезан" in text


# --------------------------------------------------------------------------- #
# Phase 6 — CSV export handler
# --------------------------------------------------------------------------- #


async def test_cb_export_sends_three_documents(file_db, make_user):
    """The export handler sends one CSV document per dataset + logs an audit row."""
    from app.db.engine import get_conn
    from app.db.repos import audit as audit_repo

    async with get_conn() as conn:
        admin = await make_user(conn, tg_id=1, is_admin=True)

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.chat.id = 4242
    cb.answer = AsyncMock()
    bot = AsyncMock()
    bot.send_document = AsyncMock()

    await stats_mod.cb_export(
        cb,
        StatsCB(action="export", field="all"),
        bot,
        user=admin,
        lang="ru",
    )

    # Three documents: payments, subscriptions, users.
    assert bot.send_document.await_count == 3
    # All went to the admin's chat as BufferedInputFile with .csv filenames.
    from aiogram.types import BufferedInputFile

    for call in bot.send_document.await_args_list:
        assert call.args[0] == 4242
        doc = call.kwargs["document"]
        assert isinstance(doc, BufferedInputFile)
        assert doc.filename.endswith(".csv")
    cb.answer.assert_awaited()

    # One audit entry recorded.
    async with get_conn() as conn:
        entries = await audit_repo.list_recent(conn, limit=10)
    assert any(e.action == "stats.export" for e in entries)


async def test_cb_export_no_message_is_noop(file_db):
    """A callback without a message answers quietly and sends nothing."""
    cb = MagicMock()
    cb.message = None
    cb.answer = AsyncMock()
    bot = AsyncMock()
    bot.send_document = AsyncMock()

    await stats_mod.cb_export(
        cb, StatsCB(action="export", field="all"), bot, user=None, lang="ru"
    )
    bot.send_document.assert_not_awaited()
    cb.answer.assert_awaited()


async def test_cb_export_build_failure_alerts(file_db, monkeypatch):
    """A build error falls back to a failure alert instead of crashing."""
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.chat.id = 7
    cb.answer = AsyncMock()
    bot = AsyncMock()
    bot.send_document = AsyncMock()

    from app.services import exports as exports_service

    async def _boom(_conn):
        raise RuntimeError("disk full")

    monkeypatch.setattr(exports_service, "export_payments_csv", _boom)

    await stats_mod.cb_export(
        cb, StatsCB(action="export", field="all"), bot, user=None, lang="ru"
    )
    bot.send_document.assert_not_awaited()
    cb.answer.assert_awaited()
    # show_alert=True path used for the failure toast.
    assert cb.answer.await_args.kwargs.get("show_alert") is True
