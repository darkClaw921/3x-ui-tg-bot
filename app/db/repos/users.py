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
from app.i18n import resolve_lang


@dataclass(slots=True, frozen=True)
class User:
    """A row from the ``users`` table.

    ``lang`` carries the user's preferred UI language (one of
    :data:`app.i18n.SUPPORTED_LANGS`). It is declared last with a default of
    ``"ru"`` so existing positional ``User(...)`` constructors in tests (which
    predate the column) keep working unchanged.

    ``is_blocked`` flags a user banned by an admin (default ``False``); it is
    declared after ``lang`` with its own default so legacy positional
    constructors keep working. A blocked user is short-circuited by
    :class:`app.middlewares.blocked.BlockedUserMiddleware`.
    """

    id: int
    tg_id: int
    username: str | None
    first_name: str | None
    is_admin: bool
    created_at: str
    lang: str = "ru"
    is_blocked: bool = False

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> User:
        """Build a :class:`User` from an :class:`aiosqlite.Row`.

        Tolerates rows selected without the ``lang`` / ``is_blocked`` columns
        (defaults to ``"ru"`` / ``False``) so call sites that select a narrow
        column set still work.
        """
        keys = row.keys()
        return cls(
            id=row["id"],
            tg_id=row["tg_id"],
            username=row["username"],
            first_name=row["first_name"],
            is_admin=bool(row["is_admin"]),
            created_at=row["created_at"],
            lang=row["lang"] if "lang" in keys else "ru",
            is_blocked=bool(row["is_blocked"]) if "is_blocked" in keys else False,
        )


async def get_by_tg_id(conn: aiosqlite.Connection, tg_id: int) -> User | None:
    """Fetch a user by Telegram id. Returns ``None`` if not found."""
    cursor = await conn.execute(
        "SELECT id, tg_id, username, first_name, is_admin, lang, is_blocked, created_at "
        "FROM users WHERE tg_id = ?",
        (tg_id,),
    )
    row = await cursor.fetchone()
    return User.from_row(row) if row else None


async def get_by_id(conn: aiosqlite.Connection, user_id: int) -> User | None:
    """Fetch a user by primary key. Returns ``None`` if not found."""
    cursor = await conn.execute(
        "SELECT id, tg_id, username, first_name, is_admin, lang, is_blocked, created_at "
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
        "SELECT id, tg_id, username, first_name, is_admin, lang, is_blocked, created_at "
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
    *,
    language_code: str | None = None,
) -> User:
    """Insert a new user row and return the resulting :class:`User`.

    ``language_code`` is the raw Telegram code (e.g. ``"en-US"``); it is
    normalized to a supported UI language via :func:`app.i18n.resolve_lang`
    (unknown/absent → :data:`app.i18n.DEFAULT_LANG`, i.e. ``"ru"``) and stored
    in the ``lang`` column.

    Caller is responsible for committing. Raises
    :class:`aiosqlite.IntegrityError` if ``tg_id`` is already present.
    """
    lang = resolve_lang(language_code)
    cursor = await conn.execute(
        "INSERT INTO users (tg_id, username, first_name, is_admin, lang) "
        "VALUES (?, ?, ?, ?, ?)",
        (tg_id, username, first_name, 1 if is_admin else 0, lang),
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
    *,
    language_code: str | None = None,
) -> User:
    """Return an existing user by ``tg_id`` or create one.

    Idempotent — repeated calls with the same ``tg_id`` never produce
    duplicates (guarded by the UNIQUE index on ``tg_id``).

    The ``is_admin`` flag is derived from :data:`settings.ADMIN_IDS`; if the
    user already exists but the admin status diverges from the settings, the
    flag is synchronised so flips in ``.env`` take effect on the next call.

    ``language_code`` (the raw Telegram code) only affects **new** rows — it
    seeds the initial UI language via :func:`app.i18n.resolve_lang`. An existing
    user's chosen ``lang`` is never overwritten here; it is changed only through
    the explicit language picker (:func:`set_lang`).
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
                lang=existing.lang,
                is_blocked=existing.is_blocked,
            )
        return existing

    return await create(
        conn,
        tg_id=tg_id,
        username=username,
        first_name=first_name,
        is_admin=is_admin_now,
        language_code=language_code,
    )


async def list_all_tg_ids(conn: aiosqlite.Connection) -> list[int]:
    """Return the Telegram ids of every registered user, oldest first.

    Used by the admin broadcast flow (:mod:`app.handlers.admin.broadcast`)
    to fan a post out to the whole audience. Only ``tg_id`` is selected —
    the broadcaster needs nothing else, and keeping the row narrow lets the
    list scale to large audiences cheaply.
    """
    cursor = await conn.execute("SELECT tg_id FROM users ORDER BY id")
    rows = await cursor.fetchall()
    return [int(row["tg_id"]) for row in rows]


async def set_admin(conn: aiosqlite.Connection, user_id: int, value: bool) -> None:
    """Toggle the ``is_admin`` flag for an existing user."""
    await conn.execute(
        "UPDATE users SET is_admin = ? WHERE id = ?",
        (1 if value else 0, user_id),
    )
    await conn.commit()


async def set_blocked(
    conn: aiosqlite.Connection, user_id: int, blocked: bool
) -> None:
    """Set the ``is_blocked`` flag for an existing user (ban / unban).

    A blocked user is short-circuited by
    :class:`app.middlewares.blocked.BlockedUserMiddleware` before any handler
    runs. Toggled from the admin user card. Commits immediately.
    """
    await conn.execute(
        "UPDATE users SET is_blocked = ? WHERE id = ?",
        (1 if blocked else 0, user_id),
    )
    await conn.commit()


async def is_blocked(conn: aiosqlite.Connection, tg_id: int) -> bool:
    """Return ``True`` iff the user with ``tg_id`` is blocked.

    A narrow lookup by Telegram id used by
    :class:`app.middlewares.blocked.BlockedUserMiddleware` so the ban check
    needs neither the full :class:`User` row nor a prior
    :class:`app.middlewares.user_ctx.UserContextMiddleware` pass. Returns
    ``False`` for unknown users (nothing to block yet).
    """
    cursor = await conn.execute(
        "SELECT is_blocked FROM users WHERE tg_id = ?",
        (tg_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return False
    return bool(row["is_blocked"])


async def set_lang(conn: aiosqlite.Connection, user_id: int, lang: str) -> None:
    """Persist the user's chosen UI ``lang`` (must be a supported code).

    Used by the language picker (:mod:`app.handlers.user.language`). The value
    is normalized through :func:`app.i18n.resolve_lang` defensively so an
    unsupported code never reaches the DB. Commits immediately.
    """
    await conn.execute(
        "UPDATE users SET lang = ? WHERE id = ?",
        (resolve_lang(lang), user_id),
    )
    await conn.commit()


async def get_lang(conn: aiosqlite.Connection, user_id: int) -> str:
    """Return the user's stored UI ``lang``.

    Falls back to :data:`app.i18n.DEFAULT_LANG` (via :func:`app.i18n.resolve_lang`)
    when the user does not exist, so callers always receive a renderable code.
    """
    cursor = await conn.execute(
        "SELECT lang FROM users WHERE id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return resolve_lang(None)
    return row["lang"]
