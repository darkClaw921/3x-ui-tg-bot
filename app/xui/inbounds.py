"""Operations over 3x-ui inbounds.

The 3x-ui panel exposes inbounds at:
- ``GET  /panel/api/inbounds/list``     — array of all inbounds.
- ``GET  /panel/api/inbounds/get/:id``  — single inbound by id.

The panel returns the ``settings`` and ``streamSettings`` fields as
**JSON-encoded strings** rather than nested objects. We unwrap them so the
rest of the codebase can treat an inbound as a normal Python ``dict``.
"""

from __future__ import annotations

import json
from typing import Any

from app.xui.client import XuiClient, XuiError


# Subfields that the panel returns as JSON-encoded strings. We decode them
# in-place. ``sniffing`` and ``allocate`` are not always present; the rest
# are part of every inbound payload.
_JSON_STRING_FIELDS = ("settings", "streamSettings", "sniffing", "allocate")


def _parse_inbound(raw: dict[str, Any]) -> dict[str, Any]:
    """Decode JSON-string subfields of an inbound payload to nested dicts.

    Non-destructive: the input ``raw`` is shallow-copied so callers that
    cache the original (e.g. in tests) are not affected. Missing or empty
    fields are tolerated.
    """
    parsed = dict(raw)
    for field in _JSON_STRING_FIELDS:
        value = parsed.get(field)
        if isinstance(value, str) and value:
            try:
                parsed[field] = json.loads(value)
            except ValueError:
                # Leave the raw string in place; downstream code can decide
                # what to do with malformed JSON instead of us silently
                # swallowing it.
                pass
    return parsed


async def list_inbounds(client: XuiClient) -> list[dict[str, Any]]:
    """Return all inbounds with ``settings``/``streamSettings`` already parsed.

    Wraps ``GET /panel/api/inbounds/list``. Raises :class:`XuiError` on
    panel-level failures (propagated from :meth:`XuiClient.request_json`).
    """
    obj = await client.request_json("GET", "/panel/api/inbounds/list")
    if obj is None:
        return []
    if not isinstance(obj, list):
        raise XuiError(f"list_inbounds: expected list, got {type(obj).__name__}")
    return [_parse_inbound(item) for item in obj if isinstance(item, dict)]


async def get_inbound(client: XuiClient, inbound_id: int) -> dict[str, Any]:
    """Return a single inbound by id, with nested JSON fields parsed.

    Wraps ``GET /panel/api/inbounds/get/:id``. Raises :class:`XuiError` if
    the inbound does not exist (panel returns ``success=false``) or the
    response shape is unexpected.
    """
    obj = await client.request_json("GET", f"/panel/api/inbounds/get/{inbound_id}")
    if not isinstance(obj, dict):
        raise XuiError(
            f"get_inbound({inbound_id}): expected object, got {type(obj).__name__}"
        )
    return _parse_inbound(obj)
