"""Aggregated metrics for the admin "Статистика" screen.

This module is the single source of truth for the dashboard numbers the
admin sees — revenue, active subscriptions, expiring-soon list, top
promos and the total user count. Each function is a thin wrapper around
a single ``SELECT`` (or repo helper) so the heavy lifting stays in the
database; we never pull rows into Python just to aggregate them.

Why a service layer? Two reasons:

* The handler (``app.handlers.admin.stats``) shouldn't have to know
  which repo answers which question — it should just call
  :func:`revenue_stars`, :func:`active_subscriptions_count` etc.
* Periods are computed *once* here (UTC, seconds resolution) so callers
  never need to fiddle with timezone-aware datetimes.

All functions accept an :class:`aiosqlite.Connection` from the caller
(same DI pattern as the repos).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import aiosqlite

from app.db.repos import payments as payments_repo
from app.db.repos import subscriptions as subs_repo
from app.db.repos.promos import Promo
from app.db.repos.subscriptions import Subscription


# --------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------- #


def _utcnow() -> datetime:
    """Return current UTC time, seconds resolution, tz-aware."""
    return datetime.now(UTC).replace(microsecond=0)


# --------------------------------------------------------------------- #
# Revenue
# --------------------------------------------------------------------- #


async def revenue_stars(conn: aiosqlite.Connection, period: timedelta) -> int:
    """Return total Stars revenue (``status='paid'``) over the last ``period``.

    The window is ``[now-period, now]`` (inclusive on both ends). Pass
    a very large ``timedelta`` (e.g. ``timedelta(days=36500)``) for an
    "all-time" total — there's no separate codepath for it because the
    query is the same.

    Delegates to :func:`app.db.repos.payments.total_stars_period`.
    """
    end = _utcnow()
    start = end - period
    return await payments_repo.total_stars_period(conn, start, end)


async def total_stars_period(
    conn: aiosqlite.Connection,
    date_from: datetime | str,
    date_to: datetime | str,
) -> int:
    """Total Stars revenue between two explicit timestamps.

    Thin pass-through to :func:`app.db.repos.payments.total_stars_period`
    — exposed here so handlers can speak in service-level vocabulary
    without importing the repo module directly.
    """
    return await payments_repo.total_stars_period(conn, date_from, date_to)


# --------------------------------------------------------------------- #
# Subscriptions
# --------------------------------------------------------------------- #


async def active_subscriptions_count(conn: aiosqlite.Connection) -> int:
    """Return the number of currently-active subscriptions.

    Active means ``status='active'`` AND ``expires_at > now`` — same
    definition as :func:`app.db.repos.subscriptions.list_active`, but we
    count in SQL to avoid materialising the rows.
    """
    now = _utcnow().isoformat(sep=" ")
    cursor = await conn.execute(
        "SELECT COUNT(*) AS n FROM subscriptions "
        "WHERE status = 'active' AND expires_at > ?",
        (now,),
    )
    row = await cursor.fetchone()
    assert row is not None
    return int(row["n"])


async def expiring_in(
    conn: aiosqlite.Connection, days: int
) -> list[Subscription]:
    """Return active subscriptions expiring within ``days`` days from now.

    Thin wrapper around
    :func:`app.db.repos.subscriptions.list_expiring_in` so the handler
    can call ``stats.expiring_in(conn, 7)`` instead of reaching into the
    repo for one line.
    """
    return await subs_repo.list_expiring_in(conn, days)


async def expiring_in_days(
    conn: aiosqlite.Connection, days: int
) -> list[Subscription]:
    """Alias for :func:`expiring_in` — name matches the task spec.

    Kept as a separate symbol so the public service vocabulary lines up
    one-for-one with the task plan (``expiring_in_days(7)``) while
    callers can also use the shorter :func:`expiring_in`.
    """
    return await expiring_in(conn, days)


# --------------------------------------------------------------------- #
# Promos
# --------------------------------------------------------------------- #


async def top_promos(
    conn: aiosqlite.Connection, limit: int = 5
) -> list[Promo]:
    """Return the top ``limit`` promos sorted by ``used_count`` DESC.

    Includes deactivated / expired promos too — admins want the
    leaderboard regardless of current usability. Promos with
    ``used_count = 0`` are still included if there's room.
    """
    cursor = await conn.execute(
        "SELECT id, code, type, value, max_uses, used_count, "
        "expires_at, created_at, created_by "
        "FROM promos "
        "ORDER BY used_count DESC, id DESC "
        "LIMIT ?",
        (int(limit),),
    )
    rows = await cursor.fetchall()
    return [Promo.from_row(r) for r in rows]


# --------------------------------------------------------------------- #
# Users / Payments
# --------------------------------------------------------------------- #


async def users_count(conn: aiosqlite.Connection) -> int:
    """Return the total number of users registered in the bot."""
    cursor = await conn.execute("SELECT COUNT(*) AS n FROM users")
    row = await cursor.fetchone()
    assert row is not None
    return int(row["n"])


async def users_count_total(conn: aiosqlite.Connection) -> int:
    """Alias for :func:`users_count` — matches the task-spec vocabulary."""
    return await users_count(conn)


async def payments_count_period(
    conn: aiosqlite.Connection,
    date_from: datetime | str,
    date_to: datetime | str,
) -> int:
    """Return the count of ``status='paid'`` payments in ``[date_from, date_to]``.

    Both bounds are inclusive. Accepts ISO-8601 strings or
    :class:`datetime.datetime` (converted to UTC ISO-8601 via the same
    helper the repo uses).
    """
    start_iso = _iso(date_from)
    end_iso = _iso(date_to)
    cursor = await conn.execute(
        "SELECT COUNT(*) AS n FROM payments "
        "WHERE status = 'paid' AND created_at >= ? AND created_at <= ?",
        (start_iso, end_iso),
    )
    row = await cursor.fetchone()
    assert row is not None
    return int(row["n"])


def _iso(value: datetime | str) -> str:
    """Normalize ``value`` to an ISO-8601 string in UTC (seconds resolution)."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        else:
            value = value.astimezone(UTC)
        return value.replace(microsecond=0).isoformat(sep=" ")
    return value


__all__ = [
    "active_subscriptions_count",
    "expiring_in",
    "expiring_in_days",
    "payments_count_period",
    "revenue_stars",
    "top_promos",
    "total_stars_period",
    "users_count",
    "users_count_total",
]
