"""Tests for :mod:`app.services.inbounds` — TTL cache + enable filtering.

Covered behaviour:

* :func:`list_user_inbounds` filters out inbounds where ``enable=False``.
* A second call within the TTL window does NOT re-query the panel — the
  cached list is returned (call counter stays at 1).
* After the TTL elapses (we monkeypatch ``time.monotonic``) or
  :func:`clear_cache` is invoked, the next call re-queries the panel
  (counter increments).
* If the panel raises, the exception propagates and the cache is NOT
  updated (counter stays at the failed-attempt number; subsequent
  successful call increments it).
* Malformed entries from the panel are skipped silently — the rest of
  the list is still returned.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services import inbounds as inbounds_mod


@pytest.fixture(autouse=True)
def _reset_cache():
    """Drop the module-level cache before AND after each test.

    The cache is process-global so leaks between tests would otherwise
    produce flaky behaviour depending on test ordering.
    """
    inbounds_mod.clear_cache()
    yield
    inbounds_mod.clear_cache()


def _make_panel_inbound(
    inbound_id: int,
    *,
    remark: str = "DE",
    port: int = 443,
    enable: bool = True,
) -> dict:
    """Build a panel-shaped inbound dict (matches what list_inbounds returns)."""
    return {
        "id": inbound_id,
        "remark": remark,
        "port": port,
        "enable": enable,
    }


async def test_list_user_inbounds_filters_disabled(monkeypatch, mock_xui_client):
    """Inbounds with ``enable=False`` are dropped from the result."""
    panel_data = [
        _make_panel_inbound(1, remark="DE", enable=True),
        _make_panel_inbound(2, remark="NL", enable=False),
        _make_panel_inbound(3, remark="US", enable=True),
    ]
    monkeypatch.setattr(
        inbounds_mod, "list_inbounds", AsyncMock(return_value=panel_data)
    )

    options = await inbounds_mod.list_user_inbounds(mock_xui_client)
    ids = [o.id for o in options]
    assert 1 in ids
    assert 3 in ids
    assert 2 not in ids
    # Returned dataclass mirrors panel fields.
    de = next(o for o in options if o.id == 1)
    assert de.remark == "DE"
    assert de.port == 443
    assert de.enabled is True


async def test_list_user_inbounds_caches_within_ttl(monkeypatch, mock_xui_client):
    """A second call within the TTL window reuses the cached list."""
    counter = {"calls": 0}

    async def fake_list(_xui):
        counter["calls"] += 1
        return [_make_panel_inbound(1, enable=True)]

    monkeypatch.setattr(inbounds_mod, "list_inbounds", fake_list)
    # Freeze time at 1000.0.
    monkeypatch.setattr(inbounds_mod.time, "monotonic", lambda: 1000.0)

    first = await inbounds_mod.list_user_inbounds(mock_xui_client)
    second = await inbounds_mod.list_user_inbounds(mock_xui_client)

    assert counter["calls"] == 1
    # Same list object reference is fine but we only require equality.
    assert [o.id for o in first] == [o.id for o in second] == [1]


async def test_list_user_inbounds_refreshes_after_ttl(monkeypatch, mock_xui_client):
    """After the TTL elapses the panel is queried again."""
    counter = {"calls": 0}

    async def fake_list(_xui):
        counter["calls"] += 1
        return [_make_panel_inbound(1, enable=True)]

    monkeypatch.setattr(inbounds_mod, "list_inbounds", fake_list)

    # We control time precisely so we can step past the 30-second TTL.
    current = {"t": 0.0}
    monkeypatch.setattr(inbounds_mod.time, "monotonic", lambda: current["t"])

    current["t"] = 100.0
    await inbounds_mod.list_user_inbounds(mock_xui_client)
    assert counter["calls"] == 1

    # Step past the TTL (default 30s).
    current["t"] = 100.0 + inbounds_mod._CACHE_TTL_SEC + 1
    await inbounds_mod.list_user_inbounds(mock_xui_client)
    assert counter["calls"] == 2


async def test_clear_cache_forces_refetch(monkeypatch, mock_xui_client):
    """`clear_cache` invalidates the cache so the next call hits the panel."""
    counter = {"calls": 0}

    async def fake_list(_xui):
        counter["calls"] += 1
        return [_make_panel_inbound(1, enable=True)]

    monkeypatch.setattr(inbounds_mod, "list_inbounds", fake_list)
    monkeypatch.setattr(inbounds_mod.time, "monotonic", lambda: 500.0)

    await inbounds_mod.list_user_inbounds(mock_xui_client)
    assert counter["calls"] == 1
    inbounds_mod.clear_cache()
    await inbounds_mod.list_user_inbounds(mock_xui_client)
    assert counter["calls"] == 2


async def test_list_user_inbounds_propagates_exception(monkeypatch, mock_xui_client):
    """An exception from the panel propagates and leaves the cache empty."""

    boom = RuntimeError("panel down")

    async def fake_list(_xui):
        raise boom

    monkeypatch.setattr(inbounds_mod, "list_inbounds", fake_list)
    monkeypatch.setattr(inbounds_mod.time, "monotonic", lambda: 100.0)

    with pytest.raises(RuntimeError):
        await inbounds_mod.list_user_inbounds(mock_xui_client)

    # After the failure the cache stays empty: a second call will try
    # again (we replace `list_inbounds` to record the second invocation).
    counter = {"calls": 0}

    async def fake_ok(_xui):
        counter["calls"] += 1
        return [_make_panel_inbound(1, enable=True)]

    monkeypatch.setattr(inbounds_mod, "list_inbounds", fake_ok)
    options = await inbounds_mod.list_user_inbounds(mock_xui_client)
    assert counter["calls"] == 1
    assert [o.id for o in options] == [1]


async def test_list_user_inbounds_skips_malformed(monkeypatch, mock_xui_client):
    """Entries without an ``id`` field are skipped, the rest is returned."""
    panel_data = [
        {"remark": "no-id", "enable": True},  # missing id → skipped
        _make_panel_inbound(7, remark="DE", enable=True),
        {"id": "not-an-int", "remark": "x", "enable": True},  # bad type → skipped
    ]
    monkeypatch.setattr(
        inbounds_mod, "list_inbounds", AsyncMock(return_value=panel_data)
    )
    monkeypatch.setattr(inbounds_mod.time, "monotonic", lambda: 0.0)

    options = await inbounds_mod.list_user_inbounds(mock_xui_client)
    assert [o.id for o in options] == [7]
