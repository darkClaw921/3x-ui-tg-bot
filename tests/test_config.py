"""Tests for :mod:`app.config` — env parsing, defaults, CSV ADMIN_IDS."""

from __future__ import annotations

import importlib

import pytest


def _fresh_settings(monkeypatch, **env):
    """Build a fresh Settings() with given env vars (no global mutation).

    We do NOT reload :mod:`app.config` so that the shared singleton used by
    other tests is not perturbed. We construct a new :class:`Settings`
    object directly.
    """
    # Wipe interference env first.
    for k in (
        "ADMIN_IDS",
        "BOT_TOKEN",
        "XUI_BASE_URL",
        "XUI_USERNAME",
        "XUI_PASSWORD",
        "XUI_INBOUND_ID",
        "XUI_SERVER_HOST",
        "XUI_SUB_BASE_URL",
        "XUI_VERIFY_SSL",
        "DB_PATH",
        "LOG_LEVEL",
    ):
        monkeypatch.delenv(k, raising=False)

    base = {
        "BOT_TOKEN": "x",
        "XUI_BASE_URL": "http://xui.test",
        "XUI_USERNAME": "u",
        "XUI_PASSWORD": "p",
        "XUI_INBOUND_ID": "1",
        "XUI_SERVER_HOST": "vpn.test",
        "XUI_SUB_BASE_URL": "https://sub.test/sub",
    }
    base.update(env)
    for k, v in base.items():
        monkeypatch.setenv(k, v)

    from app.config import Settings

    return Settings()  # type: ignore[call-arg]


def test_admin_ids_csv(monkeypatch):
    s = _fresh_settings(monkeypatch, ADMIN_IDS="1,2,3")
    assert s.ADMIN_IDS == [1, 2, 3]


def test_admin_ids_csv_with_spaces(monkeypatch):
    s = _fresh_settings(monkeypatch, ADMIN_IDS="1, 2 ,  3")
    assert s.ADMIN_IDS == [1, 2, 3]


def test_admin_ids_empty(monkeypatch):
    s = _fresh_settings(monkeypatch, ADMIN_IDS="")
    assert s.ADMIN_IDS == []


def test_admin_ids_unset(monkeypatch):
    s = _fresh_settings(monkeypatch)
    # default is empty list
    assert s.ADMIN_IDS == []


def test_admin_ids_json_brackets(monkeypatch):
    s = _fresh_settings(monkeypatch, ADMIN_IDS="[10,20]")
    assert s.ADMIN_IDS == [10, 20]


def test_admin_ids_json_brackets_with_spaces(monkeypatch):
    s = _fresh_settings(monkeypatch, ADMIN_IDS=" [ 10 , 20 , 30 ] ")
    assert s.ADMIN_IDS == [10, 20, 30]


def test_admin_ids_json_brackets_empty(monkeypatch):
    s = _fresh_settings(monkeypatch, ADMIN_IDS="[]")
    assert s.ADMIN_IDS == []


def test_admin_ids_json_brackets_invalid_json(monkeypatch):
    import pydantic_core

    with pytest.raises(pydantic_core.ValidationError):
        _fresh_settings(monkeypatch, ADMIN_IDS="[10, abc]")


def test_admin_ids_single(monkeypatch):
    s = _fresh_settings(monkeypatch, ADMIN_IDS="42")
    assert s.ADMIN_IDS == [42]


def test_admin_ids_trailing_comma(monkeypatch):
    s = _fresh_settings(monkeypatch, ADMIN_IDS="1,2,,")
    assert s.ADMIN_IDS == [1, 2]


def test_admin_ids_pre_parsed_list(monkeypatch):
    """The validator must pass through real lists untouched."""
    from app.config import Settings

    s = Settings(
        BOT_TOKEN="x",
        XUI_BASE_URL="http://x",
        XUI_USERNAME="u",
        XUI_PASSWORD="p",
        XUI_INBOUND_ID=1,
        XUI_SERVER_HOST="h",
        XUI_SUB_BASE_URL="https://s",
        ADMIN_IDS=[7, 8],
    )
    assert s.ADMIN_IDS == [7, 8]


def test_settings_defaults_present(monkeypatch):
    s = _fresh_settings(monkeypatch)
    assert s.DB_PATH  # has default
    assert s.LOG_LEVEL == "INFO"
    assert s.XUI_VERIFY_SSL is True


def test_settings_verify_ssl_false(monkeypatch):
    s = _fresh_settings(monkeypatch, XUI_VERIFY_SSL="false")
    assert s.XUI_VERIFY_SSL is False
