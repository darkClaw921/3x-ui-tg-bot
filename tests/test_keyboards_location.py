"""Tests for location availability indicators and deep-link import URLs."""

from __future__ import annotations

from urllib.parse import quote

import pytest

from app.keyboards.admin import plan_inbounds_select_kb
from app.keyboards.user import inbound_select_kb, location_indicator
from app.services import health as health_service
from app.services.inbounds import InboundOption
from app.xui.links import build_import_links


@pytest.fixture(autouse=True)
def _reset_health_snapshot():
    """Each test starts and ends with a clean ('unknown') health snapshot."""
    health_service.set_cached_status(None)
    yield
    health_service.set_cached_status(None)


def _labels(kb):
    return [b.text for row in kb.inline_keyboard for b in row]


# --------------------------------------------------------------------------- #
# location_indicator
# --------------------------------------------------------------------------- #


def test_location_indicator_unknown_when_no_probe():
    health_service.set_cached_status(None)
    assert location_indicator("ru") == "⚪"
    assert location_indicator("en") == "⚪"


def test_location_indicator_up_and_down():
    health_service.set_cached_status("up")
    assert location_indicator("ru") == "🟢"
    health_service.set_cached_status("down")
    assert location_indicator("ru") == "🔴"


# --------------------------------------------------------------------------- #
# inbound_select_kb (user) — indicator + remark fallback
# --------------------------------------------------------------------------- #


def test_inbound_select_kb_shows_up_indicator():
    health_service.set_cached_status("up")
    opts = [InboundOption(id=5, remark="Germany", port=443, enabled=True)]
    labels = _labels(inbound_select_kb(1, opts, lang="ru"))
    assert any("🟢" in lbl and "Germany" in lbl for lbl in labels)


def test_inbound_select_kb_shows_down_indicator():
    health_service.set_cached_status("down")
    opts = [InboundOption(id=5, remark="Germany", port=443, enabled=True)]
    labels = _labels(inbound_select_kb(1, opts, lang="en"))
    assert any("🔴" in lbl for lbl in labels)


def test_inbound_select_kb_remark_fallback():
    """An empty panel remark falls back to a 'Location #<id>' label."""
    opts = [InboundOption(id=9, remark="", port=8443, enabled=True)]
    ru = _labels(inbound_select_kb(1, opts, lang="ru"))
    en = _labels(inbound_select_kb(1, opts, lang="en"))
    assert any("Локация #9" in lbl for lbl in ru)
    assert any("Location #9" in lbl for lbl in en)


# --------------------------------------------------------------------------- #
# plan_inbounds_select_kb (admin) — remark fallback
# --------------------------------------------------------------------------- #


def test_admin_plan_inbounds_kb_remark_fallback():
    opts = [
        InboundOption(id=5, remark="NL", port=443, enabled=True),
        InboundOption(id=7, remark="", port=8443, enabled=True),
    ]
    labels = _labels(plan_inbounds_select_kb(opts, selected={5}, lang="ru"))
    assert any("☑ NL" in lbl for lbl in labels)
    assert any("Локация #7" in lbl for lbl in labels)


# --------------------------------------------------------------------------- #
# build_import_links — deep-link schemes
# --------------------------------------------------------------------------- #


def test_build_import_links_schemes_and_encoding():
    sub_url = "https://sub.test/sub/ABC?x=1"
    links = build_import_links(sub_url)
    enc = quote(sub_url, safe="")
    assert links["v2rayng"] == f"v2rayng://install-config?url={enc}"
    assert links["hiddify"] == f"hiddify://import/{enc}"
    assert links["streisand"] == f"streisand://import/{enc}"


def test_build_import_links_empty_for_blank():
    assert build_import_links("") == {}
