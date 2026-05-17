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
    *,
    inbound_id: int,
    extend_sub_id: int | None = None,
) -> Subscription:
    """Provision a fresh subscription, or extend a specific existing one.

    Behaviour is now explicit and controlled by ``extend_sub_id``:

    * ``extend_sub_id is None`` (default) → **always** allocate a fresh
      UUID + email + sub-id, call :func:`app.xui.clients.add_client`
      (xui-first), then insert a brand-new row into
      ``subscriptions``. This holds even when the user already has one
      or more active subscriptions — the caller is responsible for
      deciding whether to create-new vs extend (the UI surfaces a
      "Продлить / Новая" choice screen).
    * ``extend_sub_id is int`` → load the subscription via
      :func:`app.db.repos.subscriptions.get`, verify it belongs to
      ``user`` and is ``status='active'``; push its ``expires_at``
      forward by the delta and call
      :func:`app.xui.clients.update_client` with the new
      ``expiryTime``. ``inbound_id`` is **ignored** on extend — the
      existing subscription's ``xui_inbound_id`` is reused (a mismatch
      is logged at WARNING).

    Parameters
    ----------
    conn
        Open DB connection (caller-owned).
    xui
        Authenticated 3x-ui client.
    user
        Domain user (``users.id`` is used for the FK / ownership check).
    plan
        The plan being purchased; ``plan.days`` drives the delta.
    promo
        Optional promo — only ``free_days`` types affect the delta here.
        Discount-type promos affect the Stars price (handled by
        :mod:`app.services.billing`) but not the duration.
    inbound_id
        3x-ui inbound where a fresh client must be provisioned. **Only
        consulted when creating a brand-new subscription** — ignored
        for extend (existing inbound is reused).
    extend_sub_id
        ``None`` → always create new. ``int`` → extend that specific
        subscription with ownership / status validation.

    Returns
    -------
    Subscription
        The freshly-created or extended subscription record.

    Raises
    ------
    ValueError
        If ``extend_sub_id`` is given but the subscription does not
        exist, belongs to another user, or is not in ``status='active'``.
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
        total_gb=int(plan.traffic_gb),
        inbound_id=int(inbound_id),
        extend_sub_id=extend_sub_id,
    )


async def activate_free_days(
    conn: aiosqlite.Connection,
    xui: XuiClient,
    user: User,
    promo: Promo,
    *,
    inbound_id: int,
    extend_sub_id: int | None = None,
) -> Subscription:
    """Grant ``promo.value`` free days without involving Telegram Stars.

    Used by the "Активировать промокод" entry point for ``free_days``
    promos. Validation (capacity, expiry, already-redeemed) is the
    caller's responsibility — see :func:`app.services.promos.validate`.

    The promo's :class:`Promo.type` must equal ``"free_days"`` — anything
    else is a programmer error and raises :class:`ValueError` because the
    other types only make sense in combination with a paid plan.

    ``inbound_id`` is the 3x-ui inbound the user picked from the promo
    flow; consulted only when creating a fresh subscription and ignored
    (with a WARNING log on mismatch) when extending an existing one.

    ``extend_sub_id`` mirrors :func:`create_or_extend`: ``None`` always
    creates a brand-new subscription; an ``int`` extends that specific
    one with ownership / status validation.
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
        total_gb=0,
        inbound_id=int(inbound_id),
        extend_sub_id=extend_sub_id,
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
    total_gb: int = 0,
    inbound_id: int,
    extend_sub_id: int | None,
) -> Subscription:
    """Create a fresh subscription, or extend a caller-specified one.

    Common path shared by :func:`create_or_extend` and
    :func:`activate_free_days`. Always xui-first, DB-after.

    Branch selection is **fully explicit** via ``extend_sub_id``:

    * ``extend_sub_id is None`` → fresh provisioning (new UUID + email
      + sub-id, :func:`app.xui.clients.add_client`,
      :func:`app.db.repos.subscriptions.create`). The presence of
      other active subscriptions for the same user is irrelevant — the
      caller decides whether to create-new or extend by passing
      ``extend_sub_id`` or not.
    * ``extend_sub_id is int`` → load the row with
      :func:`app.db.repos.subscriptions.get` and validate ownership
      (``sub.user_id == user.id``) plus ``status == 'active'``. On
      failure raise :class:`ValueError` (the caller treats this as
      "subscription not available"). On success, extend the existing
      xui client (no new UUID) and bump ``expires_at`` via
      :func:`app.db.repos.subscriptions.extend`.

    The ``total_gb`` argument is only applied when provisioning a fresh
    client — on extend we deliberately leave ``totalGB`` untouched in
    :func:`app.xui.clients.update_client` so the user's accumulated
    traffic quota / remainder is not reset when their subscription is
    renewed.

    ``inbound_id`` is honoured only when creating fresh. On extend it
    is intentionally ignored — the existing subscription's
    ``xui_inbound_id`` is reused so the panel keeps a single client per
    subscription — but a mismatch with the requested ``inbound_id`` is
    logged at WARNING so the discrepancy is visible in logs.
    """
    delta = timedelta(days=max(0, delta_days))
    now = datetime.now(UTC).replace(microsecond=0)

    if extend_sub_id is not None:
        # ---- Extend a caller-specified subscription -------------------------
        existing = await subs_repo.get(conn, int(extend_sub_id))
        if existing is None:
            raise ValueError(
                f"subscription {extend_sub_id} not available for extend"
            )
        if existing.user_id != user.id:
            raise ValueError(
                f"subscription {extend_sub_id} not available for extend"
            )
        if existing.status != "active":
            raise ValueError(
                f"subscription {extend_sub_id} not available for extend"
            )

        if int(existing.xui_inbound_id) != int(inbound_id):
            logger.warning(
                "sub-extend: requested inbound_id={} differs from existing "
                "subscription_id={} xui_inbound_id={} — reusing existing "
                "inbound (no re-provisioning across inbounds on extend).",
                inbound_id,
                existing.id,
                existing.xui_inbound_id,
            )
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
    inbound_id = int(inbound_id)
    client_uuid = make_client_uuid()
    email = make_client_email(user.tg_id, user.username)
    sub_id = _make_sub_id()

    await add_client(
        xui,
        inbound_id=inbound_id,
        client_uuid=client_uuid,
        email=email,
        expiry_ts_ms=_expiry_ms(new_expiry),
        total_gb=int(total_gb),
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
        "sub-create user={} sub={} uuid={} email={} sub_id={} expires={}",
        user.tg_id,
        sub.id,
        client_uuid,
        email,
        sub_id,
        new_expiry.isoformat(),
    )
    return sub


__all__ = [
    "activate_free_days",
    "create_or_extend",
    "revoke",
]
