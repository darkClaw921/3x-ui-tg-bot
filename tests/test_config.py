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
        "WALLET_TOPUP_PRESETS",
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
        "AUTO_RENEW_ENABLED",
        "TRAFFIC_ALERT_PERCENT",
        "STAR_SUBSCRIPTION_PLAN_DAYS",
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

    # Pin `_env_file=None` so a checked-out / deployed .env on the developer
    # machine does not leak values into the test and break the "unset" cases.
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_admin_ids_csv(monkeypatch):
    s = _fresh_settings(monkeypatch, ADMIN_IDS="1,2,3")
    assert s.ADMIN_IDS == [1, 2, 3]


def test_wallet_topup_presets_default(monkeypatch):
    s = _fresh_settings(monkeypatch)
    assert s.WALLET_TOPUP_PRESETS == [50, 100, 250, 500]


def test_wallet_topup_presets_csv(monkeypatch):
    s = _fresh_settings(monkeypatch, WALLET_TOPUP_PRESETS="25, 75 , 300")
    assert s.WALLET_TOPUP_PRESETS == [25, 75, 300]


def test_wallet_topup_presets_empty(monkeypatch):
    s = _fresh_settings(monkeypatch, WALLET_TOPUP_PRESETS="")
    assert s.WALLET_TOPUP_PRESETS == []


def test_wallet_topup_presets_json_brackets(monkeypatch):
    s = _fresh_settings(monkeypatch, WALLET_TOPUP_PRESETS="[10,20]")
    assert s.WALLET_TOPUP_PRESETS == [10, 20]


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


# --------------------------------------------------------------------------- #
# Retention — auto-renewal / traffic alerts (Phase 4)
# --------------------------------------------------------------------------- #


def test_auto_renew_defaults(monkeypatch):
    """Phase-4 retention knobs read their documented defaults."""
    s = _fresh_settings(monkeypatch)
    assert s.AUTO_RENEW_ENABLED is True
    assert s.TRAFFIC_ALERT_PERCENT == 80
    assert s.STAR_SUBSCRIPTION_PLAN_DAYS == 30


def test_auto_renew_enabled_false(monkeypatch):
    s = _fresh_settings(monkeypatch, AUTO_RENEW_ENABLED="false")
    assert s.AUTO_RENEW_ENABLED is False


def test_traffic_alert_percent_override(monkeypatch):
    s = _fresh_settings(monkeypatch, TRAFFIC_ALERT_PERCENT="90")
    assert s.TRAFFIC_ALERT_PERCENT == 90


def test_traffic_alert_percent_zero_disables(monkeypatch):
    s = _fresh_settings(monkeypatch, TRAFFIC_ALERT_PERCENT="0")
    assert s.TRAFFIC_ALERT_PERCENT == 0


def test_traffic_alert_percent_out_of_range_rejected(monkeypatch):
    import pydantic_core

    with pytest.raises(pydantic_core.ValidationError):
        _fresh_settings(monkeypatch, TRAFFIC_ALERT_PERCENT="150")


def test_star_subscription_plan_days_override(monkeypatch):
    s = _fresh_settings(monkeypatch, STAR_SUBSCRIPTION_PLAN_DAYS="31")
    assert s.STAR_SUBSCRIPTION_PLAN_DAYS == 31


def test_star_subscription_plan_days_must_be_positive(monkeypatch):
    import pydantic_core

    with pytest.raises(pydantic_core.ValidationError):
        _fresh_settings(monkeypatch, STAR_SUBSCRIPTION_PLAN_DAYS="0")
