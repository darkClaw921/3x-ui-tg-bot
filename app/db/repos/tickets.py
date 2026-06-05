"""Repository for the ``tickets`` + ``ticket_messages`` tables.

A *ticket* is a two-way support conversation between a user and the admins,
relayed through the bot. Each ticket has a ``status`` that walks:

    open      → the user wrote, awaiting an admin reply
    answered  → an admin replied, awaiting the user
    closed    → the conversation is resolved (terminal)

The transcript lives in ``ticket_messages`` — one append-only row per message,
tagged with ``sender`` (``'user'`` or ``'admin'``) and the relayed Telegram
message id (best-effort, nullable). ``tickets.updated_at`` is bumped on every
new message / status change so :func:`list_open` can surface the most recently
active conversations first.

All functions are ``async`` and accept a caller-owned
:class:`aiosqlite.Connection` (connection injection — see
:func:`app.db.engine.get_conn`); they commit their own writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import aiosqlite

TicketStatus = Literal["open", "answered", "closed"]
TicketSender = Literal["user", "admin"]


def _utcnow_iso() -> str:
    """Return current UTC time in ISO-8601 (seconds resolution)."""
    return datetime.now(UTC).replace(microsecond=0).isoformat(sep=" ")


@dataclass(slots=True, frozen=True)
class Ticket:
    """A row from the ``tickets`` table."""

    id: int
    user_id: int
    status: TicketStatus
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> Ticket:
        """Build a :class:`Ticket` from an :class:`aiosqlite.Row`."""
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@dataclass(slots=True, frozen=True)
class TicketMessage:
    """A row from the ``ticket_messages`` table."""

    id: int
    ticket_id: int
    sender: TicketSender
    text: str
    tg_message_id: int | None
    created_at: str

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> TicketMessage:
        """Build a :class:`TicketMessage` from an :class:`aiosqlite.Row`."""
        return cls(
            id=row["id"],
            ticket_id=row["ticket_id"],
            sender=row["sender"],
            text=row["text"],
            tg_message_id=row["tg_message_id"],
            created_at=row["created_at"],
        )


_SELECT_TICKET = "SELECT id, user_id, status, created_at, updated_at FROM tickets"
_SELECT_MESSAGE = (
    "SELECT id, ticket_id, sender, text, tg_message_id, created_at "
    "FROM ticket_messages"
)


async def create_ticket(conn: aiosqlite.Connection, user_id: int) -> Ticket:
    """Open a fresh ``'open'`` ticket for ``user_id`` and return it."""
    cursor = await conn.execute(
        "INSERT INTO tickets (user_id, status) VALUES (?, 'open')",
        (user_id,),
    )
    await conn.commit()
    new_id = cursor.lastrowid
    assert new_id is not None
    created = await get(conn, new_id)
    assert created is not None
    return created


async def add_message(
    conn: aiosqlite.Connection,
    ticket_id: int,
    sender: TicketSender,
    text: str,
    tg_message_id: int | None = None,
) -> TicketMessage:
    """Append a message to a ticket and bump ``tickets.updated_at``.

    The status transition is **not** decided here — callers
    (:mod:`app.services.tickets`) set ``open`` / ``answered`` explicitly via
    :func:`set_status` so the two-way routing stays in one place. This function
    only records the message and refreshes the parent ticket's ``updated_at`` so
    the open list can be ordered by recency.
    """
    cursor = await conn.execute(
        "INSERT INTO ticket_messages (ticket_id, sender, text, tg_message_id) "
        "VALUES (?, ?, ?, ?)",
        (ticket_id, sender, text, tg_message_id),
    )
    await conn.execute(
        "UPDATE tickets SET updated_at = ? WHERE id = ?",
        (_utcnow_iso(), ticket_id),
    )
    await conn.commit()
    new_id = cursor.lastrowid
    assert new_id is not None
    fetched = await _get_message(conn, new_id)
    assert fetched is not None
    return fetched


async def get(conn: aiosqlite.Connection, ticket_id: int) -> Ticket | None:
    """Fetch a ticket by primary key. Returns ``None`` if not found."""
    cursor = await conn.execute(
        f"{_SELECT_TICKET} WHERE id = ?", (ticket_id,)
    )
    row = await cursor.fetchone()
    return Ticket.from_row(row) if row else None


async def _get_message(
    conn: aiosqlite.Connection, message_id: int
) -> TicketMessage | None:
    """Fetch a ticket message by primary key (internal helper)."""
    cursor = await conn.execute(
        f"{_SELECT_MESSAGE} WHERE id = ?", (message_id,)
    )
    row = await cursor.fetchone()
    return TicketMessage.from_row(row) if row else None


async def list_open(conn: aiosqlite.Connection) -> list[Ticket]:
    """Return every non-closed ticket, most-recently-active first.

    Both ``'open'`` and ``'answered'`` tickets are returned — an admin needs to
    see conversations awaiting a reply *and* ones they already answered that the
    user might follow up on. Ordered by ``updated_at`` descending so the list
    reads as an activity feed. Used by the admin «💬 Тикеты» screen.
    """
    cursor = await conn.execute(
        f"{_SELECT_TICKET} WHERE status != 'closed' "
        "ORDER BY updated_at DESC, id DESC"
    )
    rows = await cursor.fetchall()
    return [Ticket.from_row(r) for r in rows]


async def list_for_user(
    conn: aiosqlite.Connection, user_id: int
) -> list[Ticket]:
    """Return all tickets opened by ``user_id``, newest first."""
    cursor = await conn.execute(
        f"{_SELECT_TICKET} WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    )
    rows = await cursor.fetchall()
    return [Ticket.from_row(r) for r in rows]


async def get_open_for_user(
    conn: aiosqlite.Connection, user_id: int
) -> Ticket | None:
    """Return the user's latest non-closed ticket, or ``None``.

    Used by the user support flow to attach a follow-up message to the existing
    conversation instead of spawning a new ticket on every message.
    """
    cursor = await conn.execute(
        f"{_SELECT_TICKET} WHERE user_id = ? AND status != 'closed' "
        "ORDER BY id DESC LIMIT 1",
        (user_id,),
    )
    row = await cursor.fetchone()
    return Ticket.from_row(row) if row else None


async def set_status(
    conn: aiosqlite.Connection, ticket_id: int, status: TicketStatus
) -> None:
    """Set a ticket's ``status`` and bump ``updated_at``. Commits immediately."""
    await conn.execute(
        "UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?",
        (status, _utcnow_iso(), ticket_id),
    )
    await conn.commit()


async def list_messages(
    conn: aiosqlite.Connection, ticket_id: int
) -> list[TicketMessage]:
    """Return a ticket's transcript in chronological order."""
    cursor = await conn.execute(
        f"{_SELECT_MESSAGE} WHERE ticket_id = ? ORDER BY id ASC",
        (ticket_id,),
    )
    rows = await cursor.fetchall()
    return [TicketMessage.from_row(r) for r in rows]


__all__ = [
    "Ticket",
    "TicketMessage",
    "TicketSender",
    "TicketStatus",
    "add_message",
    "create_ticket",
    "get",
    "get_open_for_user",
    "list_for_user",
    "list_messages",
    "list_open",
    "set_status",
]
