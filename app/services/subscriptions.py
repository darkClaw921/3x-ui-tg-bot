"""Single source of truth for creating / extending a user subscription.

Why a service layer? The bot owns two stateful systems that must remain
consistent:

* The local SQLite ``subscriptions`` table (drives the UI / scheduler).
* The 3x-ui panel's per-inbound client list (drives the actual VPN
  routing).

Mixing those two writes inside handlers quickly leads to drift (e.g. a DB
row created but no panel client because the xui call failed afterwards).
This module funnels every "give this user N more days of access"
operation through a single :func:`create_or_extend` so the order is
always:

1. xui first  — :func:`app.xui.clients.add_client` /
   :func:`app.xui.clients.update_client`.
2. DB after   — :func:`app.db.repos.subscriptions.create` /
   :func:`app.db.repos.subscriptions.extend`.

Order matters: a successful xui call followed by a failed DB write leaves
an "orphan" panel client that the admin will see and can clean up; the
reverse order would mean Stars were charged and no VPN access exists.

A second public entry point, :func:`activate_free_days`, mirrors the
no-payment flow for ``promo.type='free_days'``. :func:`revoke` provides
the inverse operation used by the admin panel and the expire job
(Phase 8).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import aiosqlite
from loguru import logger

from app.config import settings
from app.db.repos import subscriptions as subs_repo
from app.db.repos.plans import Plan
from app.db.repos.promos import Promo
from app.db.repos.subscriptions import Subscription
from app.db.repos.users import User
from app.xui import XuiClient
from app.xui.clients import (
    add_client,
    make_client_email,
    make_client_uuid,
    update_client,
)


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #


def _expiry_ms(expires_at: datetime) -> int:
    """Convert a UTC :class:`datetime` to milliseconds since epoch.

    3x-ui's client ``expiryTime`` is a UNIX timestamp in **milliseconds**
    (not seconds). 0 means "never".
    """
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return int(expires_at.timestamp() * 1000)


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 timestamp produced by the repo back into a datetime.

    Accepts both the ``" "``-separated form (default of
    :func:`datetime.isoformat` with ``sep=" "``) and the ``"T"``-separated
    form. Always returns a timezone-aware UTC datetime — naive strings
    (which SQLite's ``CURRENT_TIMESTAMP`` produces) are assumed UTC.
    """
    normalised = value.replace("T", " ", 1)
    try:
        dt = datetime.fromisoformat(normalised)
    except ValueError:
        # Fall back: drop microseconds / extra fractional digits if the
        # repo ever started producing them.
        dt = datetime.strptime(normalised[:19], "%Y-%m-%d %H:%M:%S")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _bonus_days_from_promo(promo: Promo | None) -> int:
    """Return the extra days a promo grants (0 unless ``type='free_days'``)."""
    if promo is None:
        return 0
    if promo.type == "free_days":
        return max(0, int(promo.value))
    return 0


def _make_sub_id() -> str:
    """Generate a fresh subscription id (delegates to xui.clients)."""
    # Defer to the canonical helper so the format stays in lockstep with
    # ``add_client``'s default.
    from app.xui.clients import _make_sub_id as _impl

    return _impl()


# ---------------------------------------------------------------------- #
# Public API
# ---------------------------------------------------------------------- #


async def create_or_extend(
    conn: aiosqlite.Connection,
    xui: XuiClient,
    user: User,
    plan: Plan,
    promo: Promo | None,
) -> Subscription:
    """Provision or extend a paid subscription for ``user``.

    Steps:

    1. Compute the delta in days: ``plan.days + bonus_days(promo)``.
    2. If the user has an active subscription, push its ``expires_at``
       forward by the delta, then call
       :func:`app.xui.clients.update_client` with the new
       ``expiryTime`` so the panel matches the DB. The existing xui
       client is reused — no new UUID/email is generated.
    3. Otherwise, allocate a fresh UUID + email + sub-id, call
       :func:`app.xui.clients.add_client` (xui-first), then insert the
       row into the local ``subscriptions`` table.

    Parameters
    ----------
    conn
        Open DB connection (caller-owned).
    xui
        Authenticated 3x-ui client.
    user
        Domain user (``users.id`` is used for the FK).
    plan
        The plan being purchased; ``plan.days`` drives the delta.
    promo
        Optional promo — only ``free_days`` types affect the delta here.
        Discount-type promos affect the Stars price (handled by
        :mod:`app.services.billing`) but not the duration.

    Returns
    -------
    Subscription
        The freshly-created or extended subscription record.

    Raises
    ------
    app.xui.XuiError
        Bubble up from the panel call — the caller (buy handler) is
        responsible for refunding / notifying.
    """
    delta_days = int(plan.days) + _bonus_days_from_promo(promo)
    return await _provision(
        conn=conn,
        xui=xui,
        user=user,
        delta_days=delta_days,
        plan_id=plan.id,
    )


async def activate_free_days(
    conn: aiosqlite.Connection,
    xui: XuiClient,
    user: User,
    promo: Promo,
) -> Subscription:
    """Grant ``promo.value`` free days without involving Telegram Stars.

    Used by the "Активировать промокод" entry point for ``free_days``
    promos. Validation (capacity, expiry, already-redeemed) is the
    caller's responsibility — see :func:`app.services.promos.validate`.

    The promo's :class:`Promo.type` must equal ``"free_days"`` — anything
    else is a programmer error and raises :class:`ValueError` because the
    other types only make sense in combination with a paid plan.
    """
    if promo.type != "free_days":
        raise ValueError(
            f"activate_free_days called with promo.type={promo.type!r}; "
            "only 'free_days' is supported"
        )
    delta_days = max(0, int(promo.value))
    return await _provision(
        conn=conn,
        xui=xui,
        user=user,
        delta_days=delta_days,
        plan_id=None,
    )


async def revoke(xui: XuiClient, sub: Subscription) -> None:
    """Disable a subscription's xui client and mark the DB row revoked.

    Used by admin tooling and the expire job. The xui call is best-effort
    soft-disable (``enable=False``); the local DB write happens in its
    own connection because the caller may not own one.
    """
    try:
        await update_client(
            xui,
            inbound_id=sub.xui_inbound_id,
            client_uuid=sub.xui_client_uuid,
            enable=False,
        )
    except Exception as exc:  # pragma: no cover — defensive logging
        logger.warning(
            "revoke({}): xui update_client failed: {}", sub.id, exc
        )

    from app.db.engine import get_conn

    async with get_conn() as conn:
        await subs_repo.set_status(conn, sub.id, "revoked")


# ---------------------------------------------------------------------- #
# Internals
# ---------------------------------------------------------------------- #


async def _provision(
    *,
    conn: aiosqlite.Connection,
    xui: XuiClient,
    user: User,
    delta_days: int,
    plan_id: int | None,
) -> Subscription:
    """Either extend the user's active subscription or create a new one.

    Common path shared by :func:`create_or_extend` and
    :func:`activate_free_days`. Always xui-first, DB-after.
    """
    delta = timedelta(days=max(0, delta_days))
    now = datetime.now(UTC).replace(microsecond=0)

    existing = await subs_repo.get_active_for_user(conn, user.id)

    if existing is not None:
        # ---- Extend in place ------------------------------------------------
        current_expiry = _parse_iso(existing.expires_at)
        # Guard: if for some reason the row says "active" but ``expires_at``
        # is in the past, anchor the extension to ``now`` so the user gets
        # the full delta rather than days in the past.
        if current_expiry < now:
            current_expiry = now
        new_expiry = current_expiry + delta

        await update_client(
            xui,
            inbound_id=existing.xui_inbound_id,
            client_uuid=existing.xui_client_uuid,
            expiryTime=_expiry_ms(new_expiry),
            enable=True,
        )
        await subs_repo.extend(conn, existing.id, new_expiry)
        logger.info(
            "sub-extend user={} sub={} +{}d → {}",
            user.tg_id,
            existing.id,
            delta_days,
            new_expiry.isoformat(),
        )
        refreshed = await subs_repo.get(conn, existing.id)
        assert refreshed is not None
        return refreshed

    # ---- Fresh provisioning -------------------------------------------------
    new_expiry = now + delta
    inbound_id = int(settings.XUI_INBOUND_ID)
    client_uuid = make_client_uuid()
    email = make_client_email(user.tg_id)
    sub_id = _make_sub_id()

    await add_client(
        xui,
        inbound_id=inbound_id,
        client_uuid=client_uuid,
        email=email,
        expiry_ts_ms=_expiry_ms(new_expiry),
        sub_id=sub_id,
    )

    sub = await subs_repo.create(
        conn,
        user_id=user.id,
        xui_inbound_id=inbound_id,
        xui_client_uuid=client_uuid,
        xui_client_email=email,
        expires_at=new_expiry,
        plan_id=plan_id,
        xui_sub_id=sub_id,
    )
    logger.info(
        "sub-create user={} sub={} uuid={} email={} expires={}",
        user.tg_id,
        sub.id,
        client_uuid,
        email,
        new_expiry.isoformat(),
    )
    return sub


__all__ = [
    "activate_free_days",
    "create_or_extend",
    "revoke",
]
