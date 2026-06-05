"""Service layer for the two-way support-ticket flow.

This module owns the *status machine* of a support conversation so the user
and admin handlers never have to reason about transitions themselves:

    open_ticket / reply_user  →  ticket becomes 'open'     (awaiting admin)
    reply_admin               →  ticket becomes 'answered' (awaiting user)
    close_ticket              →  ticket becomes 'closed'    (terminal)

Every entry point appends the message to the transcript
(:func:`app.db.repos.tickets.add_message`) and then sets the status, so the DB
is always the single source of truth for both the conversation history and
whose turn it is. The handlers are responsible for the Telegram-side relay
(notifying admins of a new ticket, forwarding an admin reply to the user); this
layer is framework-agnostic and only touches the DB.

A user has at most one *active* (non-closed) ticket at a time: :func:`open_ticket`
reuses the user's existing open/answered ticket when present (attaching the new
message to it) instead of spawning a fresh one on every message, so a back-and-
forth conversation stays in a single thread.
"""

from __future__ import annotations

import aiosqlite

from app.db.repos import tickets as tickets_repo
from app.db.repos.tickets import Ticket, TicketMessage
from app.db.repos.users import User


async def open_ticket(
    conn: aiosqlite.Connection,
    user: User,
    text: str,
    *,
    tg_message_id: int | None = None,
) -> tuple[Ticket, TicketMessage]:
    """Record a user's support message, opening or reusing their ticket.

    If the user already has a non-closed ticket the message is appended to it
    (and the status is reset to ``'open'`` so it resurfaces for the admins);
    otherwise a brand-new ticket is created. Returns the ``(ticket, message)``
    pair so the caller can relay the message to the admins with the ticket id.
    """
    existing = await tickets_repo.get_open_for_user(conn, user.id)
    if existing is None:
        ticket = await tickets_repo.create_ticket(conn, user.id)
    else:
        ticket = existing
    message = await tickets_repo.add_message(
        conn, ticket.id, "user", text, tg_message_id=tg_message_id
    )
    # A new user message always awaits an admin → 'open'.
    if ticket.status != "open":
        await tickets_repo.set_status(conn, ticket.id, "open")
    refreshed = await tickets_repo.get(conn, ticket.id)
    assert refreshed is not None
    return refreshed, message


async def reply_user(
    conn: aiosqlite.Connection,
    ticket_id: int,
    text: str,
    *,
    tg_message_id: int | None = None,
) -> TicketMessage:
    """Append a user follow-up to an existing ticket and mark it ``'open'``.

    Used when the user replies inside an already-open conversation (the FSM
    pins the active ticket). Mirrors :func:`open_ticket` but never creates a new
    ticket — the ticket must already exist.
    """
    message = await tickets_repo.add_message(
        conn, ticket_id, "user", text, tg_message_id=tg_message_id
    )
    await tickets_repo.set_status(conn, ticket_id, "open")
    return message


async def reply_admin(
    conn: aiosqlite.Connection,
    ticket_id: int,
    text: str,
    *,
    tg_message_id: int | None = None,
) -> TicketMessage:
    """Append an admin reply to a ticket and mark it ``'answered'``.

    Records the admin's message in the transcript and flips the status to
    ``'answered'`` (awaiting the user). The caller forwards ``text`` to the
    ticket owner via the bot.
    """
    message = await tickets_repo.add_message(
        conn, ticket_id, "admin", text, tg_message_id=tg_message_id
    )
    await tickets_repo.set_status(conn, ticket_id, "answered")
    return message


async def close_ticket(conn: aiosqlite.Connection, ticket_id: int) -> None:
    """Mark a ticket ``'closed'`` (terminal). Idempotent."""
    await tickets_repo.set_status(conn, ticket_id, "closed")


__all__ = [
    "close_ticket",
    "open_ticket",
    "reply_admin",
    "reply_user",
]
