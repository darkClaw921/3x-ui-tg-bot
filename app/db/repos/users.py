"""Repository for the ``users`` table.

All functions are ``async`` and accept an :class:`aiosqlite.Connection`
(connection injection — the connection lifecycle is owned by the caller, see
:func:`app.db.engine.get_conn`). The repository never opens its own
connection, never starts transactions for simple writes, and never imports
``settings`` directly except through :func:`get_or_create` which needs to
know the admin id list.

The :class:`User` dataclass is the canonical return type. Construct it from
an :class:`aiosqlite.Row` via :meth:`User.from_row` so call sites get a
typed object instead of a raw row.
"""

from __future__ import annotations

from dataclasses import dataclass

import aiosqlite

from app.config import settings


@dataclass(slots=True, frozen=True)
class User:
    """A row from the ``users`` table."""

    id: int
    tg_id: int
    username: str | None
    first_name: str | None
    is_admin: bool
    created_at: str

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> User:
        """Build a :class:`User` from an :class:`aiosqlite.Row`."""
        return cls(
            id=row["id"],
            tg_id=row["tg_id"],
            username=row["username"],
            first_name=row["first_name"],
            is_admin=bool(row["is_admin"]),
            created_at=row["created_at"],
        )


async def get_by_tg_id(conn: aiosqlite.Connection, tg_id: int) -> User | None:
    """Fetch a user by Telegram id. Returns ``None`` if not found."""
    cursor = await conn.execute(
        "SELECT id, tg_id, username, first_name, is_admin, created_at "
        "FROM users WHERE tg_id = ?",
        (tg_id,),
    )
    row = await cursor.fetchone()
    return User.from_row(row) if row else None


async def get_by_id(conn: aiosqlite.Connection, user_id: int) -> User | None:
    """Fetch a user by primary key. Returns ``None`` if not found."""
    cursor = await conn.execute(
        "SELECT id, tg_id, username, first_name, is_admin, created_at "
        "FROM users WHERE id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    return User.from_row(row) if row else None


async def get_by_username(
    conn: aiosqlite.Connection, username: str
) -> User | None:
    """Fetch a user by Telegram ``@username``. Case-insensitive.

    The leading ``@`` is stripped if present. Returns ``None`` if no
    matching user is registered. Used by the admin "Пользователи"
    screen to look up a user via @handle.
    """
    cleaned = username.lstrip("@").strip()
    if not cleaned:
        return None
    cursor = await conn.execute(
        "SELECT id, tg_id, username, first_name, is_admin, created_at "
        "FROM users WHERE username = ? COLLATE NOCASE",
        (cleaned,),
    )
    row = await cursor.fetchone()
    return User.from_row(row) if row else None


async def create(
    conn: aiosqlite.Connection,
    tg_id: int,
    username: str | None,
    first_name: str | None,
    is_admin: bool = False,
) -> User:
    """Insert a new user row and return the resulting :class:`User`.

    Caller is responsible for committing. Raises
    :class:`aiosqlite.IntegrityError` if ``tg_id`` is already present.
    """
    cursor = await conn.execute(
        "INSERT INTO users (tg_id, username, first_name, is_admin) "
        "VALUES (?, ?, ?, ?)",
        (tg_id, username, first_name, 1 if is_admin else 0),
    )
    await conn.commit()
    new_id = cursor.lastrowid
    assert new_id is not None  # sqlite always assigns AUTOINCREMENT id
    fetched = await get_by_id(conn, new_id)
    assert fetched is not None
    return fetched


async def get_or_create(
    conn: aiosqlite.Connection,
    tg_id: int,
    username: str | None,
    first_name: str | None,
) -> User:
    """Return an existing user by ``tg_id`` or create one.

    Idempotent — repeated calls with the same ``tg_id`` never produce
    duplicates (guarded by the UNIQUE index on ``tg_id``).

    The ``is_admin`` flag is derived from :data:`settings.ADMIN_IDS`; if the
    user already exists but the admin status diverges from the settings, the
    flag is synchronised so flips in ``.env`` take effect on the next call.
    """
    is_admin_now = tg_id in set(settings.ADMIN_IDS)

    existing = await get_by_tg_id(conn, tg_id)
    if existing is not None:
        if existing.is_admin != is_admin_now:
            await set_admin(conn, existing.id, is_admin_now)
            return User(
                id=existing.id,
                tg_id=existing.tg_id,
                username=existing.username,
                first_name=existing.first_name,
                is_admin=is_admin_now,
                created_at=existing.created_at,
            )
        return existing

    return await create(
        conn,
        tg_id=tg_id,
        username=username,
        first_name=first_name,
        is_admin=is_admin_now,
    )


async def set_admin(conn: aiosqlite.Connection, user_id: int, value: bool) -> None:
    """Toggle the ``is_admin`` flag for an existing user."""
    await conn.execute(
        "UPDATE users SET is_admin = ? WHERE id = ?",
        (1 if value else 0, user_id),
    )
    await conn.commit()
