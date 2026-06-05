"""Service layer for the admin-action audit trail.

A single thin entry point, :func:`log_action`, that records a privileged admin
mutation in the ``audit_log`` table. It is called from every admin handler that
changes state (plan / promo CRUD, user revoke / toggle_admin / grant_sub /
block, broadcast).

The function is **crash-safe by design**: an audit-log failure must never break
the admin action it is recording. Any exception (DB error, serialisation issue)
is logged and swallowed, and ``None`` is returned, so callers can fire-and-forget
``await log_action(...)`` without a try/except of their own.

``details`` accepts an arbitrary JSON-serialisable mapping which is serialised to
a compact JSON string for the ``details`` column; on a serialisation error it
falls back to ``str(details)`` so something is always recorded.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import aiosqlite
from loguru import logger

from app.db.repos import audit as audit_repo
from app.db.repos.audit import AuditEntry


def _serialise_details(details: Mapping[str, Any] | None) -> str | None:
    """Serialise a ``details`` mapping to a compact JSON string (or ``None``)."""
    if details is None:
        return None
    try:
        return json.dumps(details, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(details)


async def log_action(
    conn: aiosqlite.Connection,
    admin_id: int | None,
    action: str,
    target_type: str | None = None,
    target_id: int | None = None,
    details: Mapping[str, Any] | None = None,
) -> AuditEntry | None:
    """Record an admin action in ``audit_log`` (best-effort, never raises).

    Parameters
    ----------
    conn
        Open DB connection (caller-owned).
    admin_id
        The acting admin's ``users.id`` (``None`` when unknown).
    action
        Short dotted verb, e.g. ``'plan.create'`` / ``'user.block'``.
    target_type / target_id
        Identify the affected entity (both nullable for target-less actions
        such as a broadcast).
    details
        Optional JSON-serialisable mapping with extra context.

    Returns the created :class:`AuditEntry`, or ``None`` if logging failed (the
    failure is logged at WARNING — the caller's action proceeds regardless).
    """
    try:
        return await audit_repo.add(
            conn,
            admin_id=admin_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=_serialise_details(details),
        )
    except (aiosqlite.Error, Exception) as exc:  # noqa: BLE001 — never break the action
        logger.warning(
            "audit log_action failed (action={}, admin_id={}): {}",
            action,
            admin_id,
            exc,
        )
        return None


__all__ = ["log_action"]
