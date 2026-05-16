"""Tests for :mod:`app.xui.links` — subscription URL, vless URI, QR PNG."""

from __future__ import annotations

import pytest

from app.xui.links import build_subscription_url, build_vless_link, make_qr_png


def test_make_qr_png_returns_png(monkey_settings):
    data = make_qr_png("hello")
    # PNG magic header.
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(data) > 100


def test_make_qr_png_long_payload():
    """A long payload still encodes successfully."""
    payload = "vless://" + "x" * 2000
    data = make_qr_png(payload)
    assert data.startswith(b"\x89PNG")


def test_build_subscription_url_normalises_slashes(monkey_settings):
    monkey_settings(XUI_SUB_BASE_URL="https://host/sub/")
    assert build_subscription_url("abc") == "https://host/sub/abc"
    assert build_subscription_url("/abc") == "https://host/sub/abc"


def test_build_subscription_url_no_trailing(monkey_settings):
    monkey_settings(XUI_SUB_BASE_URL="https://host/sub")
    assert build_subscription_url("abc") == "https://host/sub/abc"


def _inbound(stream=None, port=8443, clients=None, network="tcp", security="reality"):
    """Build a parsed inbound dict for tests."""
    if stream is None:
        stream = {"network": network, "security": security}
    settings_block = {"clients": clients or []}
    return {
        "port": port,
        "streamSettings": stream,
        "settings": settings_block,
    }


def test_build_vless_link_tcp_reality(monkey_settings):
    monkey_settings(XUI_SERVER_HOST="example.com")
    stream = {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
            "serverNames": ["www.cloudflare.com"],
            "settings": {"publicKey": "PK", "fingerprint": "chrome", "spiderX": "/"},
            "shortIds": ["abcd"],
        },
    }
    clients = [{"id": "uuid-1", "flow": "xtls-rprx-vision"}]
    inb = _inbound(stream=stream, clients=clients)
    uri = build_vless_link(inb, "uuid-1", "tg_1")
    assert uri.startswith("vless://uuid-1@example.com:8443?")
    assert "type=tcp" in uri
    assert "security=reality" in uri
    assert "pbk=PK" in uri
    assert "fp=chrome" in uri
    assert "spx=/" in uri
    assert "sid=abcd" in uri
    assert "flow=xtls-rprx-vision" in uri
    assert uri.endswith("#tg_1")


def test_build_vless_link_ws_tls(monkey_settings):
    monkey_settings(XUI_SERVER_HOST="vpn.test")
    stream = {
        "network": "ws",
        "security": "tls",
        "wsSettings": {"path": "/ws", "headers": {"Host": "example.com"}},
        "tlsSettings": {
            "serverName": "example.com",
            "alpn": ["h2", "http/1.1"],
            "settings": {"fingerprint": "chrome"},
        },
    }
    inb = _inbound(stream=stream)
    uri = build_vless_link(inb, "uu", "name")
    assert "type=ws" in uri
    assert "security=tls" in uri
    assert "path=/ws" in uri
    assert "host=example.com" in uri
    assert "sni=example.com" in uri
    assert "alpn=h2,http/1.1" in uri or "alpn=h2%2Chttp" in uri
    assert "fp=chrome" in uri


def test_build_vless_link_grpc(monkey_settings):
    stream = {
        "network": "grpc",
        "security": "none",
        "grpcSettings": {"serviceName": "GunService", "multiMode": True},
    }
    inb = _inbound(stream=stream)
    uri = build_vless_link(inb, "u", "e")
    assert "type=grpc" in uri
    assert "serviceName=GunService" in uri
    assert "mode=multi" in uri


def test_build_vless_link_http(monkey_settings):
    stream = {
        "network": "http",
        "security": "none",
        "httpSettings": {"path": "/api", "host": ["a", "b"]},
    }
    inb = _inbound(stream=stream)
    uri = build_vless_link(inb, "u", "e")
    assert "type=http" in uri
    assert "path=/api" in uri
    assert "host=a,b" in uri


def test_build_vless_link_http_host_str(monkey_settings):
    stream = {
        "network": "http",
        "security": "none",
        "httpSettings": {"path": "/api", "host": "single"},
    }
    inb = _inbound(stream=stream)
    uri = build_vless_link(inb, "u", "e")
    assert "host=single" in uri


def test_build_vless_link_kcp(monkey_settings):
    stream = {
        "network": "kcp",
        "security": "none",
        "kcpSettings": {"header": {"type": "srtp"}, "seed": "S"},
    }
    inb = _inbound(stream=stream)
    uri = build_vless_link(inb, "u", "e")
    assert "type=kcp" in uri
    assert "headerType=srtp" in uri
    assert "seed=S" in uri


def test_build_vless_link_quic(monkey_settings):
    stream = {
        "network": "quic",
        "security": "none",
        "quicSettings": {"security": "aes-128-gcm", "key": "kkk", "header": {"type": "none"}},
    }
    inb = _inbound(stream=stream)
    uri = build_vless_link(inb, "u", "e")
    assert "type=quic" in uri
    assert "quicSecurity=aes-128-gcm" in uri
    assert "key=kkk" in uri


def test_build_vless_link_no_security(monkey_settings):
    """Plain TCP without security still produces a vless URI."""
    stream = {"network": "tcp", "security": "none"}
    inb = _inbound(stream=stream)
    uri = build_vless_link(inb, "u", "name")
    assert uri.startswith("vless://u@")
    assert "security=none" in uri


def test_build_vless_link_no_stream_settings(monkey_settings):
    """An inbound missing streamSettings degrades gracefully."""
    inb = {"port": 443, "settings": {}}
    uri = build_vless_link(inb, "u", "x")
    assert uri.startswith("vless://u@")


def test_build_vless_link_bad_stream_settings_type(monkey_settings):
    """If streamSettings is not a dict the helper falls back to defaults."""
    inb = {"port": 443, "streamSettings": "broken-string", "settings": {}}
    uri = build_vless_link(inb, "u", "x")
    assert uri.startswith("vless://u@")
    assert "type=tcp" in uri


def test_build_vless_link_tcp_with_header_path_host(monkey_settings):
    stream = {
        "network": "tcp",
        "security": "none",
        "tcpSettings": {
            "header": {
                "type": "http",
                "request": {
                    "path": ["/p1"],
                    "headers": {"Host": ["one", "two"]},
                },
            }
        },
    }
    inb = _inbound(stream=stream)
    uri = build_vless_link(inb, "u", "x")
    assert "headerType=http" in uri
    assert "path=/p1" in uri
    assert "host=one,two" in uri


def test_build_vless_link_tcp_with_string_host(monkey_settings):
    stream = {
        "network": "tcp",
        "security": "none",
        "tcpSettings": {
            "header": {
                "type": "http",
                "request": {"headers": {"Host": "single.com"}},
            }
        },
    }
    inb = _inbound(stream=stream)
    uri = build_vless_link(inb, "u", "x")
    assert "host=single.com" in uri


def test_build_vless_link_reality_with_serverName_singular(monkey_settings):
    stream = {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
            "serverName": "fallback.com",
            "settings": {},
            "shortIds": "ssss",
        },
    }
    inb = _inbound(stream=stream)
    uri = build_vless_link(inb, "u", "x")
    assert "sni=fallback.com" in uri
    assert "sid=ssss" in uri
