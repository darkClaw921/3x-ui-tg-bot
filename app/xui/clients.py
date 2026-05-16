"""Operations over clients of a 3x-ui inbound.

The 3x-ui panel expects the ``settings`` payload for ``addClient`` /
``updateClient`` to be a **JSON-encoded string** sitting inside another
JSON object. That is, the wire shape is::

    {
      "id": <inbound_id>,
      "settings": "{\\"clients\\":[{\\"id\\":..., \\"email\\":..., ...}]}"
    }

This module hides that quirk: callers pass plain Python kwargs.

Endpoints used:
- ``POST /panel/api/inbounds/addClient``
- ``POST /panel/api/inbounds/updateClient/:client_uuid``
- ``POST /panel/api/inbounds/:inbound_id/delClient/:client_uuid``
- ``GET  /panel/api/inbounds/getClientTraffics/:email``
"""

from __future__ import annotations

import json
import secrets
from typing import Any
from uuid import uuid4

from loguru import logger

from app.xui.client import XuiClient, XuiError


# ---------------------------------------------------------------------- #
# ID / email helpers
# ---------------------------------------------------------------------- #


def make_client_uuid() -> str:
    """Generate a fresh random UUID4 for a vless client id."""
    return str(uuid4())


def make_client_email(tg_id: int) -> str:
    """Generate a unique-ish client label for the panel.

    3x-ui requires the ``email`` field to be unique across an inbound.
    We embed the Telegram id for traceability and append a short random
    suffix so re-subscribing a user (after a delete) does not collide
    with stale traffic snapshots.
    """
    return f"tg_{tg_id}_{secrets.token_hex(3)}"


def _make_sub_id() -> str:
    """Generate a random subscription id (16 hex chars)."""
    return secrets.token_hex(8)


# ---------------------------------------------------------------------- #
# CRUD
# ---------------------------------------------------------------------- #


async def add_client(
    client: XuiClient,
    inbound_id: int,
    client_uuid: str,
    email: str,
    expiry_ts_ms: int,
    total_gb: int = 0,
    sub_id: str | None = None,
    flow: str = "",
    enable: bool = True,
    limit_ip: int = 0,
    tg_id: int | str = "",
    reset: int = 0,
) -> dict[str, Any]:
    """Provision a new client inside the given inbound.

    Parameters mirror the 3x-ui client schema:

    - ``expiry_ts_ms`` — absolute UNIX timestamp in **milliseconds** (not
      seconds). Use 0 for "never".
    - ``total_gb`` — traffic quota in GiB; 0 means unlimited.
    - ``sub_id`` — subscription id used by the panel's ``/sub/<sub_id>``
      endpoint. A 16-hex random value is generated when ``None``.
    - ``flow`` — empty for vless+reality with xtls-rprx-vision off, or
      ``"xtls-rprx-vision"`` otherwise. Caller decides.

    Returns the panel's ``obj`` field (typically the new client record).
    """
    if sub_id is None:
        sub_id = _make_sub_id()

    client_payload = {
        "id": client_uuid,
        "email": email,
        "expiryTime": int(expiry_ts_ms),
        "totalGB": int(total_gb),
        "enable": bool(enable),
        "subId": sub_id,
        "flow": flow,
        "limitIp": int(limit_ip),
        "tgId": tg_id,
        "reset": int(reset),
    }
    body = {
        "id": int(inbound_id),
        # 3x-ui requires the settings to be a JSON-encoded string, not a
        # nested object — this is the single most common source of
        # "panel says success=false" errors.
        "settings": json.dumps({"clients": [client_payload]}),
    }

    obj = await client.request_json(
        "POST",
        "/panel/api/inbounds/addClient",
        json=body,
    )
    logger.info("xui: addClient inbound={} email={} uuid={}", inbound_id, email, client_uuid)
    # ``obj`` may be the created client, ``None``, or an empty dict depending
    # on panel build — normalise to a dict for callers.
    return obj if isinstance(obj, dict) else {"id": client_uuid, "email": email, "subId": sub_id}


# Subset of fields ``updateClient`` accepts. We whitelist to catch typos and
# avoid sending unsupported keys that may cause the panel to wipe values.
_UPDATABLE_CLIENT_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "email",
        "expiryTime",
        "totalGB",
        "enable",
        "flow",
        "subId",
        "limitIp",
        "tgId",
        "reset",
    }
)


async def update_client(
    client: XuiClient,
    inbound_id: int,
    client_uuid: str,
    **fields: Any,
) -> dict[str, Any]:
    """Update fields of an existing client in-place.

    The panel applies fields **partially** — missing keys retain their
    previous value. We still require at least one ``id`` field because the
    panel uses the request body's ``id`` (UUID) to identify the row;
    when not provided we default it to ``client_uuid``.

    Unknown keys raise :class:`ValueError`.
    """
    unknown = set(fields).difference(_UPDATABLE_CLIENT_FIELDS)
    if unknown:
        raise ValueError(f"update_client: unsupported fields {sorted(unknown)!r}")

    payload = dict(fields)
    payload.setdefault("id", client_uuid)
    # Coerce known numeric / bool types so callers can pass naturals.
    if "expiryTime" in payload:
        payload["expiryTime"] = int(payload["expiryTime"])
    if "totalGB" in payload:
        payload["totalGB"] = int(payload["totalGB"])
    if "enable" in payload:
        payload["enable"] = bool(payload["enable"])
    if "limitIp" in payload:
        payload["limitIp"] = int(payload["limitIp"])
    if "reset" in payload:
        payload["reset"] = int(payload["reset"])

    body = {
        "id": int(inbound_id),
        "settings": json.dumps({"clients": [payload]}),
    }
    obj = await client.request_json(
        "POST",
        f"/panel/api/inbounds/updateClient/{client_uuid}",
        json=body,
    )
    logger.info("xui: updateClient inbound={} uuid={} fields={}", inbound_id, client_uuid, list(fields))
    return obj if isinstance(obj, dict) else {"id": client_uuid}


async def del_client(
    client: XuiClient,
    inbound_id: int,
    client_uuid: str,
) -> None:
    """Delete a client from an inbound.

    Soft-fails when the panel reports the client does not exist — the
    delete is idempotent from the caller's point of view (re-running an
    expire job should not crash because someone already cleaned up).
    Any other panel error still propagates as :class:`XuiError`.
    """
    try:
        await client.request_json(
            "POST",
            f"/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}",
        )
    except XuiError as exc:
        msg = str(exc).lower()
        if "not exist" in msg or "not found" in msg or "no such" in msg:
            logger.info(
                "xui: delClient noop inbound={} uuid={} (already absent)",
                inbound_id,
                client_uuid,
            )
            return
        raise
    logger.info("xui: delClient inbound={} uuid={}", inbound_id, client_uuid)


async def get_client_traffics(
    client: XuiClient,
    email: str,
) -> dict[str, Any]:
    """Return traffic counters for a client identified by its email label.

    Returns a dict shaped like::

        {
          "id": int,
          "inboundId": int,
          "enable": bool,
          "email": str,
          "up": int, "down": int, "total": int,
          "expiryTime": int  # ms
        }

    Raises :class:`XuiError` if the panel returns ``success=false``.
    Returns an empty dict if the client is not found (panel returns
    ``success=true`` with ``obj=null``).
    """
    obj = await client.request_json(
        "GET",
        f"/panel/api/inbounds/getClientTraffics/{email}",
    )
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise XuiError(
            f"get_client_traffics({email}): expected object, got {type(obj).__name__}"
        )
    return obj
