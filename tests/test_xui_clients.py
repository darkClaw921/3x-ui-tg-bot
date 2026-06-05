"""Tests for :mod:`app.xui.clients`."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.xui import XuiError
from app.xui.clients import (
    add_client,
    del_client,
    get_client,
    get_client_traffics,
    make_client_email,
    make_client_uuid,
    update_client,
)


def _request_json_for(current: dict):
    """Build an AsyncMock side_effect for ``client.request_json``.

    Returns the wrapped ``current`` client for ``clients/get/...`` paths
    (mirroring the panel envelope ``{"client": {...}, "inboundIds": [...]}``)
    and ``None`` for the subsequent mutating call.
    """

    async def _dispatch(method, path, **kwargs):
        if "clients/get/" in path:
            return {"client": dict(current), "inboundIds": [1]}
        return None

    return _dispatch


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
    """add_client posts a ``{client, inboundIds}`` body to clients/add."""
    client = AsyncMock()
    client.request_json = AsyncMock(return_value=None)
    out = await add_client(
        client,
        inbound_id=3,
        client_uuid="uuid",
        email="tg_1_xx",
        expiry_ts_ms=1700000000000,
        sub_id="subid",
        total_gb=5,
        tg_id=42,
    )
    # obj is null on the new panel → fallback dict keeps the ids.
    assert out["id"] == "uuid"
    assert out["email"] == "tg_1_xx"
    args, kwargs = client.request_json.call_args
    assert args[0] == "POST"
    assert args[1] == "/panel/api/clients/add"
    body = kwargs["json"]
    assert body["inboundIds"] == [3]
    c = body["client"]
    assert c["email"] == "tg_1_xx"
    assert c["uuid"] == "uuid"
    assert c["subId"] == "subid"
    assert c["expiryTime"] == 1700000000000
    assert c["totalGB"] == 5
    assert c["tgId"] == 42  # coerced to int
    # The legacy ``settings``-string wrapper must be gone.
    assert "settings" not in body


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


async def test_add_client_coerces_non_numeric_tg_id():
    """A non-numeric tg_id degrades to 0 (the create endpoint wants an int)."""
    client = AsyncMock()
    client.request_json = AsyncMock(return_value=None)
    await add_client(
        client, inbound_id=1, client_uuid="u", email="e", expiry_ts_ms=0, tg_id="oops"
    )
    body = client.request_json.call_args.kwargs["json"]
    assert body["client"]["tgId"] == 0


async def test_get_client_returns_inner_client():
    client = AsyncMock()
    client.request_json = AsyncMock(
        return_value={"client": {"email": "e", "uuid": "u"}, "inboundIds": [1]}
    )
    out = await get_client(client, "e")
    assert out == {"email": "e", "uuid": "u"}
    assert client.request_json.call_args.args[1] == "/panel/api/clients/get/e"


async def test_get_client_not_found_returns_empty():
    client = AsyncMock()
    client.request_json = AsyncMock(side_effect=XuiError(" (record not found)"))
    out = await get_client(client, "missing")
    assert out == {}


async def test_update_client_whitelists_fields():
    client = AsyncMock()
    with pytest.raises(ValueError):
        await update_client(client, "e", evil="bad")


async def test_update_client_read_merge_write():
    """Update reads the current client, overlays changes, drops numeric id."""
    client = AsyncMock()
    current = {
        "id": 7,  # numeric internal id — must be dropped from the update body
        "email": "old",
        "uuid": "U",
        "subId": "S",
        "totalGB": 5,
        "expiryTime": 100,
        "enable": True,
        "tgId": 42,
    }
    client.request_json = AsyncMock(side_effect=_request_json_for(current))
    await update_client(client, "old", enable=False)

    calls = client.request_json.await_args_list
    assert calls[0].args == ("GET", "/panel/api/clients/get/old")
    assert calls[1].args[0] == "POST"
    assert calls[1].args[1] == "/panel/api/clients/update/old"
    body = calls[1].kwargs["json"]
    assert "id" not in body  # numeric id stripped (panel wants a string id)
    assert body["enable"] is False  # override applied
    assert body["totalGB"] == 5  # preserved
    assert body["uuid"] == "U"  # preserved
    assert body["email"] == "old"  # mandatory, set from the arg


async def test_update_client_payload_coercion():
    client = AsyncMock()
    current = {"email": "e", "uuid": "u", "totalGB": 0, "expiryTime": 0, "enable": True}
    client.request_json = AsyncMock(side_effect=_request_json_for(current))
    await update_client(
        client,
        "e",
        expiryTime="1700000000000",
        totalGB="5",
        enable=1,
        limitIp="2",
        reset="0",
    )
    body = client.request_json.await_args_list[1].kwargs["json"]
    assert body["expiryTime"] == 1700000000000
    assert body["totalGB"] == 5
    assert body["enable"] is True
    assert body["limitIp"] == 2
    assert body["reset"] == 0


async def test_update_client_not_found_raises():
    client = AsyncMock()
    client.request_json = AsyncMock(return_value=None)  # get → {}
    with pytest.raises(XuiError):
        await update_client(client, "ghost", enable=False)


async def test_del_client_calls_correct_endpoint():
    client = AsyncMock()
    client.request_json = AsyncMock(return_value=None)
    await del_client(client, "user@e")
    args, _ = client.request_json.call_args
    assert args[0] == "POST"
    assert args[1] == "/panel/api/clients/del/user%40e"


async def test_del_client_keep_traffic_flag():
    client = AsyncMock()
    client.request_json = AsyncMock(return_value=None)
    await del_client(client, "e", keep_traffic=True)
    assert client.request_json.call_args.args[1] == "/panel/api/clients/del/e?keepTraffic=1"


async def test_del_client_soft_fail_not_exist():
    """A 'not exist' error from the panel is swallowed."""
    client = AsyncMock()
    client.request_json = AsyncMock(side_effect=XuiError("client does not exist"))
    await del_client(client, "u")  # must not raise


async def test_del_client_soft_fail_not_found():
    client = AsyncMock()
    client.request_json = AsyncMock(
        side_effect=XuiError('client "x" not found in any inbound or client record')
    )
    await del_client(client, "u")


async def test_del_client_real_error_propagates():
    client = AsyncMock()
    client.request_json = AsyncMock(side_effect=XuiError("network blew up"))
    with pytest.raises(XuiError):
        await del_client(client, "u")


async def test_get_client_traffics():
    """Traffic rides along the paged client list; we return the item's traffic."""
    client = AsyncMock()
    client.request_json = AsyncMock(
        return_value={
            "items": [{"email": "e", "traffic": {"up": 10, "down": 20, "total": 0}}],
            "total": 1,
        }
    )
    out = await get_client_traffics(client, "e")
    assert out["up"] == 10
    assert out["down"] == 20
    path = client.request_json.call_args.args[1]
    assert "clients/list/paged" in path
    assert "search=e" in path


async def test_get_client_traffics_single_item_lenient():
    """A one-row search result is accepted even without an exact email match."""
    client = AsyncMock()
    client.request_json = AsyncMock(
        return_value={"items": [{"email": "other", "traffic": {"up": 5}}], "total": 1}
    )
    out = await get_client_traffics(client, "e")
    assert out["up"] == 5


async def test_get_client_traffics_not_found():
    """No items → empty dict."""
    client = AsyncMock()
    client.request_json = AsyncMock(return_value={"items": [], "total": 0})
    out = await get_client_traffics(client, "missing")
    assert out == {}


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
