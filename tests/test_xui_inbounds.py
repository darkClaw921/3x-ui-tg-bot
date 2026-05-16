"""Tests for :mod:`app.xui.inbounds`."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.xui import XuiError
from app.xui.inbounds import _parse_inbound, get_inbound, list_inbounds


def test_parse_inbound_decodes_json_string_fields():
    raw = {
        "id": 1,
        "settings": json.dumps({"clients": [{"id": "u"}]}),
        "streamSettings": json.dumps({"network": "tcp"}),
        "sniffing": "",
        "allocate": None,
    }
    parsed = _parse_inbound(raw)
    assert isinstance(parsed["settings"], dict)
    assert parsed["settings"]["clients"][0]["id"] == "u"
    assert parsed["streamSettings"]["network"] == "tcp"
    # The original dict is left untouched.
    assert isinstance(raw["settings"], str)


def test_parse_inbound_leaves_malformed_json_alone():
    raw = {"settings": "{not-json}"}
    parsed = _parse_inbound(raw)
    assert parsed["settings"] == "{not-json}"


def test_parse_inbound_handles_already_dict():
    raw = {"settings": {"clients": []}}
    parsed = _parse_inbound(raw)
    assert parsed["settings"] == {"clients": []}


async def test_list_inbounds_returns_parsed():
    client = AsyncMock()
    client.request_json = AsyncMock(
        return_value=[
            {"id": 1, "settings": json.dumps({"clients": []})},
            {"id": 2, "settings": json.dumps({"clients": [{"id": "u"}]})},
        ]
    )
    out = await list_inbounds(client)
    assert out[0]["settings"]["clients"] == []
    assert out[1]["settings"]["clients"][0]["id"] == "u"


async def test_list_inbounds_none_returns_empty():
    client = AsyncMock()
    client.request_json = AsyncMock(return_value=None)
    out = await list_inbounds(client)
    assert out == []


async def test_list_inbounds_not_a_list_raises():
    client = AsyncMock()
    client.request_json = AsyncMock(return_value={"oops": True})
    with pytest.raises(XuiError):
        await list_inbounds(client)


async def test_list_inbounds_filters_non_dict():
    client = AsyncMock()
    client.request_json = AsyncMock(return_value=[{"id": 1}, "junk", 5])
    out = await list_inbounds(client)
    assert out == [{"id": 1}]


async def test_get_inbound_returns_parsed():
    client = AsyncMock()
    client.request_json = AsyncMock(
        return_value={"id": 1, "settings": json.dumps({"clients": [{"id": "x"}]})}
    )
    inbound = await get_inbound(client, 1)
    assert inbound["settings"]["clients"][0]["id"] == "x"


async def test_get_inbound_non_dict_raises():
    client = AsyncMock()
    client.request_json = AsyncMock(return_value=42)
    with pytest.raises(XuiError):
        await get_inbound(client, 99)


async def test_get_inbound_propagates_panel_error():
    """If request_json raises XuiError, get_inbound propagates."""
    client = AsyncMock()
    client.request_json = AsyncMock(side_effect=XuiError("panel-down"))
    with pytest.raises(XuiError):
        await get_inbound(client, 1)
