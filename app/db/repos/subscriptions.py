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
    """A row from the ``subscriptions`` table.

    ``is_trial`` flags a free-trial subscription (``True``) vs a regular/paid
    one (``False``). It is declared last with a default of ``False`` so any
    positional ``Subscription(...)`` constructors in tests that predate the
    column keep working unchanged.

    ``auto_renew`` flags a subscription enrolled in automatic renewal — either
    a native Telegram Star subscription (in which case ``tg_sub_charge_id`` is
    set to the recurring payment's ``telegram_payment_charge_id``) or a wallet
    fallback (``tg_sub_charge_id`` stays ``None`` and the scheduler
    auto-charges the user's Stars balance). Both fields are declared last with
    backwards-compatible defaults (``False`` / ``None``) so positional
    ``Subscription(...)`` constructors that predate the columns keep working.
    """

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
    is_trial: bool = False
    auto_renew: bool = False
    tg_sub_charge_id: str | None = None

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> Subscription:
        """Build a :class:`Subscription` from an :class:`aiosqlite.Row`.

        Tolerates rows selected without the ``is_trial`` / ``auto_renew`` /
        ``tg_sub_charge_id`` columns (defaulting to ``False`` / ``False`` /
        ``None``) so call sites that select a narrow column set still work.
        """
        keys = row.keys()
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
            is_trial=bool(row["is_trial"]) if "is_trial" in keys else False,
            auto_renew=bool(row["auto_renew"]) if "auto_renew" in keys else False,
            tg_sub_charge_id=(
                row["tg_sub_charge_id"] if "tg_sub_charge_id" in keys else None
            ),
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
    "xui_sub_id, expires_at, created_at, plan_id, status, is_trial, "
    "auto_renew, tg_sub_charge_id "
    "FROM subscriptions"
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
    is_trial: bool = False,
) -> Subscription:
    """Insert a new active subscription.

    ``xui_sub_id`` is the panel's ``subId`` used by the public
    subscription URL (``/sub/<sub_id>``). Defaults to the empty string so
    old call sites keep compiling; the user purchase flow always passes
    a non-empty value.

    ``is_trial`` marks the row as a free-trial subscription. When ``True`` the
    insert is subject to the partial-unique index ``idx_subscriptions_one_trial``
    (``UNIQUE(user_id) WHERE is_trial = 1``): a second trial for the same user
    raises :class:`aiosqlite.IntegrityError`. The service layer
    (:func:`app.services.subscriptions.activate_trial`) catches that and maps it
    to a "trial already used" outcome.
    """
    cursor = await conn.execute(
        "INSERT INTO subscriptions "
        "(user_id, xui_inbound_id, xui_client_uuid, xui_client_email, "
        " xui_sub_id, expires_at, plan_id, status, is_trial) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)",
        (
            user_id,
            xui_inbound_id,
            xui_client_uuid,
            xui_client_email,
            xui_sub_id,
            _to_iso(expires_at),
            plan_id,
            1 if is_trial else 0,
        ),
    )
    await conn.commit()
    new_id = cursor.lastrowid
    assert new_id is not None
    sub = await get(conn, new_id)
    assert sub is not None
    return sub


async def has_trial(conn: aiosqlite.Connection, user_id: int) -> bool:
    """Return ``True`` iff ``user_id`` already holds a trial subscription.

    Used to hide the «🎁 Пробный период» button once the user has claimed
    their trial (a UX guard) and as a cheap pre-check before
    :func:`app.services.subscriptions.activate_trial`. The hard guarantee that
    a user can hold at most one trial is the partial-unique index
    ``idx_subscriptions_one_trial`` — this helper is the fast, race-tolerant
    read in front of it.
    """
    cursor = await conn.execute(
        "SELECT 1 FROM subscriptions WHERE user_id = ? AND is_trial = 1 LIMIT 1",
        (user_id,),
    )
    row = await cursor.fetchone()
    return row is not None


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


async def list_active_for_user(
    conn: aiosqlite.Connection, user_id: int
) -> list[Subscription]:
    """Return all currently-active subscriptions for ``user_id``.

    Active means ``status='active'`` AND ``expires_at > now``. Ordered by
    ``expires_at`` descending (newest expiry first), so the freshest
    extension appears at the top of UI lists. Ties broken by ``id`` desc
    for determinism.

    Sibling of :func:`get_active_for_user`, which returns at most one
    subscription. This function exists to support users that hold
    multiple concurrent subscriptions (one per device/inbound) —
    introduced together with the explicit ``extend_sub_id`` argument in
    :func:`app.services.subscriptions.create_or_extend`.
    """
    now = _utcnow_iso()
    cursor = await conn.execute(
        f"{_SELECT} "
        "WHERE user_id = ? AND status = 'active' AND expires_at > ? "
        "ORDER BY expires_at DESC, id DESC",
        (user_id, now),
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


async def set_auto_renew(
    conn: aiosqlite.Connection,
    sub_id: int,
    value: bool,
    tg_sub_charge_id: str | None = None,
) -> None:
    """Toggle a subscription's ``auto_renew`` flag and (optionally) its charge id.

    Used by both auto-renewal mechanisms:

    * Native Telegram Star subscriptions — on the first recurring payment the
      handler calls ``set_auto_renew(sub_id, True, tg_sub_charge_id=<charge>)``
      so the recurring ``telegram_payment_charge_id`` is persisted (it is what
      :meth:`aiogram.Bot.edit_user_star_subscription` needs to cancel the
      subscription later). Cancelling calls
      ``set_auto_renew(sub_id, False)`` — ``tg_sub_charge_id`` is left as ``None``
      here (the column keeps its previous value unless explicitly overwritten).
    * Wallet fallback — the user enables ``auto_renew=1`` with no
      ``tg_sub_charge_id`` so :func:`list_auto_renew_due` picks the row up and
      the scheduler charges their Stars balance.

    When ``tg_sub_charge_id`` is ``None`` only the ``auto_renew`` column is
    written, so toggling the flag off never clobbers a previously-stored charge
    id (it may still be needed for an ``is_canceled=False`` re-enable).
    """
    if tg_sub_charge_id is None:
        await conn.execute(
            "UPDATE subscriptions SET auto_renew = ? WHERE id = ?",
            (1 if value else 0, sub_id),
        )
    else:
        await conn.execute(
            "UPDATE subscriptions SET auto_renew = ?, tg_sub_charge_id = ? "
            "WHERE id = ?",
            (1 if value else 0, tg_sub_charge_id, sub_id),
        )
    await conn.commit()


async def list_auto_renew_due(
    conn: aiosqlite.Connection,
    within_hours: int = 24,
) -> list[Subscription]:
    """Return active wallet-fallback subscriptions due for auto-renewal.

    Selects rows that are **all** of:

    * ``status='active'`` — only live subscriptions renew;
    * ``auto_renew=1`` — the user opted into automatic renewal;
    * ``tg_sub_charge_id IS NULL`` — they are **not** native Telegram Star
      subscriptions (Telegram bills those itself); only the wallet-fallback
      mechanism needs the scheduler to charge them;
    * ``expires_at <= now + within_hours`` — they expire within the lookahead
      window so the renewal lands before access lapses.

    Ordered by ``expires_at`` ascending so the most-urgent renewals run first.
    Used by :func:`app.scheduler.auto_renew_job`.
    """
    now_dt = datetime.now(UTC).replace(microsecond=0)
    cutoff_dt = now_dt + timedelta(hours=max(0, int(within_hours)))
    cursor = await conn.execute(
        f"{_SELECT} "
        "WHERE status = 'active' AND auto_renew = 1 "
        "AND tg_sub_charge_id IS NULL AND expires_at <= ? "
        "ORDER BY expires_at ASC, id ASC",
        (cutoff_dt.isoformat(sep=" "),),
    )
    rows = await cursor.fetchall()
    return [Subscription.from_row(r) for r in rows]


async def get_active_auto_renew_for(
    conn: aiosqlite.Connection,
    user_id: int,
    plan_id: int,
) -> Subscription | None:
    """Return the user's active native Star-subscription for ``plan_id``, or None.

    Finds the row that a *subsequent* recurring Telegram Star charge should
    extend: ``status='active'``, ``auto_renew=1`` and a non-NULL
    ``tg_sub_charge_id`` (the marker of a native Star subscription) for the
    given ``(user_id, plan_id)``. When several match (shouldn't happen — one
    native subscription per plan), the latest-expiring one wins.

    Used by :func:`app.handlers.user.buy.on_successful_payment` to locate the
    subscription a recurring charge belongs to.
    """
    cursor = await conn.execute(
        f"{_SELECT} "
        "WHERE user_id = ? AND plan_id = ? AND status = 'active' "
        "AND auto_renew = 1 AND tg_sub_charge_id IS NOT NULL "
        "ORDER BY expires_at DESC, id DESC LIMIT 1",
        (user_id, plan_id),
    )
    row = await cursor.fetchone()
    return Subscription.from_row(row) if row else None


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


NotificationKind = Literal["3d", "1d", "0d", "expired", "traffic80"]

# Allowed notification kinds — validated in code now that the DB column is
# free-text (the legacy ``CHECK`` constraint was dropped in Phase 4 so new kinds
# can be added without a destructive table rebuild). ``traffic80`` is the
# one-off "80% of traffic quota used" alert emitted by
# :func:`app.scheduler.traffic_snapshot_job`.
NOTIFICATION_KINDS: frozenset[str] = frozenset(
    {"3d", "1d", "0d", "expired", "traffic80"}
)


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

    ``kind`` is validated in code against :data:`NOTIFICATION_KINDS` (the DB
    column is intentionally free-text — see
    :func:`app.db.engine._relax_subscription_notifications_kind`). An unknown
    kind raises :class:`ValueError` so a typo surfaces immediately rather than
    silently persisting an un-dedupable notification.

    Implementation uses ``INSERT OR IGNORE`` against the
    ``UNIQUE(subscription_id, kind)`` constraint, so the check + insert is a
    single SQL statement (no TOCTOU window).
    """
    if kind not in NOTIFICATION_KINDS:
        raise ValueError(f"unknown notification kind: {kind!r}")
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
