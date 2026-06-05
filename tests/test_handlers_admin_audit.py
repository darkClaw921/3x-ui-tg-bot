"""Tests for :mod:`app.handlers.admin.audit`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.db.repos.audit import AuditEntry
from app.handlers.admin import audit as audit_mod
from app.keyboards.admin import AuditCB


def _entry(**kw):
    base = dict(
        id=1, admin_id=None, action="plan.create", target_type="plan",
        target_id=5, details=None, created_at="2025-01-01 00:00:00",
    )
    base.update(kw)
    return AuditEntry(**base)


def test_target_suffix():
    assert audit_mod._target_suffix(_entry()) == " → plan#5"
    assert audit_mod._target_suffix(
        _entry(target_type=None, target_id=None)
    ) == ""
    assert audit_mod._target_suffix(
        _entry(target_type="broadcast", target_id=None)
    ) == " → broadcast"


def test_details_suffix():
    assert audit_mod._details_suffix(_entry(details=None)) == ""
    out = audit_mod._details_suffix(_entry(details='{"a":1}'))
    assert "{&quot;a&quot;:1}" in out or "{" in out


async def test_admin_label_none():
    assert await audit_mod._admin_label(None) == "—"


async def test_admin_label_resolves(file_db):
    from app.db.engine import get_conn
    from app.db.repos import users as users_repo

    async with get_conn() as conn:
        admin = await users_repo.create(
            conn, tg_id=1, username="boss", first_name="B", is_admin=True
        )
    label = await audit_mod._admin_label(admin.id)
    assert label == "@boss"


async def _seed_audit(file_db, n):
    from app.db.engine import get_conn
    from app.db.repos import users as users_repo
    from app.services import audit as audit_service

    async with get_conn() as conn:
        admin = await users_repo.create(
            conn, tg_id=1, username="boss", first_name="B", is_admin=True
        )
        for i in range(n):
            await audit_service.log_action(
                conn, admin.id, "plan.create", "plan", i + 1, {"i": i}
            )
    return admin


async def test_cb_open_renders_first_page(file_db):
    await _seed_audit(file_db, 3)
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await audit_mod.cb_open(cb, lang="ru")
    text = cb.message.edit_text.await_args.args[0]
    assert "Аудит" in text
    assert "plan.create" in text
    assert "@boss" in text


async def test_cb_open_empty(file_db):
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await audit_mod.cb_open(cb, lang="ru")
    text = cb.message.edit_text.await_args.args[0]
    assert "Записей пока нет" in text


async def test_pagination_next_button_present(file_db):
    # 15 entries → 2 pages of 10.
    await _seed_audit(file_db, 15)
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await audit_mod.cb_open(cb, lang="ru")
    kb = cb.message.edit_text.await_args.kwargs["reply_markup"]
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert any("▶" in label for label in labels)


async def test_cb_page_second_page(file_db):
    await _seed_audit(file_db, 15)
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await audit_mod.cb_page(cb, AuditCB(action="open", page=1), lang="ru")
    kb = cb.message.edit_text.await_args.kwargs["reply_markup"]
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert any("Назад" in label for label in labels)
