"""Admin «📜 Аудит» — paginated view of the admin-action trail.

Renders the most recent :class:`app.db.repos.audit.AuditEntry` rows (newest
first) — who did what, to which entity, when — written by
:func:`app.services.audit.log_action` from every privileged admin handler
(plan / promo CRUD, user revoke / toggle_admin / grant_sub / block, broadcast,
ticket reply / close).

The trail is paged with :class:`app.keyboards.admin.AuditCB` (``page`` is
0-based); each entry line resolves the acting admin's display name and folds the
optional JSON ``details`` blob into a compact suffix.

All handlers live behind :class:`app.middlewares.admin_only.AdminOnlyMiddleware`
(router-level on the parent admin router).
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.db.engine import get_conn
from app.db.repos import audit as audit_repo
from app.db.repos import users as users_repo
from app.db.repos.audit import AuditEntry
from app.i18n import DEFAULT_LANG, t
from app.keyboards.admin import AdminCB, AuditCB, audit_kb

router = Router(name="admin_audit")

_PAGE_SIZE = 10


def _safe(value: object) -> str:
    """Escape ``<``/``>``/``&`` for HTML rendering."""
    if value is None:
        return "—"
    text = str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def _admin_label(admin_id: int | None) -> str:
    """Resolve an acting admin's compact display label (or a dash)."""
    if admin_id is None:
        return "—"
    async with get_conn() as conn:
        admin = await users_repo.get_by_id(conn, admin_id)
    if admin is None:
        return f"#{admin_id}"
    if admin.username:
        return f"@{_safe(admin.username)}"
    return _safe(admin.first_name) if admin.first_name else f"#{admin.tg_id}"


def _target_suffix(entry: AuditEntry) -> str:
    """Build the `` → type#id`` suffix for an entry (empty when no target)."""
    if entry.target_type is None and entry.target_id is None:
        return ""
    type_part = entry.target_type or "?"
    id_part = f"#{entry.target_id}" if entry.target_id is not None else ""
    return f" → {type_part}{id_part}"


def _details_suffix(entry: AuditEntry) -> str:
    """Build the trailing ``(details)`` suffix for an entry (empty when none)."""
    if not entry.details:
        return ""
    return f"\n   <code>{_safe(entry.details)}</code>"


async def _render(message: Message, page: int, lang: str, *, edit: bool) -> None:
    """Render one audit page (edit current message or send a new one)."""
    offset = max(0, page) * _PAGE_SIZE
    async with get_conn() as conn:
        entries = await audit_repo.list_recent(conn, limit=_PAGE_SIZE, offset=offset)
        total = await audit_repo.count(conn)

    lines = [t("admin.audit.title", lang), ""]
    if not entries:
        lines.append(t("admin.audit.empty", lang))
    else:
        for entry in entries:
            lines.append(
                t(
                    "admin.audit.item",
                    lang,
                    created_at=entry.created_at,
                    admin=await _admin_label(entry.admin_id),
                    action=_safe(entry.action),
                    target=_target_suffix(entry),
                    details=_details_suffix(entry),
                )
            )
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3900] + "\n…"

    has_prev = page > 0
    has_next = offset + _PAGE_SIZE < total
    kb = audit_kb(page=page, has_prev=has_prev, has_next=has_next, lang=lang)
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@router.callback_query(AdminCB.filter((F.area == "audit") & (F.action == "open")))
async def cb_open(callback: CallbackQuery, lang: str = DEFAULT_LANG) -> None:
    """Entry point from the admin main menu — render the first audit page."""
    if callback.message is not None:
        await _render(callback.message, 0, lang, edit=True)
    await callback.answer()


@router.callback_query(AuditCB.filter(F.action == "open"))
async def cb_page(
    callback: CallbackQuery, callback_data: AuditCB, lang: str = DEFAULT_LANG
) -> None:
    """Render the requested audit page."""
    if callback.message is not None:
        await _render(callback.message, callback_data.page, lang, edit=True)
    await callback.answer()


__all__ = ["router"]
