"""Builders for vless:// URIs, subscription URLs, and QR PNGs.

A vless URI as understood by xray-core / v2rayN / NekoBox::

    vless://<uuid>@<host>:<port>?<query>#<fragment>

The query parameters depend on the inbound's transport (``streamSettings``):

- ``type``     — transport (``tcp`` / ``ws`` / ``grpc`` / ``http`` / ``kcp`` / ``quic``)
- ``security`` — ``none`` / ``tls`` / ``reality`` / ``xtls``
- For ``tls``     — ``sni``, ``fp``, ``alpn``
- For ``reality`` — ``pbk``, ``fp``, ``sni``, ``sid``, ``spx``
- Transport-specific — ``path``, ``host``, ``serviceName``, ``mode``, ``headerType`` …
- ``flow`` — from the client object inside ``settings.clients[i]``

This module turns an already-parsed inbound dict (see :mod:`app.xui.inbounds`)
plus a client uuid into that URI.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any
from urllib.parse import quote, urlencode

import qrcode

from app.config import settings


# ---------------------------------------------------------------------- #
# Subscription URL
# ---------------------------------------------------------------------- #


def build_subscription_url(sub_id: str) -> str:
    """Return the public subscription URL for a client's ``subId``.

    Joins ``settings.XUI_SUB_BASE_URL`` with ``sub_id`` while collapsing
    duplicate slashes (the base URL may or may not have a trailing slash;
    callers should not have to care).
    """
    base = settings.XUI_SUB_BASE_URL.rstrip("/")
    return f"{base}/{sub_id.lstrip('/')}"


# ---------------------------------------------------------------------- #
# vless URI
# ---------------------------------------------------------------------- #


def _find_client(inbound: dict[str, Any], client_uuid: str) -> dict[str, Any]:
    """Locate a client record inside ``inbound.settings.clients`` by uuid."""
    settings_block = inbound.get("settings") or {}
    clients = settings_block.get("clients") if isinstance(settings_block, dict) else None
    if isinstance(clients, list):
        for c in clients:
            if isinstance(c, dict) and c.get("id") == client_uuid:
                return c
    return {}


def _stream_params(stream: dict[str, Any]) -> dict[str, str]:
    """Extract vless query params from ``streamSettings``.

    Only includes keys whose value is non-empty; xray clients ignore them
    anyway and the resulting URI looks cleaner.
    """
    network = (stream.get("network") or "tcp").lower()
    security = (stream.get("security") or "none").lower()

    params: dict[str, str] = {"type": network, "security": security}

    # --- transport-specific -----------------------------------------------
    if network == "tcp":
        tcp_settings = stream.get("tcpSettings") or {}
        header = tcp_settings.get("header") or {}
        header_type = header.get("type")
        if header_type:
            params["headerType"] = str(header_type)
        request = header.get("request") or {}
        path_list = request.get("path") if isinstance(request, dict) else None
        if isinstance(path_list, list) and path_list:
            params["path"] = str(path_list[0])
        headers = request.get("headers") if isinstance(request, dict) else None
        if isinstance(headers, dict):
            host_list = headers.get("Host") or headers.get("host")
            if isinstance(host_list, list) and host_list:
                params["host"] = ",".join(str(h) for h in host_list)
            elif isinstance(host_list, str) and host_list:
                params["host"] = host_list

    elif network == "ws":
        ws = stream.get("wsSettings") or {}
        if ws.get("path"):
            params["path"] = str(ws["path"])
        headers = ws.get("headers") or {}
        host = headers.get("Host") or headers.get("host") if isinstance(headers, dict) else None
        if host:
            params["host"] = str(host)

    elif network == "grpc":
        grpc = stream.get("grpcSettings") or {}
        if grpc.get("serviceName"):
            params["serviceName"] = str(grpc["serviceName"])
        if grpc.get("multiMode"):
            params["mode"] = "multi"

    elif network in ("http", "h2"):
        http = stream.get("httpSettings") or {}
        if http.get("path"):
            params["path"] = str(http["path"])
        host = http.get("host")
        if isinstance(host, list) and host:
            params["host"] = ",".join(str(h) for h in host)
        elif isinstance(host, str) and host:
            params["host"] = host

    elif network == "kcp":
        kcp = stream.get("kcpSettings") or {}
        header = kcp.get("header") or {}
        if header.get("type"):
            params["headerType"] = str(header["type"])
        if kcp.get("seed"):
            params["seed"] = str(kcp["seed"])

    elif network == "quic":
        quic = stream.get("quicSettings") or {}
        if quic.get("security"):
            params["quicSecurity"] = str(quic["security"])
        if quic.get("key"):
            params["key"] = str(quic["key"])
        header = quic.get("header") or {}
        if header.get("type"):
            params["headerType"] = str(header["type"])

    # --- security-specific ------------------------------------------------
    if security == "tls":
        tls = stream.get("tlsSettings") or {}
        if tls.get("serverName"):
            params["sni"] = str(tls["serverName"])
        alpn = tls.get("alpn")
        if isinstance(alpn, list) and alpn:
            params["alpn"] = ",".join(str(a) for a in alpn)
        settings_block = tls.get("settings") or {}
        fp = settings_block.get("fingerprint") if isinstance(settings_block, dict) else None
        if fp:
            params["fp"] = str(fp)

    elif security == "reality":
        reality = stream.get("realitySettings") or {}
        if reality.get("serverNames"):
            sni_list = reality["serverNames"]
            if isinstance(sni_list, list) and sni_list:
                params["sni"] = str(sni_list[0])
            elif isinstance(sni_list, str):
                params["sni"] = sni_list
        # Some panel builds expose serverName (singular) as a convenience.
        if not params.get("sni") and reality.get("serverName"):
            params["sni"] = str(reality["serverName"])
        sub = reality.get("settings") or {}
        if isinstance(sub, dict):
            if sub.get("publicKey"):
                params["pbk"] = str(sub["publicKey"])
            if sub.get("fingerprint"):
                params["fp"] = str(sub["fingerprint"])
            if sub.get("spiderX"):
                params["spx"] = str(sub["spiderX"])
        # ``shortIds`` lives at the top-level realitySettings in 3x-ui.
        sids = reality.get("shortIds")
        if isinstance(sids, list) and sids:
            params["sid"] = str(sids[0])
        elif isinstance(sids, str) and sids:
            params["sid"] = sids

    return {k: v for k, v in params.items() if v != ""}


def build_vless_link(inbound: dict[str, Any], client_uuid: str, email: str) -> str:
    """Build a ``vless://`` URI from a parsed inbound + a client uuid.

    Parameters
    ----------
    inbound
        Inbound payload as returned by :func:`app.xui.inbounds.get_inbound`
        (with ``settings`` / ``streamSettings`` already decoded).
    client_uuid
        Client UUID — used as both the userinfo of the URI and the lookup
        key in ``settings.clients``.
    email
        Email/label of the client. Used for the URI fragment (``#email``)
        so that xray-core clients can display a readable name.

    The host is taken from :data:`app.config.settings.XUI_SERVER_HOST`
    (not from the panel) because the panel often binds to ``0.0.0.0``
    while the public DNS name lives elsewhere.
    """
    port = int(inbound.get("port") or 0)
    stream = inbound.get("streamSettings") or {}
    if not isinstance(stream, dict):
        stream = {}

    params = _stream_params(stream)

    # ``flow`` comes from the client record, not the inbound.
    client_obj = _find_client(inbound, client_uuid)
    flow = client_obj.get("flow") or ""
    if flow:
        params["flow"] = str(flow)

    query = urlencode(params, safe=":/,")
    # urllib.parse.quote with safe='' percent-encodes the fragment so
    # display-name with spaces/cyrillic survives copy-paste between clients.
    fragment = quote(email, safe="")

    host = settings.XUI_SERVER_HOST
    return f"vless://{client_uuid}@{host}:{port}?{query}#{fragment}"


# ---------------------------------------------------------------------- #
# QR
# ---------------------------------------------------------------------- #


def make_qr_png(text: str) -> bytes:
    """Render ``text`` as a QR code and return raw PNG bytes.

    The bytes are ready to feed directly to ``aiogram``'s ``send_photo``
    (or to write to disk). Uses :func:`qrcode.make` with library defaults
    (auto-fit version, error-correction L, 10px box size).
    """
    image = qrcode.make(text)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
