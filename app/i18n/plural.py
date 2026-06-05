"""Pluralization helpers for the i18n module.

Different languages use different plural rules. This module provides a small
registry of *plural selector* functions — one per language — that map a count
``n`` to a plural *category* key (``"one"``, ``"few"``, ``"many"``, ``"other"``).

A locale catalog entry that depends on grammatical number stores a ``dict`` of
the relevant category keys instead of a flat string, e.g.::

    "mysub.subs_plural": {
        "one": "подписка",
        "few": "подписки",
        "many": "подписок",
    }

:func:`pluralize` (see :mod:`app.i18n`) resolves the category for ``n`` via the
selector for the requested language and picks the matching string.

The Russian selector mirrors ``_pluralize_subs`` in
:mod:`app.handlers.user.my_subscription` exactly (three nominal buckets:
``1`` / ``2-4`` / ``5-20``) so existing tests that assert the Russian forms of
«подписка/подписки/подписок» keep passing.
"""

from __future__ import annotations

from collections.abc import Callable


def _plural_ru(n: int) -> str:
    """Return the Russian plural category for ``n``.

    Russian has three forms:

    * ``one``  — 1, 21, 31, … (but NOT 11)
    * ``few``  — 2-4, 22-24, … (but NOT 12-14)
    * ``many`` — 0, 5-20, 25-30, …

    Mirrors the buckets of ``_pluralize_subs`` in
    :mod:`app.handlers.user.my_subscription`.
    """
    n = abs(int(n))
    mod10 = n % 10
    mod100 = n % 100
    if mod10 == 1 and mod100 != 11:
        return "one"
    if 2 <= mod10 <= 4 and not (12 <= mod100 <= 14):
        return "few"
    return "many"


def _plural_en(n: int) -> str:
    """Return the English plural category for ``n`` (``one`` for 1, else ``other``)."""
    return "one" if abs(int(n)) == 1 else "other"


def _plural_other(n: int) -> str:  # noqa: ARG001 — uniform selector signature
    """Single-form selector for languages without distinct plural forms.

    Used as the fallback selector (and for ``uk``/``fa``/``zh`` stubs which
    fall back to the English catalog). Always returns ``"other"``.
    """
    return "other"


# Per-language plural selector. Languages without a dedicated selector fall
# back to ``_plural_other`` via :func:`plural_category`.
_SELECTORS: dict[str, Callable[[int], str]] = {
    "ru": _plural_ru,
    "en": _plural_en,
    "uk": _plural_ru,  # Ukrainian shares Russian's one/few/many rule.
}


def plural_category(n: int, lang: str) -> str:
    """Return the plural category (``one``/``few``/``many``/``other``) for ``n``.

    Falls back to :func:`_plural_other` (always ``"other"``) for languages with
    no registered selector.
    """
    selector = _SELECTORS.get(lang, _plural_other)
    return selector(n)


__all__ = ["plural_category"]
