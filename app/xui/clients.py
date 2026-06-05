"""Operations over clients in the 3x-ui panel (new ``/panel/api/clients/*`` API).

The React-rewrite major version of 3x-ui replaced the old inbound-scoped
client endpoints (``/panel/api/inbounds/addClient`` & friends, which keyed
by inbound id + client UUID and wrapped the payload in a JSON-encoded
``settings`` string) with a flat, **email-keyed** client resource:

- ``POST /panel/api/clients/add``            — body ``{"client": {...}, "inboundIds": [id]}``
- ``GET  /panel/api/clients/get/:email``     — body ``{"client": {...}, "inboundIds": [...]}``
- ``POST /panel/api/clients/update/:email``  — body is the flat client object (full replace)
- ``POST /panel/api/clients/del/:email``     — optional ``?keepTraffic=1``
- ``GET  /panel/api/clients/list/paged?search=:email`` — items carry live ``traffic``

Two consequences shape this module:

* **Clients are addressed by email**, not by UUID. ``update_client`` /
  ``del_client`` / ``get_client_traffics`` all take an ``email``.
* **``update`` is a full replace** that requires the ``email`` field and
  rejects the numeric internal ``id``. So :func:`update_client` does a
  read-merge-write: fetch the current client, overlay the changed fields,
  and post the whole object back — this preserves ``totalGB`` / ``subId`` /
  ``uuid`` etc. that the caller did not touch (critical so revoking or
  extending a sub never resets the user's quota).

The envelope (``{success, msg, obj}``) and CSRF handling are unchanged from
:mod:`app.xui.client`.
"""

from __future__ import annotations

import re
import secrets
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from loguru import logger

from app.xui.client import XuiClient, XuiError


# ---------------------------------------------------------------------- #
# ID / email helpers
# ---------------------------------------------------------------------- #


def make_client_uuid() -> str:
    """Generate a fresh random UUID4 for a vless client id."""
    return str(uuid4())


def make_client_email(tg_id: int, username: str | None = None) -> str:
    """Generate a unique-ish client label for the panel.

    3x-ui requires the ``email`` field to be unique across an inbound.
    We embed the Telegram id for traceability and append a short random
    suffix so re-subscribing a user (after a delete) does not collide
    with stale traffic snapshots.

    When ``username`` is provided, it is normalised (lowercased; chars
    outside ``[A-Za-z0-9_]`` collapsed to ``_``; trimmed; capped at 32)
    and prepended for human-readable identification in the panel. If
    the resulting normalised slug is empty, the function falls back to
    the legacy ``tg_<id>_<hex>`` shape.
    """
    suffix = secrets.token_hex(3)
    if username:
        safe = re.sub(r"[^A-Za-z0-9_]", "_", username).strip("_").lower()[:32]
        if safe:
            return f"{safe}_tg_{tg_id}_{suffix}"
    return f"tg_{tg_id}_{suffix}"


def _make_sub_id() -> str:
    """Generate a random subscription id (16 hex chars)."""
    return secrets.token_hex(8)


def _q(value: str) -> str:
    """URL-encode a path/query segment (mirrors the panel's encodeURIComponent)."""
    return quote(str(value), safe="")


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
    """Provision a new client and attach it to ``inbound_id``.

    Parameters mirror the panel's client schema:

    - ``expiry_ts_ms`` — absolute UNIX timestamp in **milliseconds** (not
      seconds). Use 0 for "never".
    - ``total_gb`` — traffic quota in GiB; 0 means unlimited.
    - ``sub_id`` — subscription id used by the panel's ``/sub/<sub_id>``
      endpoint. A 16-hex random value is generated when ``None``.
    - ``tg_id`` — coerced to ``int`` (the new create endpoint wants a
      numeric ``tgId``); a non-numeric value degrades to ``0``.

    Wire shape::

        POST /panel/api/clients/add
        {"client": {email, uuid, subId, flow, totalGB, ...}, "inboundIds": [id]}

    Returns the panel's ``obj`` (currently ``null`` on success) normalised
    to a dict so callers can rely on ``id`` / ``email`` / ``subId`` keys.
    """
    if sub_id is None:
        sub_id = _make_sub_id()

    body = {
        "client": {
            "email": email,
            "uuid": client_uuid,
            "subId": sub_id,
            "flow": flow,
            "totalGB": int(total_gb),
            "limitIp": int(limit_ip),
            "tgId": _coerce_tg_id(tg_id),
            "enable": bool(enable),
            "reset": int(reset),
            "expiryTime": int(expiry_ts_ms),
            "comment": "",
        },
        "inboundIds": [int(inbound_id)],
    }

    obj = await client.request_json("POST", "/panel/api/clients/add", json=body)
    logger.info("xui: clients/add inbound={} email={} uuid={}", inbound_id, email, client_uuid)
    # ``obj`` is ``null`` on the new panel — normalise to a dict so callers
    # keep getting the ids they generated.
    return obj if isinstance(obj, dict) else {"id": client_uuid, "email": email, "subId": sub_id}


def _coerce_tg_id(tg_id: int | str) -> int:
    """Best-effort coercion of ``tg_id`` to the numeric ``tgId`` the API wants."""
    if tg_id in ("", None):
        return 0
    try:
        return int(tg_id)
    except (TypeError, ValueError):
        return 0


# Fields the panel's client object exposes that we are willing to round-trip
# on an update. The numeric internal ``id`` is deliberately excluded — the
# update endpoint expects ``id`` to be a string and rejects the row's numeric
# primary key, so we strip it.
_CLIENT_FIELDS: frozenset[str] = frozenset(
    {
        "email",
        "uuid",
        "subId",
        "flow",
        "security",
        "password",
        "auth",
        "totalGB",
        "limitIp",
        "tgId",
        "enable",
        "reset",
        "expiryTime",
        "comment",
        "group",
    }
)

# Subset of fields callers may override on an update. Kept tight so a typo'd
# kwarg raises instead of silently being sent (or wiping a value).
_UPDATABLE_CLIENT_FIELDS: frozenset[str] = frozenset(
    {
        "email",
        "uuid",
        "subId",
        "flow",
        "totalGB",
        "limitIp",
        "tgId",
        "enable",
        "reset",
        "expiryTime",
        "comment",
    }
)


async def get_client(client: XuiClient, email: str) -> dict[str, Any]:
    """Return the panel's client record for ``email`` (or ``{}`` if absent).

    Wraps ``GET /panel/api/clients/get/:email``. The panel answers
    ``success=false`` with a "record not found" message for a missing
    client — that is surfaced here as an empty dict rather than an error,
    so callers can branch on truthiness.
    """
    try:
        obj = await client.request_json("GET", f"/panel/api/clients/get/{_q(email)}")
    except XuiError as exc:
        if "not found" in str(exc).lower():
            return {}
        raise
    if not isinstance(obj, dict):
        return {}
    inner = obj.get("client")
    return inner if isinstance(inner, dict) else {}


async def update_client(
    client: XuiClient,
    email: str,
    **fields: Any,
) -> dict[str, Any]:
    """Update fields of an existing client, identified by ``email``.

    The new panel's update is a **full replace**: it requires the ``email``
    field and overwrites the whole client. To avoid wiping values the caller
    did not touch (e.g. ``totalGB`` on a renewal), this does a
    read-merge-write — fetch the current client, overlay ``fields``, and
    post the merged object back.

    Unknown override keys raise :class:`ValueError`. Raises
    :class:`XuiError` if the client does not exist.
    """
    unknown = set(fields).difference(_UPDATABLE_CLIENT_FIELDS)
    if unknown:
        raise ValueError(f"update_client: unsupported fields {sorted(unknown)!r}")

    current = await get_client(client, email)
    if not current:
        raise XuiError(f"update_client: client {email!r} not found")

    payload: dict[str, Any] = {
        k: v for k, v in current.items() if k in _CLIENT_FIELDS
    }
    payload.update(fields)
    # ``email`` is mandatory and must match the URL — keep the caller's value.
    payload["email"] = email
    _coerce_numeric_fields(payload)

    obj = await client.request_json(
        "POST",
        f"/panel/api/clients/update/{_q(email)}",
        json=payload,
    )
    logger.info("xui: clients/update email={} fields={}", email, sorted(fields))
    return obj if isinstance(obj, dict) else {"email": email}


def _coerce_numeric_fields(payload: dict[str, Any]) -> None:
    """Coerce known numeric / bool fields in-place so the panel accepts them."""
    for key in ("expiryTime", "totalGB", "limitIp", "reset"):
        if key in payload and payload[key] is not None:
            payload[key] = int(payload[key])
    if "enable" in payload:
        payload["enable"] = bool(payload["enable"])
    if "tgId" in payload and payload["tgId"] is not None:
        payload["tgId"] = _coerce_tg_id(payload["tgId"])


async def del_client(
    client: XuiClient,
    email: str,
    *,
    keep_traffic: bool = False,
) -> None:
    """Delete a client identified by ``email``.

    Wraps ``POST /panel/api/clients/del/:email`` (``?keepTraffic=1`` when
    ``keep_traffic`` is set). Soft-fails when the panel reports the client
    is absent — the delete is idempotent from the caller's point of view
    (re-running an expire job must not crash because someone already
    cleaned up). Any other panel error still propagates as :class:`XuiError`.
    """
    path = f"/panel/api/clients/del/{_q(email)}"
    if keep_traffic:
        path += "?keepTraffic=1"
    try:
        await client.request_json("POST", path)
    except XuiError as exc:
        msg = str(exc).lower()
        if "not exist" in msg or "not found" in msg or "no such" in msg:
            logger.info("xui: clients/del noop email={} (already absent)", email)
            return
        raise
    logger.info("xui: clients/del email={}", email)


async def get_client_traffics(
    client: XuiClient,
    email: str,
) -> dict[str, Any]:
    """Return live traffic counters for the client labelled ``email``.

    The dedicated ``getClientTraffics`` endpoint was removed; live counters
    now ride along the paged client list. We query
    ``GET /panel/api/clients/list/paged?search=:email`` and return the
    matching item's ``traffic`` object, shaped like::

        {"up": int, "down": int, "total": int, "expiryTime": int,
         "enable": bool, "email": str, "inboundId": int, "lastOnline": int}

    Returns an empty dict if the client is not found (callers treat that as
    "no data yet"). Raises :class:`XuiError` only on an unexpected envelope
    shape.
    """
    obj = await client.request_json(
        "GET",
        f"/panel/api/clients/list/paged?page=1&pageSize=1&search={_q(email)}",
    )
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise XuiError(
            f"get_client_traffics({email}): expected object, got {type(obj).__name__}"
        )
    items = obj.get("items")
    if not isinstance(items, list) or not items:
        return {}
    match = next(
        (it for it in items if isinstance(it, dict) and it.get("email") == email),
        None,
    )
    # A search scoped to one email that returns a single row is unambiguous —
    # accept it even if the label differs by trivial normalisation.
    if match is None and len(items) == 1 and isinstance(items[0], dict):
        match = items[0]
    if match is None:
        return {}
    traffic = match.get("traffic")
    return traffic if isinstance(traffic, dict) else match
