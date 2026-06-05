"""Panel reachability probing and a cached health snapshot.

Two responsibilities live here:

* :func:`check_xui_health` — a single lightweight probe of the 3x-ui panel.
  It tries :func:`app.xui.inbounds.list_inbounds` under an explicit timeout and
  reports ``(ok, error)``. This is the primitive the scheduler's
  ``health_check_job`` calls every ~30 minutes.

* A tiny process-local snapshot (:func:`get_cached_status` /
  :func:`set_cached_status`) so user-facing keyboards can render a 🟢/🔴
  availability indicator next to locations *without* hitting the panel on every
  render. The scheduler updates the snapshot after each probe; the snapshot
  starts ``None`` ("unknown") until the first probe lands.

The probe is deliberately framework-agnostic (no ``aiogram`` import) so the
scheduler can compose it with the alerting / persistence layers.
"""

from __future__ import annotations

import asyncio

from loguru import logger

from app.db.repos.health import HealthState
from app.xui import XuiClient, XuiError
from app.xui.inbounds import list_inbounds

# How long a single health probe may take before we declare the panel down.
# The panel's own client has generous per-request read timeouts (30s); for a
# *health* probe we want a much tighter bound so a wedged panel surfaces fast
# and the job can't stall the scheduler.
_PROBE_TIMEOUT_SEC: float = 10.0


# Process-local cache of the last known panel state. ``None`` means "no probe
# has completed yet" and keyboards render an "unknown" / neutral indicator.
_cached_status: HealthState | None = None


def get_cached_status() -> HealthState | None:
    """Return the last probed panel state (``'up'`` / ``'down'`` / ``None``).

    ``None`` until the first :func:`check_xui_health` result is published via
    :func:`set_cached_status`. Cheap and synchronous so keyboards can call it
    inline while building a markup.
    """
    return _cached_status


def set_cached_status(status: HealthState | None) -> None:
    """Publish the latest panel state for keyboards to read.

    Called by the scheduler after each probe. ``None`` resets to "unknown".
    """
    global _cached_status
    _cached_status = status


async def check_xui_health(xui: XuiClient) -> tuple[bool, str | None]:
    """Probe the 3x-ui panel and return ``(ok, error)``.

    Performs a lightweight :func:`list_inbounds` call wrapped in
    :func:`asyncio.wait_for` so it can never hang longer than
    :data:`_PROBE_TIMEOUT_SEC`. Any failure — timeout, transport/TLS error
    (:class:`app.xui.XuiError`) or an unexpected exception — is caught and
    reported as ``(False, <reason>)`` rather than propagated, because the
    caller (the scheduler) must keep running regardless.

    Returns
    -------
    tuple[bool, str | None]
        ``(True, None)`` when the panel answered; ``(False, reason)`` with a
        short human-readable error string otherwise.
    """
    try:
        await asyncio.wait_for(list_inbounds(xui), timeout=_PROBE_TIMEOUT_SEC)
    except TimeoutError:
        msg = f"timeout after {_PROBE_TIMEOUT_SEC:.0f}s"
        logger.warning("check_xui_health: {}", msg)
        return False, msg
    except XuiError as exc:
        logger.warning("check_xui_health: panel error: {}", exc)
        return False, str(exc)
    except Exception as exc:  # noqa: BLE001 — health probe must never raise
        logger.warning("check_xui_health: unexpected error: {}", exc)
        return False, str(exc)
    return True, None


__all__ = [
    "check_xui_health",
    "get_cached_status",
    "set_cached_status",
]
