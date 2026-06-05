"""User-side support-ticket flow (two-way chat through the bot).

The «❓ Поддержка» button (:func:`app.keyboards.user.user_main_menu`) opens a
short prompt and enters :class:`app.states.user.SupportFlow.writing`; the user's
next text message is recorded as a ticket message via
:func:`app.services.tickets.open_ticket` (which reuses the user's existing open
ticket or opens a fresh one), and the admins are notified.

Admins are notified two ways:

* every id in :data:`app.config.settings.ADMIN_IDS` receives a DM with the
  ticket id, the sender and the text;
* if :data:`app.config.settings.SUPPORT_CHAT_ID` is non-zero, the same notice is
  also posted to that shared triage chat.

The admin side (reply / close) lives in :mod:`app.handlers.admin.tickets`; an
admin reply is delivered back to the ticket owner from there. This module only
owns the user-facing capture + the admin notification fan-out.

Handlers
--------
* :func:`cb_open` — ``SupportCB(action='open')``: show the intro + prompt and
  enter :class:`SupportFlow.writing`.
* :func:`st_message` — text in :class:`SupportFlow.writing`: persist the message,
  notify admins, confirm to the user, clear the state.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger

from app.config import settings
from app.db.engine import get_conn
from app.db.repos.users import User
from app.i18n import DEFAULT_LANG, t
from app.keyboards.user import SupportCB, cancel_kb
from app.services import tickets as tickets_service
from app.states.user import SupportFlow

router = Router(name="user_support")


def _safe(value: object) -> str:
    """Escape ``<``/``>``/``&`` for HTML rendering inside the admin notice."""
    if value is None:
        return "—"
    text = str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _user_label(user: User) -> str:
    """Return a short human label for ``user`` used in the admin notice."""
    handle = f"@{user.username}" if user.username else f"#{user.tg_id}"
    name = _safe(user.first_name) if user.first_name else handle
    return f"{name} ({handle}, tg_id <code>{user.tg_id}</code>)"


async def notify_admins(
    bot: Bot, *, ticket_id: int, user: User, text: str
) -> None:
    """Fan a new ticket message out to the admins (DMs + optional shared chat).

    DMs every :data:`app.config.settings.ADMIN_IDS` admin and, when
    :data:`app.config.settings.SUPPORT_CHAT_ID` is set, also posts to that chat.
    Each send is best-effort: a failure to reach one admin (blocked the bot,
    never started it) is logged and does not abort the rest.
    """
    notice = t(
        "support.admin_notify",
        DEFAULT_LANG,
        ticket_id=ticket_id,
        user=_user_label(user),
        text=_safe(text),
    )
    targets: list[int] = list(dict.fromkeys(int(a) for a in settings.ADMIN_IDS))
    if settings.SUPPORT_CHAT_ID:
        targets.append(int(settings.SUPPORT_CHAT_ID))
    for chat_id in targets:
        try:
            await bot.send_message(chat_id, notice)
        except Exception as exc:  # noqa: BLE001 — best-effort per recipient
            logger.warning(
                "support: notify admin/chat {} failed for ticket {}: {}",
                chat_id,
                ticket_id,
                exc,
            )


@router.callback_query(SupportCB.filter(F.action == "open"))
async def cb_open(
    callback: CallbackQuery,
    state: FSMContext,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Open the support screen and enter the ticket-writing state."""
    if user is None:
        await callback.answer(t("support.need_start", lang), show_alert=True)
        return
    await state.set_state(SupportFlow.writing)
    if callback.message is not None:
        await callback.message.edit_text(
            t("support.intro", lang) + "\n\n" + t("support.prompt", lang),
            reply_markup=cancel_kb(lang),
        )
    await callback.answer()


@router.message(SupportFlow.writing)
async def st_message(
    message: Message,
    state: FSMContext,
    bot: Bot,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Capture the user's support message, persist it and notify admins."""
    if user is None:
        await state.clear()
        await message.answer(t("support.need_start", lang))
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer(t("support.empty", lang), reply_markup=cancel_kb(lang))
        return

    try:
        async with get_conn() as conn:
            ticket, _msg = await tickets_service.open_ticket(
                conn, user, text, tg_message_id=message.message_id
            )
    except Exception as exc:  # noqa: BLE001 — surface a soft failure
        logger.error("support: open_ticket failed for user {}: {}", user.id, exc)
        await state.clear()
        await message.answer(t("support.failed", lang))
        return

    await state.clear()
    await notify_admins(bot, ticket_id=ticket.id, user=user, text=text)
    await message.answer(t("support.sent", lang, ticket_id=ticket.id))


__all__ = ["notify_admins", "router"]
