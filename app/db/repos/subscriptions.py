"""Repository for ``subscriptions`` and ``traffic_snapshots``.

These two tables are co-located in one module because traffic snapshots are
always per-subscription and never queried independently.

Timestamps (``expires_at``, ``taken_at``) are stored as ISO-8601 strings
(SQLite has no native datetime type). Helpers accept either naive ``str``
ISO values from callers or :class:`datetime.datetime`. Datetimes are
serialised in UTC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import aiosqlite

SubscriptionStatus = Literal["active", "expired", "revoked"]


def _to_iso(value: datetime | str) -> str:
    """Normalize ``value`` to an ISO-8601 string in UTC."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        else:
            value = value.astimezone(UTC)
        return value.replace(microsecond=0).isoformat(sep=" ")
    return value


def _utcnow_iso() -> str:
    """Return current UTC time in ISO-8601 (seconds resolution)."""
    return datetime.now(UTC).replace(microsecond=0).isoformat(sep=" ")


@dataclass(slots=True, frozen=True)
class Subscription:
    """A row from the ``subscriptions`` table."""

    id: int
    user_id: int
    xui_inbound_id: int
    xui_client_uuid: str
    xui_client_email: str
    xui_sub_id: str
    expires_at: str
    created_at: str
    plan_id: int | None
    status: SubscriptionStatus

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> Subscription:
        """Build a :class:`Subscription` from an :class:`aiosqlite.Row`."""
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            xui_inbound_id=row["xui_inbound_id"],
            xui_client_uuid=row["xui_client_uuid"],
            xui_client_email=row["xui_client_email"],
            xui_sub_id=row["xui_sub_id"],
            expires_at=row["expires_at"],
            created_at=row["created_at"],
            plan_id=row["plan_id"],
            status=row["status"],
        )


@dataclass(slots=True, frozen=True)
class TrafficSnapshot:
    """A row from the ``traffic_snapshots`` table."""

    id: int
    subscription_id: int
    up: int
    down: int
    taken_at: str

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> TrafficSnapshot:
        """Build a :class:`TrafficSnapshot` from an :class:`aiosqlite.Row`."""
        return cls(
            id=row["id"],
            subscription_id=row["subscription_id"],
            up=row["up"],
            down=row["down"],
            taken_at=row["taken_at"],
        )


_SELECT = (
    "SELECT id, user_id, xui_inbound_id, xui_client_uuid, xui_client_email, "
    "xui_sub_id, expires_at, created_at, plan_id, status FROM subscriptions"
)


async def create(
    conn: aiosqlite.Connection,
    user_id: int,
    xui_inbound_id: int,
    xui_client_uuid: str,
    xui_client_email: str,
    expires_at: datetime | str,
    plan_id: int | None,
    xui_sub_id: str = "",
) -> Subscription:
    """Insert a new active subscription.

    ``xui_sub_id`` is the panel's ``subId`` used by the public
    subscription URL (``/sub/<sub_id>``). Defaults to the empty string so
    old call sites keep compiling; the user purchase flow always passes
    a non-empty value.
    """
    cursor = await conn.execute(
        "INSERT INTO subscriptions "
        "(user_id, xui_inbound_id, xui_client_uuid, xui_client_email, "
        " xui_sub_id, expires_at, plan_id, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'active')",
        (
            user_id,
            xui_inbound_id,
            xui_client_uuid,
            xui_client_email,
            xui_sub_id,
            _to_iso(expires_at),
            plan_id,
        ),
    )
    await conn.commit()
    new_id = cursor.lastrowid
    assert new_id is not None
    sub = await get(conn, new_id)
    assert sub is not None
    return sub


async def get(conn: aiosqlite.Connection, sub_id: int) -> Subscription | None:
    """Fetch a subscription by primary key. Returns ``None`` if not found."""
    cursor = await conn.execute(f"{_SELECT} WHERE id = ?", (sub_id,))
    row = await cursor.fetchone()
    return Subscription.from_row(row) if row else None


async def get_active_for_user(
    conn: aiosqlite.Connection, user_id: int
) -> Subscription | None:
    """Return the user's latest active subscription, or ``None``.

    Active means ``status='active'`` AND ``expires_at > now``. If the user
    has multiple active rows (shouldn't happen — :func:`create_or_extend`
    prevents it — but be defensive), the one with the latest ``expires_at``
    wins.
    """
    now = _utcnow_iso()
    cursor = await conn.execute(
        f"{_SELECT} "
        "WHERE user_id = ? AND status = 'active' AND expires_at > ? "
        "ORDER BY expires_at DESC, id DESC LIMIT 1",
        (user_id, now),
    )
    row = await cursor.fetchone()
    return Subscription.from_row(row) if row else None


async def list_for_user(
    conn: aiosqlite.Connection, user_id: int
) -> list[Subscription]:
    """Return all subscriptions for a user, newest first."""
    cursor = await conn.execute(
        f"{_SELECT} WHERE user_id = ? ORDER BY created_at DESC, id DESC",
        (user_id,),
    )
    rows = await cursor.fetchall()
    return [Subscription.from_row(r) for r in rows]


async def extend(
    conn: aiosqlite.Connection,
    sub_id: int,
    new_expires_at: datetime | str,
) -> None:
    """Move ``expires_at`` forward; leave ``status`` untouched."""
    await conn.execute(
        "UPDATE subscriptions SET expires_at = ? WHERE id = ?",
        (_to_iso(new_expires_at), sub_id),
    )
    await conn.commit()


async def set_status(
    conn: aiosqlite.Connection,
    sub_id: int,
    status: SubscriptionStatus,
) -> None:
    """Update only the ``status`` column. ``expires_at`` is preserved."""
    await conn.execute(
        "UPDATE subscriptions SET status = ? WHERE id = ?",
        (status, sub_id),
    )
    await conn.commit()


async def list_expired_active(
    conn: aiosqlite.Connection,
    now: datetime | str | None = None,
) -> list[Subscription]:
    """Return active subscriptions whose ``expires_at <= now``.

    Used by the expire-checker job (Phase 8) to find rows that should be
    moved to ``status='expired'`` and have their xui client disabled.
    """
    now_iso = _to_iso(now) if now is not None else _utcnow_iso()
    cursor = await conn.execute(
        f"{_SELECT} "
        "WHERE status = 'active' AND expires_at <= ? "
        "ORDER BY expires_at ASC, id ASC",
        (now_iso,),
    )
    rows = await cursor.fetchall()
    return [Subscription.from_row(r) for r in rows]


async def list_active(conn: aiosqlite.Connection) -> list[Subscription]:
    """Return all currently-active (status + not expired) subscriptions."""
    now = _utcnow_iso()
    cursor = await conn.execute(
        f"{_SELECT} "
        "WHERE status = 'active' AND expires_at > ? "
        "ORDER BY expires_at ASC, id ASC",
        (now,),
    )
    rows = await cursor.fetchall()
    return [Subscription.from_row(r) for r in rows]


async def list_expiring_in(
    conn: aiosqlite.Connection, days: int
) -> list[Subscription]:
    """Return active subscriptions expiring within ``days`` days from now.

    Used by the reminder job (Phase 8). The window is ``[now, now+days]``.
    """
    now_dt = datetime.now(UTC).replace(microsecond=0)
    end_dt = now_dt + timedelta(days=days)
    now_iso = now_dt.isoformat(sep=" ")
    end_iso = end_dt.isoformat(sep=" ")
    cursor = await conn.execute(
        f"{_SELECT} "
        "WHERE status = 'active' AND expires_at > ? AND expires_at <= ? "
        "ORDER BY expires_at ASC, id ASC",
        (now_iso, end_iso),
    )
    rows = await cursor.fetchall()
    return [Subscription.from_row(r) for r in rows]


async def add_traffic_snapshot(
    conn: aiosqlite.Connection,
    sub_id: int,
    up: int,
    down: int,
) -> TrafficSnapshot:
    """Append a traffic snapshot for a subscription."""
    cursor = await conn.execute(
        "INSERT INTO traffic_snapshots (subscription_id, up, down) "
        "VALUES (?, ?, ?)",
        (sub_id, up, down),
    )
    await conn.commit()
    new_id = cursor.lastrowid
    assert new_id is not None
    fetched = await conn.execute(
        "SELECT id, subscription_id, up, down, taken_at "
        "FROM traffic_snapshots WHERE id = ?",
        (new_id,),
    )
    row = await fetched.fetchone()
    assert row is not None
    return TrafficSnapshot.from_row(row)


NotificationKind = Literal["3d", "1d", "0d", "expired"]


async def try_mark_notification_sent(
    conn: aiosqlite.Connection,
    sub_id: int,
    kind: NotificationKind,
) -> bool:
    """Atomically record a notification of ``kind`` for ``sub_id``.

    Returns ``True`` if the row was inserted (i.e. the caller should send the
    Telegram message). Returns ``False`` if a row with this ``(sub_id, kind)``
    already exists — used as a deduplication guard so the scheduler does not
    spam users on repeated runs.

    Implementation uses ``INSERT OR IGNORE`` against the
    ``UNIQUE(subscription_id, kind)`` constraint, so the check + insert is a
    single SQL statement (no TOCTOU window).
    """
    cursor = await conn.execute(
        "INSERT OR IGNORE INTO subscription_notifications "
        "(subscription_id, kind) VALUES (?, ?)",
        (sub_id, kind),
    )
    await conn.commit()
    # ``rowcount`` is 1 when the INSERT actually happened, 0 when IGNOREd.
    return cursor.rowcount == 1


async def last_traffic_snapshot(
    conn: aiosqlite.Connection, sub_id: int
) -> TrafficSnapshot | None:
    """Return the most recent snapshot for a subscription, or ``None``."""
    cursor = await conn.execute(
        "SELECT id, subscription_id, up, down, taken_at "
        "FROM traffic_snapshots "
        "WHERE subscription_id = ? "
        "ORDER BY taken_at DESC, id DESC LIMIT 1",
        (sub_id,),
    )
    row = await cursor.fetchone()
    return TrafficSnapshot.from_row(row) if row else None
