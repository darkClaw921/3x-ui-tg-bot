"""Tests for :mod:`app.handlers.user._keys`."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.handlers.user import _keys as keys_mod
from app.xui import XuiError


def _sub(sub_id=1, xui_sub_id="subid", uuid="u", email="e"):
    from app.db.repos.subscriptions import Subscription

    return Subscription(
        id=sub_id, user_id=1, xui_inbound_id=1, xui_client_uuid=uuid,
        xui_client_email=email, xui_sub_id=xui_sub_id,
        expires_at="2099-01-01 00:00:00", created_at="2025",
        plan_id=None, status="active",
    )


async def test_deliver_keys_happy(monkeypatch, mock_bot):
    sub = _sub()
    inbound = {
        "port": 443,
        "streamSettings": {"network": "tcp", "security": "none"},
        "settings": {"clients": [{"id": "u"}]},
    }
    monkeypatch.setattr(keys_mod, "get_inbound", AsyncMock(return_value=inbound))
    await keys_mod.deliver_keys(
        mock_bot, AsyncMock(), chat_id=1, sub=sub, header="HEADER"
    )
    mock_bot.send_message.assert_awaited()
    mock_bot.send_photo.assert_awaited()


async def test_deliver_keys_xui_error(monkeypatch, mock_bot):
    sub = _sub()
    monkeypatch.setattr(
        keys_mod, "get_inbound", AsyncMock(side_effect=XuiError("down"))
    )
    # Must not raise — still sends sub URL fallback.
    await keys_mod.deliver_keys(
        mock_bot, AsyncMock(), chat_id=1, sub=sub
    )
    mock_bot.send_message.assert_awaited()


async def test_deliver_keys_no_sub_id(monkeypatch, mock_bot):
    """Subscription with empty xui_sub_id → sub_url is empty too."""
    sub = _sub(xui_sub_id="")
    inbound = {
        "port": 443,
        "streamSettings": {"network": "tcp", "security": "none"},
        "settings": {"clients": [{"id": "u"}]},
    }
    monkeypatch.setattr(keys_mod, "get_inbound", AsyncMock(return_value=inbound))
    await keys_mod.deliver_keys(mock_bot, AsyncMock(), chat_id=1, sub=sub)
    mock_bot.send_message.assert_awaited()


async def test_deliver_keys_no_vless_no_sub_url(monkeypatch, mock_bot):
    """Both vless and sub URL missing → still sends messages, skips photo."""
    sub = _sub(xui_sub_id="")
    monkeypatch.setattr(
        keys_mod, "get_inbound", AsyncMock(side_effect=XuiError("down"))
    )
    await keys_mod.deliver_keys(mock_bot, AsyncMock(), chat_id=1, sub=sub)
    mock_bot.send_message.assert_awaited()
    mock_bot.send_photo.assert_not_awaited()


# --------------------------------------------------------------------------- #
# Phase 6 — connection guide / deep-link import URLs
# --------------------------------------------------------------------------- #


def test_build_howto_text_contains_all_client_links():
    sub_url = "https://sub.test/sub/XYZ"
    from app.xui.links import build_import_links

    links = build_import_links(sub_url)
    text_ru = keys_mod.build_howto_text(sub_url, "ru")
    text_en = keys_mod.build_howto_text(sub_url, "en")
    for body in (text_ru, text_en):
        assert links["happ"] in body
        assert links["v2rayng"] in body
        assert links["hiddify"] in body
        assert links["streisand"] in body
    # Localised titles differ between languages.
    assert "Как подключиться" in text_ru
    assert "How to connect" in text_en


def test_build_howto_text_empty_for_no_sub_url():
    assert keys_mod.build_howto_text("", "ru") == ""


async def test_deliver_keys_sends_howto_message(monkeypatch, mock_bot):
    """When a sub URL exists, deliver_keys appends the connection-guide message."""
    sub = _sub()
    inbound = {
        "port": 443,
        "streamSettings": {"network": "tcp", "security": "none"},
        "settings": {"clients": [{"id": "u"}]},
    }
    monkeypatch.setattr(keys_mod, "get_inbound", AsyncMock(return_value=inbound))
    await keys_mod.deliver_keys(mock_bot, AsyncMock(), chat_id=1, sub=sub)

    bodies = [c.args[1] for c in mock_bot.send_message.await_args_list]
    assert any("happ://import/" in b for b in bodies)
    assert any("v2rayng://install-config" in b for b in bodies)
    assert any("hiddify://import/" in b for b in bodies)


async def test_deliver_keys_skips_howto_when_no_sub_url(monkeypatch, mock_bot):
    """No sub URL → no connection-guide message (nothing to import)."""
    sub = _sub(xui_sub_id="")
    monkeypatch.setattr(
        keys_mod, "get_inbound", AsyncMock(side_effect=XuiError("down"))
    )
    await keys_mod.deliver_keys(mock_bot, AsyncMock(), chat_id=1, sub=sub)
    bodies = [c.args[1] for c in mock_bot.send_message.await_args_list]
    assert not any("install-config" in b for b in bodies)
