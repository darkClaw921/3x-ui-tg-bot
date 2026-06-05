"""Boundary-value tests for the CONFIG + I18N + LINKS domain.

This module deliberately targets *edge* / *corner* inputs that the sibling
suites (``test_config.py``, ``test_i18n.py``, ``test_xui_links.py``) do not
already cover:

* :func:`app.config.Settings._parse_csv_ints` — the CSV/JSON int parser shared
  by ``ADMIN_IDS`` and ``WALLET_TOPUP_PRESETS`` (``None``, JSON non-array,
  non-numeric element …).
* The numeric field constraints (``ge`` / ``le`` / ``gt``) on the Phase-3/4
  knobs, probed exactly *on* and *just past* their boundaries.
* :func:`app.i18n.resolve_lang`, :func:`app.i18n.t`, :func:`app.i18n.pluralize`
  — language normalization, fallback chain, RU/EN plural buckets at the tricky
  counts (11-14, 21-24, 100/101/111, negatives, 1000).
* :func:`app.xui.links.build_import_links` and
  :func:`app.xui.links.build_subscription_url` — encoding of special / cyrillic
  characters, empty inputs, slash collapsing.

Each test asserts the *actual* observed behaviour of the code under test; any
place where that behaviour diverges from a naive expectation is called out in
an inline comment so the divergence is documented rather than silently encoded.
"""

from __future__ import annotations

import pydantic_core
import pytest

from app.config import Settings
from app.i18n import DEFAULT_LANG, pluralize, resolve_lang, t
from app.i18n.locales import en, ru
from app.xui.links import build_import_links, build_subscription_url


# --------------------------------------------------------------------------- #
# Local helpers (conftest.py is intentionally untouched)
# --------------------------------------------------------------------------- #


def _settings(**overrides: object) -> Settings:
    """Construct a :class:`Settings` with all required fields + ``overrides``.

    ``_env_file=None`` pins out any developer ``.env`` so the test sees exactly
    the values we pass. Values are supplied as native Python objects so the
    constructor (not the env layer) exercises the validators directly.
    """
    base: dict[str, object] = {
        "BOT_TOKEN": "x",
        "XUI_BASE_URL": "http://xui.test",
        "XUI_USERNAME": "u",
        "XUI_PASSWORD": "p",
        "XUI_INBOUND_ID": 1,
        "XUI_SERVER_HOST": "vpn.test",
        "XUI_SUB_BASE_URL": "https://sub.test/sub",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


# =========================================================================== #
# config._parse_csv_ints  (ADMIN_IDS / WALLET_TOPUP_PRESETS)
# =========================================================================== #


@pytest.mark.parametrize("field", ["ADMIN_IDS", "WALLET_TOPUP_PRESETS"])
def test_csv_none_yields_empty_list(field):
    # ``None`` is the explicit early-return branch of the validator.
    s = _settings(**{field: None})
    assert getattr(s, field) == []


@pytest.mark.parametrize("field", ["ADMIN_IDS", "WALLET_TOPUP_PRESETS"])
def test_csv_empty_string_yields_empty_list(field):
    s = _settings(**{field: ""})
    assert getattr(s, field) == []


@pytest.mark.parametrize("field", ["ADMIN_IDS", "WALLET_TOPUP_PRESETS"])
def test_csv_inner_and_outer_spaces_are_stripped(field):
    # " 1 , 2 " — leading/trailing whitespace on the whole string and on items.
    s = _settings(**{field: " 1 , 2 "})
    assert getattr(s, field) == [1, 2]


@pytest.mark.parametrize("field", ["ADMIN_IDS", "WALLET_TOPUP_PRESETS"])
def test_csv_trailing_comma_drops_empty_item(field):
    # "1,2," — the trailing empty segment is filtered out by ``if part.strip()``.
    s = _settings(**{field: "1,2,"})
    assert getattr(s, field) == [1, 2]


@pytest.mark.parametrize("field", ["ADMIN_IDS", "WALLET_TOPUP_PRESETS"])
def test_csv_json_array_is_decoded(field):
    s = _settings(**{field: "[1,2,3]"})
    assert getattr(s, field) == [1, 2, 3]


@pytest.mark.parametrize("field", ["ADMIN_IDS", "WALLET_TOPUP_PRESETS"])
def test_csv_empty_json_array(field):
    s = _settings(**{field: "[]"})
    assert getattr(s, field) == []


@pytest.mark.parametrize("field", ["ADMIN_IDS", "WALLET_TOPUP_PRESETS"])
def test_csv_single_value(field):
    s = _settings(**{field: "5"})
    assert getattr(s, field) == [5]


@pytest.mark.parametrize("field", ["ADMIN_IDS", "WALLET_TOPUP_PRESETS"])
def test_csv_json_non_array_rejected(field):
    # "{}" does not start with "[" → it is treated as a CSV item, and
    # ``int("{}")`` raises ValueError → surfaced as a pydantic ValidationError.
    # This is the task's "JSON non-array → error" boundary: a JSON object given
    # as the env value is rejected rather than silently accepted. (The validator's
    # explicit ``raise ValueError("value JSON must be an array")`` guard only
    # fires for a "[...]"-wrapped string whose JSON is not a list, which is
    # impossible — a bracketed string always decodes to a list — so that guard
    # is effectively unreachable through this code path.)
    with pytest.raises(pydantic_core.ValidationError):
        _settings(**{field: "{}"})


@pytest.mark.parametrize("field", ["ADMIN_IDS", "WALLET_TOPUP_PRESETS"])
def test_csv_non_numeric_item_rejected(field):
    with pytest.raises(pydantic_core.ValidationError):
        _settings(**{field: "1,foo"})


# =========================================================================== #
# config — numeric field constraints at the boundary
# =========================================================================== #


# --- TRIAL_DAYS: ge=0 ------------------------------------------------------- #


def test_trial_days_negative_rejected():
    with pytest.raises(pydantic_core.ValidationError):
        _settings(TRIAL_DAYS=-1)


@pytest.mark.parametrize("value", [0, 1])
def test_trial_days_zero_and_one_accepted(value):
    assert _settings(TRIAL_DAYS=value).TRIAL_DAYS == value


# --- TRIAL_TRAFFIC_GB: ge=0 ------------------------------------------------- #


def test_trial_traffic_gb_negative_rejected():
    with pytest.raises(pydantic_core.ValidationError):
        _settings(TRIAL_TRAFFIC_GB=-1)


@pytest.mark.parametrize("value", [0, 1])
def test_trial_traffic_gb_boundary_accepted(value):
    assert _settings(TRIAL_TRAFFIC_GB=value).TRIAL_TRAFFIC_GB == value


# --- TRAFFIC_ALERT_PERCENT: ge=0 le=100 ------------------------------------ #


def test_traffic_alert_percent_below_zero_rejected():
    with pytest.raises(pydantic_core.ValidationError):
        _settings(TRAFFIC_ALERT_PERCENT=-1)


@pytest.mark.parametrize("value", [0, 100])
def test_traffic_alert_percent_inclusive_bounds_accepted(value):
    assert _settings(TRAFFIC_ALERT_PERCENT=value).TRAFFIC_ALERT_PERCENT == value


def test_traffic_alert_percent_above_hundred_rejected():
    with pytest.raises(pydantic_core.ValidationError):
        _settings(TRAFFIC_ALERT_PERCENT=101)


# --- STAR_SUBSCRIPTION_PLAN_DAYS: gt=0 ------------------------------------- #


def test_star_subscription_plan_days_zero_rejected():
    # gt=0 is *strict* — zero is below the boundary.
    with pytest.raises(pydantic_core.ValidationError):
        _settings(STAR_SUBSCRIPTION_PLAN_DAYS=0)


def test_star_subscription_plan_days_one_accepted():
    assert _settings(STAR_SUBSCRIPTION_PLAN_DAYS=1).STAR_SUBSCRIPTION_PLAN_DAYS == 1


# =========================================================================== #
# i18n.resolve_lang
# =========================================================================== #


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (None, DEFAULT_LANG),  # missing → default
        ("", DEFAULT_LANG),  # empty → default
        ("en", "en"),  # exact supported
        ("en-US", "en"),  # IETF region tag → primary subtag
        ("RU", "ru"),  # upper-cased → normalized
        ("ru", "ru"),
        ("uk", "uk"),  # supported stub returned as-is
        ("fa", "fa"),
        ("zh", "zh"),
        ("zh-Hans", "zh"),  # script subtag stripped
        ("  en  ", "en"),  # surrounding whitespace is stripped
        ("  RU ", "ru"),  # whitespace + case together
        ("de", DEFAULT_LANG),  # unsupported → default
        ("xx", DEFAULT_LANG),  # nonsense → default
    ],
)
def test_resolve_lang_boundaries(code, expected):
    assert resolve_lang(code) == expected


def test_resolve_lang_underscore_is_not_a_subtag_separator():
    # NOTE (documented behaviour, NOT a bug): resolve_lang splits on "-" only
    # (IETF BCP-47 uses hyphens). An underscore locale like "en_GB" is therefore
    # treated as a single primary subtag "en_gb", which is unsupported, so it
    # resolves to DEFAULT_LANG ("ru") — not to "en". Telegram only ever sends
    # hyphenated tags, so this never bites in production.
    assert resolve_lang("en_GB") == DEFAULT_LANG


# =========================================================================== #
# i18n.t  — resolution, fallback chain, safe format
# =========================================================================== #


def test_t_existing_key_ru_and_en():
    assert t("menu.greeting", "ru") == ru.MESSAGES["menu.greeting"]
    assert t("menu.greeting", "en") == en.MESSAGES["menu.greeting"]


def test_t_missing_key_returns_key_itself():
    assert t("totally.absent.key", "en") == "totally.absent.key"
    assert t("totally.absent.key", "ru") == "totally.absent.key"


def test_t_stub_lang_falls_back_to_english():
    # uk catalog is empty → lookup("uk") misses, falls back to the EN value.
    assert t("menu.greeting", "uk") == en.MESSAGES["menu.greeting"]


def test_t_none_lang_uses_default_language():
    assert t("menu.greeting", None) == ru.MESSAGES["menu.greeting"]


def test_t_unsupported_lang_falls_back_to_english_not_default():
    # NOTE (documented behaviour): t() does NOT route ``lang`` through
    # resolve_lang. An unsupported code ("de") is passed straight to lookup(),
    # which misses the (absent) "de" table and falls back to FALLBACK_LANG
    # ("en") — NOT to DEFAULT_LANG ("ru"). So for an unknown language t()
    # yields the English string, whereas resolve_lang() would have yielded "ru".
    assert t("menu.greeting", "de") == en.MESSAGES["menu.greeting"]


def test_t_missing_placeholder_does_not_crash():
    # Template references {expires_at} but no param is supplied → the literal
    # placeholder survives (safe format_map) instead of raising KeyError.
    rendered = t("keys.valid_until", "en")
    assert "{expires_at}" in rendered


def test_t_placeholder_is_substituted_when_provided():
    rendered = t("keys.valid_until", "en", expires_at="2099-12-31")
    assert "2099-12-31" in rendered
    assert "{expires_at}" not in rendered


def test_t_extra_params_are_ignored():
    # A param the template never references must not raise nor alter output.
    assert t("menu.greeting", "en", nonexistent="zzz") == en.MESSAGES["menu.greeting"]


# =========================================================================== #
# i18n.pluralize  — RU buckets (one/few/many) + EN (one/other)
# =========================================================================== #


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (0, "подписок"),  # zero → many
        (1, "подписка"),  # one
        (2, "подписки"),  # few
        (3, "подписки"),  # few
        (4, "подписки"),  # few
        (5, "подписок"),  # many
        (11, "подписок"),  # teen exception → many (NOT one)
        (12, "подписок"),  # teen exception → many (NOT few)
        (14, "подписок"),  # teen exception → many (NOT few)
        (21, "подписка"),  # one (mod10==1, mod100!=11)
        (22, "подписки"),  # few
        (25, "подписок"),  # many
        (100, "подписок"),  # many (mod10==0)
        (101, "подписка"),  # one
        (111, "подписок"),  # teen exception → many
        (1000, "подписок"),  # many (mod10==0)
    ],
)
def test_pluralize_russian_buckets(n, expected):
    assert pluralize("mysub.subs_plural", n, "ru") == expected


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (0, "subscriptions"),  # other
        (1, "subscription"),  # one
        (2, "subscriptions"),  # other
        (5, "subscriptions"),  # other
    ],
)
def test_pluralize_english_forms(n, expected):
    assert pluralize("mysub.subs_plural", n, "en") == expected


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (-1, "подписка"),  # abs(-1)=1 → one
        (-2, "подписки"),  # abs(-2)=2 → few
        (-5, "подписок"),  # abs(-5)=5 → many
        (-11, "подписок"),  # abs(-11)=11 → many
    ],
)
def test_pluralize_russian_handles_negative_counts(n, expected):
    # The selector normalizes via abs(), so the magnitude drives the form.
    assert pluralize("mysub.subs_plural", n, "ru") == expected


def test_pluralize_english_negative_one():
    assert pluralize("mysub.subs_plural", -1, "en") == "subscription"


def test_pluralize_default_lang_matches_reference_subs_helper():
    # Mirrors _pluralize_subs in app.handlers.user.my_subscription: 1/2/5.
    assert pluralize("mysub.subs_plural", 1) == "подписка"
    assert pluralize("mysub.subs_plural", 2) == "подписки"
    assert pluralize("mysub.subs_plural", 5) == "подписок"


# =========================================================================== #
# links.build_import_links
# =========================================================================== #


def test_build_import_links_empty_url_returns_empty_dict():
    assert build_import_links("") == {}


def test_build_import_links_has_exactly_four_clients():
    links = build_import_links("https://sub.test/sub/abc")
    assert set(links) == {"happ", "v2rayng", "hiddify", "streisand"}


def test_build_import_links_happ_scheme_and_percent_encoding():
    from urllib.parse import quote

    url = "https://sub.test/sub/abc"
    links = build_import_links(url)
    expected_enc = quote(url, safe="")
    assert links["happ"] == f"happ://import/{expected_enc}"
    assert links["happ"].startswith("happ://import/")
    # The raw "/" and ":" of the embedded URL must be percent-encoded so the
    # deep-link path stays well-formed.
    assert "%3A%2F%2F" in links["happ"]


def test_build_import_links_special_chars_are_encoded():
    from urllib.parse import quote

    # ?, &, =, space and a cyrillic word all need encoding.
    url = "https://h.test/sub/a b?x=1&y=2/привет"
    links = build_import_links(url)
    encoded = quote(url, safe="")
    for client, value in links.items():
        # Every reserved char that would break the deep link is gone.
        assert " " not in value, client
        assert "&" not in value, client
        # The encoded payload is identical across all path-tail/query clients.
        assert encoded in value, client


def test_build_import_links_v2rayng_passes_url_as_query_param():
    from urllib.parse import quote

    url = "https://sub.test/sub/xyz"
    links = build_import_links(url)
    assert links["v2rayng"] == f"v2rayng://install-config?url={quote(url, safe='')}"


# =========================================================================== #
# links.build_subscription_url  — slash collapsing
# =========================================================================== #


def test_build_subscription_url_base_trailing_slash_and_leading_slash(monkey_settings):
    monkey_settings(XUI_SUB_BASE_URL="https://host/sub/")
    # Every combination of trailing/leading slash collapses to a single "/".
    assert build_subscription_url("abc") == "https://host/sub/abc"
    assert build_subscription_url("/abc") == "https://host/sub/abc"


def test_build_subscription_url_base_no_trailing_slash(monkey_settings):
    monkey_settings(XUI_SUB_BASE_URL="https://host/sub")
    assert build_subscription_url("abc") == "https://host/sub/abc"
    assert build_subscription_url("/abc") == "https://host/sub/abc"


def test_build_subscription_url_empty_sub_id_leaves_trailing_slash(monkey_settings):
    # An empty sub_id yields "<base>/" — the join always inserts exactly one
    # separator after the (stripped) base. Documented edge behaviour.
    monkey_settings(XUI_SUB_BASE_URL="https://host/sub")
    assert build_subscription_url("") == "https://host/sub/"
    monkey_settings(XUI_SUB_BASE_URL="https://host/sub/")
    assert build_subscription_url("") == "https://host/sub/"
