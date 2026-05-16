"""Tests for :mod:`app.xui.clients`."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.xui import XuiError
from app.xui.clients import (
    add_client,
    del_client,
    get_client_traffics,
    make_client_email,
    make_client_uuid,
    update_client,
)


def test_make_client_uuid_unique():
    a = make_client_uuid()
    b = make_client_uuid()
    assert a != b
    # UUID4 string has 36 chars including dashes.
    assert len(a) == 36


def test_make_client_email_contains_tg_id():
    email = make_client_email(42)
    assert email.startswith("tg_42_")
    assert len(email) > len("tg_42_")


def test_make_client_email_no_username_legacy_shape():
    """Without a username the legacy ``tg_<id>_<hex>`` shape is preserved."""
    email = make_client_email(7, None)
    assert email.startswith("tg_7_")
    # 'tg_7_' + 6 hex chars
    assert len(email) == len("tg_7_") + 6


def test_make_client_email_with_plain_username():
    email = make_client_email(42, "alice")
    assert email.startswith("alice_tg_42_")
    # Suffix is 6 hex chars.
    assert len(email) == len("alice_tg_42_") + 6


def test_make_client_email_normalises_special_chars():
    """Dots, dashes and spaces collapse into underscores."""
    email = make_client_email(1, "a.b-c d")
    assert email.startswith("a_b_c_d_tg_1_")


def test_make_client_email_truncates_long_username():
    """The slug portion is capped at 32 chars."""
    long_name = "a" * 50
    email = make_client_email(99, long_name)
    # The slug is exactly 32 'a's, then '_tg_99_<hex>'.
    assert email.startswith("a" * 32 + "_tg_99_")
    # 33rd 'a' must NOT be present before '_tg_'.
    assert not email.startswith("a" * 33)


def test_make_client_email_all_special_falls_back():
    """A username made entirely of special chars normalises to empty
    after the trim, so the helper falls back to the legacy shape."""
    email = make_client_email(5, "...---!!!")
    assert email.startswith("tg_5_")
    # Must NOT have any leading slug separator.
    assert "_tg_5_" not in email[: len("tg_5_")]


def test_make_client_email_lowercases_username():
    email = make_client_email(8, "Alice")
    assert email.startswith("alice_tg_8_")
    # No uppercase letters in the slug part.
    slug = email.split("_tg_", 1)[0]
    assert slug == slug.lower()


def test_make_client_email_empty_username_falls_back():
    """An empty-string username is treated the same as None."""
    email = make_client_email(11, "")
    assert email.startswith("tg_11_")


async def test_add_client_sends_correct_payload():
    client = AsyncMock()
    client.request_json = AsyncMock(return_value={"id": "uuid", "email": "tg_1_xx"})
    out = await add_client(
        client,
        inbound_id=3,
        client_uuid="uuid",
        email="tg_1_xx",
        expiry_ts_ms=1700000000000,
        sub_id="subid",
    )
    assert out["id"] == "uuid"
    # Verify the call shape.
    args, kwargs = client.request_json.call_args
    assert args[0] == "POST"
    assert args[1] == "/panel/api/inbounds/addClient"
    body = kwargs["json"]
    assert body["id"] == 3
    # ``settings`` is JSON-stringified.
    parsed = json.loads(body["settings"])
    assert parsed["clients"][0]["id"] == "uuid"
    assert parsed["clients"][0]["subId"] == "subid"
    assert parsed["clients"][0]["expiryTime"] == 1700000000000


async def test_add_client_defaults_sub_id_when_none():
    client = AsyncMock()
    client.request_json = AsyncMock(return_value=None)
    out = await add_client(
        client,
        inbound_id=1,
        client_uuid="uuid",
        email="e",
        expiry_ts_ms=0,
        sub_id=None,
    )
    # When obj is not a dict, helper builds fallback with generated subId.
    assert isinstance(out, dict)
    assert "subId" in out


async def test_update_client_whitelists_fields():
    client = AsyncMock()
    client.request_json = AsyncMock(return_value={"id": "uuid"})
    with pytest.raises(ValueError):
        await update_client(client, inbound_id=1, client_uuid="uuid", evil="bad")


async def test_update_client_payload_coercion():
    client = AsyncMock()
    client.request_json = AsyncMock(return_value=None)
    await update_client(
        client,
        inbound_id=1,
        client_uuid="u",
        expiryTime="1700000000000",
        totalGB="5",
        enable=1,
        limitIp="2",
        reset="0",
    )
    args, kwargs = client.request_json.call_args
    body = kwargs["json"]
    parsed = json.loads(body["settings"])
    fields = parsed["clients"][0]
    assert fields["expiryTime"] == 1700000000000
    assert fields["totalGB"] == 5
    assert fields["enable"] is True
    assert fields["limitIp"] == 2
    assert fields["reset"] == 0


async def test_update_client_default_id_set():
    """If the caller doesn't pass 'id' explicitly, it defaults to client_uuid."""
    client = AsyncMock()
    client.request_json = AsyncMock(return_value=None)
    await update_client(client, inbound_id=1, client_uuid="uuid-Z", enable=False)
    body = client.request_json.call_args.kwargs["json"]
    parsed = json.loads(body["settings"])
    assert parsed["clients"][0]["id"] == "uuid-Z"


async def test_del_client_calls_correct_endpoint():
    client = AsyncMock()
    client.request_json = AsyncMock(return_value=None)
    await del_client(client, inbound_id=5, client_uuid="uuu")
    args, _ = client.request_json.call_args
    assert args[1] == "/panel/api/inbounds/5/delClient/uuu"


async def test_del_client_soft_fail_not_exist():
    """A 'not exist' error from the panel is swallowed."""
    client = AsyncMock()
    client.request_json = AsyncMock(side_effect=XuiError("client does not exist"))
    # Must not raise.
    await del_client(client, inbound_id=1, client_uuid="u")


async def test_del_client_soft_fail_not_found():
    client = AsyncMock()
    client.request_json = AsyncMock(side_effect=XuiError("not found"))
    await del_client(client, inbound_id=1, client_uuid="u")


async def test_del_client_real_error_propagates():
    client = AsyncMock()
    client.request_json = AsyncMock(side_effect=XuiError("network blew up"))
    with pytest.raises(XuiError):
        await del_client(client, inbound_id=1, client_uuid="u")


async def test_get_client_traffics():
    client = AsyncMock()
    client.request_json = AsyncMock(
        return_value={"id": 1, "email": "e", "up": 10, "down": 20}
    )
    out = await get_client_traffics(client, "e")
    assert out["up"] == 10


async def test_get_client_traffics_empty_obj():
    """obj=None → empty dict."""
    client = AsyncMock()
    client.request_json = AsyncMock(return_value=None)
    out = await get_client_traffics(client, "missing")
    assert out == {}


async def test_get_client_traffics_unexpected_shape():
    client = AsyncMock()
    client.request_json = AsyncMock(return_value=[1, 2, 3])
    with pytest.raises(XuiError):
        await get_client_traffics(client, "e")
