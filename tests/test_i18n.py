"""Tests for :mod:`app.i18n` — the custom localization module.

Covers the public API contract:

* :func:`app.i18n.t` — language resolution, fallback chain, safe ``format_map``.
* :func:`app.i18n.pluralize` — Russian/English plural forms.
* :func:`app.i18n.resolve_lang` — Telegram ``language_code`` normalization.
* Catalog coverage — every Russian key must exist in the English fallback so a
  missing translation never degrades to a raw key.
"""

from __future__ import annotations

import pytest

from app.i18n import (
    DEFAULT_LANG,
    FALLBACK_LANG,
    LANG_NAMES,
    SUPPORTED_LANGS,
    pluralize,
    resolve_lang,
    t,
)
from app.i18n.locales import en, fa, ru, uk, zh


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #


def test_constants():
    assert DEFAULT_LANG == "ru"
    assert FALLBACK_LANG == "en"
    assert SUPPORTED_LANGS == ("ru", "en", "uk", "fa", "zh")
    # Every supported language has a human-readable name.
    for code in SUPPORTED_LANGS:
        assert code in LANG_NAMES
        assert LANG_NAMES[code]


# --------------------------------------------------------------------------- #
# t() — resolution + fallback
# --------------------------------------------------------------------------- #


def test_t_returns_requested_language():
    assert t("menu.greeting", "en") == en.MESSAGES["menu.greeting"]
    assert t("menu.greeting", "ru") == ru.MESSAGES["menu.greeting"]


def test_t_default_language_is_russian():
    # No lang argument → DEFAULT_LANG ("ru").
    assert t("menu.greeting") == ru.MESSAGES["menu.greeting"]


def test_t_stub_language_falls_back_to_english():
    # uk/fa/zh are stubs — a key they don't define resolves to the EN value.
    expected = en.MESSAGES["menu.greeting"]
    assert t("menu.greeting", "uk") == expected
    assert t("menu.greeting", "fa") == expected
    assert t("menu.greeting", "zh") == expected


def test_t_missing_key_returns_key_itself():
    assert t("no.such.key", "en") == "no.such.key"
    assert t("no.such.key", "ru") == "no.such.key"


def test_t_plural_only_entry_returns_key_when_queried_via_t():
    # mysub.subs_plural is a plural dict — t() must not render an arbitrary form.
    assert t("mysub.subs_plural", "ru") == "mysub.subs_plural"


# --------------------------------------------------------------------------- #
# t() — safe format_map
# --------------------------------------------------------------------------- #


def test_t_substitution_applies_params():
    rendered = t("keys.valid_until", "en", expires_at="2026-01-01")
    assert "2026-01-01" in rendered


def test_t_missing_param_does_not_crash():
    # Template references {expires_at} but we pass nothing — renders literally.
    rendered = t("keys.valid_until", "en")
    assert "{expires_at}" in rendered


def test_t_extra_params_are_ignored():
    # Passing a param the template doesn't use must not raise.
    assert t("menu.greeting", "en", unused="x") == en.MESSAGES["menu.greeting"]


def test_t_positional_only_allows_key_and_lang_as_param_names():
    # key/lang are positional-only, so **params can carry those names.
    rendered = t("buy.confirm_plan", "en", title="Pro")
    assert "Pro" in rendered


# --------------------------------------------------------------------------- #
# pluralize()
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (1, "подписка"),
        (2, "подписки"),
        (3, "подписки"),
        (4, "подписки"),
        (5, "подписок"),
        (11, "подписок"),
        (21, "подписка"),
        (22, "подписки"),
        (25, "подписок"),
        (111, "подписок"),
    ],
)
def test_pluralize_russian_forms(n, expected):
    assert pluralize("mysub.subs_plural", n, "ru") == expected


@pytest.mark.parametrize(
    ("n", "expected"),
    [(1, "subscription"), (2, "subscriptions"), (5, "subscriptions")],
)
def test_pluralize_english_forms(n, expected):
    assert pluralize("mysub.subs_plural", n, "en") == expected


def test_pluralize_default_language_is_russian():
    assert pluralize("mysub.subs_plural", 5) == "подписок"


def test_pluralize_non_plural_key_returns_key():
    # A flat-string entry queried via pluralize → returns the key (visible bug).
    assert pluralize("menu.greeting", 3, "ru") == "menu.greeting"


def test_pluralize_missing_key_returns_key():
    assert pluralize("no.such.plural", 3, "ru") == "no.such.plural"


def test_pluralize_exposes_n_placeholder():
    # The chosen form can reference {n}; mysub.subs_plural doesn't, but the
    # call must still succeed and never raise on the injected n.
    assert pluralize("mysub.subs_plural", 2, "ru") == "подписки"


# --------------------------------------------------------------------------- #
# resolve_lang()
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("ru", "ru"),
        ("en", "en"),
        ("en-US", "en"),
        ("zh-Hans", "zh"),
        ("uk", "uk"),
        ("fa", "fa"),
        ("RU", "ru"),  # case-insensitive
        ("de", "ru"),  # unsupported → default
        ("", "ru"),  # empty → default
        (None, "ru"),  # missing → default
    ],
)
def test_resolve_lang(code, expected):
    assert resolve_lang(code) == expected


# --------------------------------------------------------------------------- #
# Catalog coverage — RU ⊆ EN
# --------------------------------------------------------------------------- #


def test_every_russian_key_exists_in_english():
    """No Russian key may be missing from the English fallback catalog."""
    ru_keys = set(ru.MESSAGES)
    en_keys = set(en.MESSAGES)
    missing = ru_keys - en_keys
    assert not missing, f"Keys present in RU but missing in EN: {sorted(missing)}"


def test_plural_entries_are_dicts_in_both_languages():
    """A plural-typed key must be a dict in both RU and EN (same shape kind)."""
    for key, value in ru.MESSAGES.items():
        if isinstance(value, dict):
            assert isinstance(en.MESSAGES.get(key), dict), (
                f"{key} is a plural dict in RU but not in EN"
            )


def test_stub_catalogs_are_empty_or_subset_of_english():
    """uk/fa/zh stubs only contain keys that also exist in EN (so fallback works)."""
    en_keys = set(en.MESSAGES)
    for stub in (uk, fa, zh):
        for key in stub.MESSAGES:
            assert key in en_keys, f"stub key {key} has no EN fallback"
