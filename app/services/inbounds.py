"""Available 3x-ui inbounds for user-/admin-facing flows.

The buy flow and the admin "Подключения" editor both need a short list of
inbounds the user can pick from — but the panel's
:func:`app.xui.inbounds.list_inbounds` endpoint is a few hundred bytes per
inbound and chatty enough that calling it on every keyboard render would
both hammer the panel and noticeably slow down the bot.

This module provides a small wrapper around that endpoint with:

* a project-level :class:`InboundOption` dataclass exposing only the
  fields the keyboards / handlers actually use
  (``id, remark, port, enabled``);
* a global in-memory TTL cache (30 seconds) so several concurrent flows
  share the same panel response;
* an :class:`asyncio.Lock` so the very first concurrent burst on a cold
  cache results in a single panel call, not N.

The cache key is global because the bot talks to exactly one panel
instance; if that ever changes the cache would need to be re-keyed on
something stable like the client's base URL.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from loguru import logger

from app.xui import XuiClient
from app.xui.inbounds import list_inbounds


# Cache TTL in seconds. Chosen to be short enough that admin edits to
# inbound state propagate quickly, long enough that paging through a buy
# keyboard does not refetch.
_CACHE_TTL_SEC: float = 30.0


@dataclass(slots=True, frozen=True)
class InboundOption:
    """Projection of a 3x-ui inbound surfaced to handlers and keyboards.

    Only the fields the bot needs to render a choice button and persist
    the selection. ``enabled`` mirrors the panel's ``enable`` flag; we
    expose it for completeness even though :func:`list_user_inbounds`
    filters disabled inbounds out — admin tooling may want to inspect the
    flag downstream.
    """

    id: int
    remark: str
    port: int
    enabled: bool


# Module-level cache. ``_cache`` holds the last list returned; ``_ts`` is
# the monotonic timestamp of that fetch (0.0 == cold cache). ``_lock``
# serialises refresh attempts so a thundering herd on a cold cache results
# in a single panel call.
_cache: list[InboundOption] | None = None
_ts: float = 0.0
_lock = asyncio.Lock()


def _is_fresh(now: float) -> bool:
    """Return True if the cache is populated and within the TTL."""
    return _cache is not None and (now - _ts) < _CACHE_TTL_SEC


def clear_cache() -> None:
    """Drop the cached inbounds list.

    Exposed for tests and for admin actions that mutate panel-side
    inbound state and need the next render to reflect the change
    immediately rather than waiting up to ``_CACHE_TTL_SEC`` seconds.
    """
    global _cache, _ts
    _cache = None
    _ts = 0.0


async def list_user_inbounds(xui: XuiClient) -> list[InboundOption]:
    """Return enabled inbounds from the panel, cached for 30 seconds.

    Behaviour:

    * Cache hit (within TTL) — returns the cached list without any
      network call.
    * Cache miss — acquires :data:`_lock`, double-checks freshness (in
      case another coroutine populated it while we were waiting), then
      calls :func:`app.xui.inbounds.list_inbounds` and stores the result.
    * Panel error — the exception propagates and the cache is *not*
      updated (a stale-but-valid cache is preferable to an empty one,
      but here we have nothing yet so callers must handle the error).

    Only inbounds with ``enable=True`` are kept; the rest are dropped at
    this layer so handlers do not need to filter again.

    Parameters
    ----------
    xui
        Authenticated :class:`app.xui.client.XuiClient` instance.

    Returns
    -------
    list[InboundOption]
        Frozen-dataclass projection of each enabled inbound.
    """
    global _cache, _ts

    now = time.monotonic()
    if _is_fresh(now):
        # mypy-friendly: _is_fresh guarantees _cache is not None.
        assert _cache is not None
        return _cache

    async with _lock:
        # Re-check after acquiring the lock — another coroutine may have
        # already refreshed the cache while we were queued.
        now = time.monotonic()
        if _is_fresh(now):
            assert _cache is not None
            return _cache

        raw = await list_inbounds(xui)
        options: list[InboundOption] = []
        for item in raw:
            # Defensive: the panel occasionally omits fields on malformed
            # inbounds. Skip those rather than blowing up the entire list.
            try:
                inbound_id = int(item["id"])
                enable = bool(item.get("enable", False))
            except (KeyError, TypeError, ValueError):
                logger.warning("list_user_inbounds: skipping malformed inbound: {}", item)
                continue
            if not enable:
                continue
            options.append(
                InboundOption(
                    id=inbound_id,
                    remark=str(item.get("remark") or ""),
                    port=int(item.get("port") or 0),
                    enabled=True,
                )
            )

        _cache = options
        _ts = now
        return options


__all__ = [
    "InboundOption",
    "clear_cache",
    "list_user_inbounds",
]
