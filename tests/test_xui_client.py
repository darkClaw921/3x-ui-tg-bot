"""Tests for :mod:`app.xui.client` — auth, retries, lifecycle."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.xui.client import XuiClient, XuiError, close_xui_client, get_xui_client


async def test_login_success(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="http://xui.test/login",
        json={"success": True, "msg": "ok"},
    )
    client = XuiClient(base_url="http://xui.test", username="u", password="p", verify_ssl=False)
    await client.login()
    assert client._logged_in is True
    await client.close()


async def test_login_wrong_creds(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="http://xui.test/login",
        json={"success": False, "msg": "wrong"},
    )
    client = XuiClient(base_url="http://xui.test", username="u", password="p", verify_ssl=False)
    with pytest.raises(XuiError):
        await client.login()
    await client.close()


async def test_login_http_error(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="http://xui.test/login",
        status_code=500,
        text="boom",
    )
    client = XuiClient(base_url="http://xui.test", username="u", password="p", verify_ssl=False)
    with pytest.raises(XuiError):
        await client.login()
    await client.close()


async def test_login_non_json(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="http://xui.test/login",
        text="not-json",
        headers={"content-type": "text/plain"},
    )
    client = XuiClient(base_url="http://xui.test", username="u", password="p", verify_ssl=False)
    with pytest.raises(XuiError):
        await client.login()
    await client.close()


async def test_login_transport_error(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("net-down"))
    client = XuiClient(base_url="http://xui.test", username="u", password="p", verify_ssl=False)
    with pytest.raises(XuiError):
        await client.login()
    await client.close()


async def test_request_json_unwraps_obj(httpx_mock):
    httpx_mock.add_response(
        method="POST", url="http://xui.test/login", json={"success": True}
    )
    httpx_mock.add_response(
        method="GET",
        url="http://xui.test/panel/api/inbounds/list",
        json={"success": True, "obj": [1, 2, 3]},
    )
    client = XuiClient(base_url="http://xui.test", username="u", password="p", verify_ssl=False)
    result = await client.request_json("GET", "/panel/api/inbounds/list")
    assert result == [1, 2, 3]
    await client.close()


async def test_request_relogin_on_401(httpx_mock):
    # First login → OK.
    httpx_mock.add_response(
        method="POST", url="http://xui.test/login", json={"success": True}
    )
    # First GET → 401.
    httpx_mock.add_response(
        method="GET", url="http://xui.test/foo", status_code=401, text="no"
    )
    # Second login → OK.
    httpx_mock.add_response(
        method="POST", url="http://xui.test/login", json={"success": True}
    )
    # Retry GET → OK.
    httpx_mock.add_response(
        method="GET",
        url="http://xui.test/foo",
        json={"success": True, "obj": {"ok": 1}},
    )
    client = XuiClient(base_url="http://xui.test", username="u", password="p", verify_ssl=False)
    result = await client.request_json("GET", "/foo")
    assert result == {"ok": 1}
    await client.close()


async def test_request_relogin_on_envelope_login_msg(httpx_mock):
    """200 OK but success=false with msg=login → must trigger relogin."""
    httpx_mock.add_response(
        method="POST", url="http://xui.test/login", json={"success": True}
    )
    httpx_mock.add_response(
        method="GET",
        url="http://xui.test/foo",
        json={"success": False, "msg": "please login"},
    )
    httpx_mock.add_response(
        method="POST", url="http://xui.test/login", json={"success": True}
    )
    httpx_mock.add_response(
        method="GET",
        url="http://xui.test/foo",
        json={"success": True, "obj": "ok"},
    )
    client = XuiClient(base_url="http://xui.test", username="u", password="p", verify_ssl=False)
    out = await client.request_json("GET", "/foo")
    assert out == "ok"
    await client.close()


async def test_request_json_panel_error(httpx_mock):
    httpx_mock.add_response(
        method="POST", url="http://xui.test/login", json={"success": True}
    )
    httpx_mock.add_response(
        method="GET",
        url="http://xui.test/foo",
        json={"success": False, "msg": "bad-thing"},
    )
    client = XuiClient(base_url="http://xui.test", username="u", password="p", verify_ssl=False)
    with pytest.raises(XuiError):
        await client.request_json("GET", "/foo")
    await client.close()


async def test_request_json_non_2xx(httpx_mock):
    httpx_mock.add_response(
        method="POST", url="http://xui.test/login", json={"success": True}
    )
    httpx_mock.add_response(
        method="GET", url="http://xui.test/foo", status_code=500, text="ouch"
    )
    client = XuiClient(base_url="http://xui.test", username="u", password="p", verify_ssl=False)
    with pytest.raises(XuiError):
        await client.request_json("GET", "/foo")
    await client.close()


async def test_request_json_non_json_response(httpx_mock):
    httpx_mock.add_response(
        method="POST", url="http://xui.test/login", json={"success": True}
    )
    httpx_mock.add_response(
        method="GET",
        url="http://xui.test/foo",
        text="not-json",
        headers={"content-type": "text/plain"},
    )
    client = XuiClient(base_url="http://xui.test", username="u", password="p", verify_ssl=False)
    with pytest.raises(XuiError):
        await client.request_json("GET", "/foo")
    await client.close()


async def test_request_json_envelope_not_object(httpx_mock):
    httpx_mock.add_response(
        method="POST", url="http://xui.test/login", json={"success": True}
    )
    httpx_mock.add_response(
        method="GET",
        url="http://xui.test/foo",
        json=[1, 2, 3],
    )
    client = XuiClient(base_url="http://xui.test", username="u", password="p", verify_ssl=False)
    with pytest.raises(XuiError):
        await client.request_json("GET", "/foo")
    await client.close()


async def test_concurrent_requests_share_login(httpx_mock):
    """Two concurrent requests should not double-login (asyncio.Lock)."""
    httpx_mock.add_response(
        method="POST", url="http://xui.test/login", json={"success": True}
    )
    httpx_mock.add_response(
        method="GET",
        url="http://xui.test/a",
        json={"success": True, "obj": "A"},
    )
    httpx_mock.add_response(
        method="GET",
        url="http://xui.test/b",
        json={"success": True, "obj": "B"},
    )
    client = XuiClient(base_url="http://xui.test", username="u", password="p", verify_ssl=False)
    a, b = await asyncio.gather(
        client.request_json("GET", "/a"),
        client.request_json("GET", "/b"),
    )
    assert {a, b} == {"A", "B"}
    # Only one /login request total.
    login_reqs = [r for r in httpx_mock.get_requests() if r.url.path == "/login"]
    assert len(login_reqs) == 1
    await client.close()


async def test_context_manager_closes(httpx_mock):
    httpx_mock.add_response(
        method="POST", url="http://xui.test/login", json={"success": True}
    )
    async with XuiClient(
        base_url="http://xui.test", username="u", password="p", verify_ssl=False
    ) as client:
        await client.login()
    # Closed inside __aexit__ — no assertion needed (no leak).


async def test_get_xui_client_singleton():
    """Singleton factory returns the same instance on repeated calls."""
    # Reset module-level singleton first.
    await close_xui_client()
    c1 = await get_xui_client()
    c2 = await get_xui_client()
    assert c1 is c2
    await close_xui_client()
