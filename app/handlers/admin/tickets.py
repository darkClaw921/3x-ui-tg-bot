"""Admin «💬 Тикеты» — open-ticket list, ticket card, two-way reply / close.

The admin side of the support flow. The user side
(:mod:`app.handlers.user.support`) captures a ticket message and notifies the
admins; here an admin browses open tickets, reads the transcript, and replies
or closes a ticket. An admin reply is recorded
(:func:`app.services.tickets.reply_admin`, status → ``'answered'``) and relayed
to the ticket owner via the bot, so the conversation is fully bidirectional and
its history is persisted in the DB.

Handlers
--------
* :func:`cb_open` / :func:`cb_list` — render the open-ticket list
  (``AdminCB(area='tickets', action='open')`` / ``TicketCB(action='list')``).
* :func:`cb_card` — open a ticket card with its transcript
  (``TicketCB(action='card', id=<ticket_id>)``).
* :func:`cb_reply` — enter :class:`AdminTicketReply.writing`
  (``TicketCB(action='reply', id=<ticket_id>)``).
* :func:`st_reply` — capture the admin's reply, persist it, relay it to the
  user, re-render the card.
* :func:`cb_close` — close the ticket (``TicketCB(action='close', id=...)``).

All handlers live behind :class:`app.middlewares.admin_only.AdminOnlyMiddleware`
(router-level on the parent admin router) — no per-handler admin checks needed.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger

from app.db.engine import get_conn
from app.db.repos import tickets as tickets_repo
from app.db.repos import users as users_repo
from app.db.repos.tickets import Ticket
from app.db.repos.users import User
from app.i18n import DEFAULT_LANG, t
from app.keyboards.admin import AdminCB, TicketCB, cancel_kb, ticket_card_kb, tickets_list_kb
from app.services import audit as audit_service
from app.services import tickets as tickets_service
from app.states.admin import AdminTicketReply

router = Router(name="admin_tickets")

_MAX_HISTORY = 20


def _safe(value: object) -> str:
    """Escape ``<``/``>``/``&`` for HTML rendering."""
    if value is None:
        return "—"
    text = str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _status_label(status: str, lang: str) -> str:
    """Map a ticket status to its localized label."""
    return {
        "open": t("admin.tickets.status_open", lang),
        "answered": t("admin.tickets.status_answered", lang),
        "closed": t("admin.tickets.status_closed", lang),
    }.get(status, status)


def _user_short(user: User | None) -> str:
    """Return a compact user label for the list / card."""
    if user is None:
        return "—"
    if user.username:
        return f"@{_safe(user.username)}"
    return _safe(user.first_name) if user.first_name else f"#{user.tg_id}"


async def _render_list(message: Message, lang: str, *, edit: bool) -> None:
    """Render the open-ticket list (edit current message or send a new one)."""
    async with get_conn() as conn:
        tickets = await tickets_repo.list_open(conn)
        labels: list[tuple[int, str]] = []
        for ticket in tickets:
            owner = await users_repo.get_by_id(conn, ticket.user_id)
            labels.append(
                (
                    ticket.id,
                    t(
                        "admin.tickets.list_item",
                        lang,
                        ticket_id=ticket.id,
                        status=_status_label(ticket.status, lang),
                        user=_user_short(owner),
                        updated_at=ticket.updated_at,
                    ),
                )
            )

    if not tickets:
        text = t("admin.tickets.title", lang) + "\n\n" + t("admin.tickets.empty", lang)
    else:
        text = t("admin.tickets.title", lang)
    kb = tickets_list_kb(labels, lang=lang)
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


async def _build_card(ticket: Ticket, lang: str) -> str:
    """Build the HTML body of a ticket card (header + transcript)."""
    async with get_conn() as conn:
        owner = await users_repo.get_by_id(conn, ticket.user_id)
        messages = await tickets_repo.list_messages(conn, ticket.id)

    lines = [
        t(
            "admin.tickets.card_header",
            lang,
            ticket_id=ticket.id,
            user=_user_short(owner),
            status=_status_label(ticket.status, lang),
        ),
        "",
        t("admin.tickets.history_title", lang),
    ]
    shown = messages[-_MAX_HISTORY:]
    for msg in shown:
        key = "admin.tickets.msg_admin" if msg.sender == "admin" else "admin.tickets.msg_user"
        lines.append(t(key, lang, text=_safe(msg.text)))
    if len(messages) > _MAX_HISTORY:
        lines.insert(3, f"… (+{len(messages) - _MAX_HISTORY})")
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3900] + "\n…"
    return text


async def _render_card(
    message: Message, ticket: Ticket, lang: str, *, edit: bool
) -> None:
    """Render a ticket card (edit current message or send a new one)."""
    text = await _build_card(ticket, lang)
    kb = ticket_card_kb(ticket.id, is_closed=ticket.status == "closed", lang=lang)
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


# --------------------------------------------------------------------- #
# Navigation
# --------------------------------------------------------------------- #


@router.callback_query(AdminCB.filter((F.area == "tickets") & (F.action == "open")))
async def cb_open(
    callback: CallbackQuery, state: FSMContext, lang: str = DEFAULT_LANG
) -> None:
    """Entry point from the admin main menu — render the open-ticket list."""
    await state.clear()
    if callback.message is not None:
        await _render_list(callback.message, lang, edit=True)
    await callback.answer()


@router.callback_query(TicketCB.filter(F.action == "list"))
async def cb_list(
    callback: CallbackQuery, state: FSMContext, lang: str = DEFAULT_LANG
) -> None:
    """Re-render the open-ticket list (back from a card)."""
    await state.clear()
    if callback.message is not None:
        await _render_list(callback.message, lang, edit=True)
    await callback.answer()


@router.callback_query(TicketCB.filter(F.action == "card"))
async def cb_card(
    callback: CallbackQuery,
    callback_data: TicketCB,
    state: FSMContext,
    lang: str = DEFAULT_LANG,
) -> None:
    """Open a ticket card with its transcript."""
    await state.clear()
    async with get_conn() as conn:
        ticket = await tickets_repo.get(conn, callback_data.id)
    if ticket is None:
        await callback.answer(t("admin.tickets.not_found", lang), show_alert=True)
        return
    if callback.message is not None:
        await _render_card(callback.message, ticket, lang, edit=True)
    await callback.answer()


# --------------------------------------------------------------------- #
# Reply (AdminTicketReply FSM)
# --------------------------------------------------------------------- #


@router.callback_query(TicketCB.filter(F.action == "reply"))
async def cb_reply(
    callback: CallbackQuery,
    callback_data: TicketCB,
    state: FSMContext,
    lang: str = DEFAULT_LANG,
) -> None:
    """Enter the reply state for a ticket."""
    async with get_conn() as conn:
        ticket = await tickets_repo.get(conn, callback_data.id)
    if ticket is None:
        await callback.answer(t("admin.tickets.not_found", lang), show_alert=True)
        return
    await state.set_state(AdminTicketReply.writing)
    await state.update_data(reply_ticket_id=ticket.id)
    if callback.message is not None:
        await callback.message.edit_text(
            t("admin.tickets.reply_prompt", lang, ticket_id=ticket.id),
            reply_markup=cancel_kb(lang),
        )
    await callback.answer()


@router.message(AdminTicketReply.writing)
async def st_reply(
    message: Message,
    state: FSMContext,
    bot: Bot,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Persist the admin reply, relay it to the user, re-render the card."""
    text = (message.text or "").strip()
    if not text:
        await message.answer(
            t("admin.tickets.reply_empty", lang), reply_markup=cancel_kb(lang)
        )
        return

    data = await state.get_data()
    ticket_id = int(data.get("reply_ticket_id", 0))
    async with get_conn() as conn:
        ticket = await tickets_repo.get(conn, ticket_id)
        if ticket is None:
            await state.clear()
            await message.answer(t("admin.tickets.not_found", lang))
            return
        await tickets_service.reply_admin(
            conn, ticket_id, text, tg_message_id=message.message_id
        )
        owner = await users_repo.get_by_id(conn, ticket.user_id)
        await audit_service.log_action(
            conn,
            user.id if user is not None else None,
            "ticket.reply",
            target_type="ticket",
            target_id=ticket_id,
        )

    await state.clear()

    # Relay the reply to the ticket owner (best-effort).
    delivered = True
    if owner is not None:
        try:
            await bot.send_message(
                owner.tg_id,
                t(
                    "support.reply_received",
                    owner.lang,
                    ticket_id=ticket_id,
                    text=text,
                ),
            )
        except Exception as exc:  # noqa: BLE001 — user may have blocked the bot
            delivered = False
            logger.warning(
                "admin_tickets: reply delivery to user {} failed: {}",
                owner.tg_id,
                exc,
            )

    await message.answer(
        t("admin.tickets.reply_sent", lang)
        if delivered
        else t("admin.tickets.reply_failed", lang)
    )
    async with get_conn() as conn:
        refreshed = await tickets_repo.get(conn, ticket_id)
    if refreshed is not None:
        await _render_card(message, refreshed, lang, edit=False)


# --------------------------------------------------------------------- #
# Close
# --------------------------------------------------------------------- #


@router.callback_query(TicketCB.filter(F.action == "close"))
async def cb_close(
    callback: CallbackQuery,
    callback_data: TicketCB,
    state: FSMContext,
    bot: Bot,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Close a ticket, notify the owner, re-render the card."""
    await state.clear()
    ticket_id = callback_data.id
    async with get_conn() as conn:
        ticket = await tickets_repo.get(conn, ticket_id)
        if ticket is None:
            await callback.answer(t("admin.tickets.not_found", lang), show_alert=True)
            return
        await tickets_service.close_ticket(conn, ticket_id)
        owner = await users_repo.get_by_id(conn, ticket.user_id)
        await audit_service.log_action(
            conn,
            user.id if user is not None else None,
            "ticket.close",
            target_type="ticket",
            target_id=ticket_id,
        )

    if owner is not None:
        try:
            await bot.send_message(
                owner.tg_id,
                t("support.closed_notice", owner.lang, ticket_id=ticket_id),
            )
        except Exception as exc:  # noqa: BLE001 — best-effort notice
            logger.warning(
                "admin_tickets: close notice to user {} failed: {}",
                owner.tg_id,
                exc,
            )

    async with get_conn() as conn:
        refreshed = await tickets_repo.get(conn, ticket_id)
    if callback.message is not None and refreshed is not None:
        await _render_card(callback.message, refreshed, lang, edit=True)
    await callback.answer(t("admin.tickets.closed", lang, ticket_id=ticket_id))


__all__ = ["router"]
