"""In-memory message catalog assembled from the per-language locale modules.

This module wires the locale dicts (:mod:`app.i18n.locales`) into a single
``CATALOG`` mapping ``lang -> {key: value}`` consumed by :func:`app.i18n.t` and
:func:`app.i18n.pluralize`. Loading happens once at import time — the catalogs
are static Python dicts, so there is no I/O and no runtime parsing cost.

``lookup(key, lang)`` implements the resolution policy:

    requested lang → FALLBACK_LANG (en) → ``None``

It deliberately does NOT fall back to the raw ``key`` — that final step lives in
:func:`app.i18n.t` so callers always get a printable string, while internal
callers (e.g. :func:`app.i18n.pluralize`) can distinguish "key absent" from
"key present but empty".
"""

from __future__ import annotations

from app.i18n.locales import en, fa, ru, uk, zh

# Mapping of supported language code -> message dict. Order is not significant;
# the resolution order is enforced by :func:`lookup` via ``FALLBACK_LANG``.
CATALOG: dict[str, dict[str, str | dict[str, str]]] = {
    "ru": ru.MESSAGES,
    "en": en.MESSAGES,
    "uk": uk.MESSAGES,
    "fa": fa.MESSAGES,
    "zh": zh.MESSAGES,
}

# The language every other language falls back to when a key is missing. Kept
# here (rather than imported from :mod:`app.i18n`) to avoid a circular import —
# :mod:`app.i18n` imports this module, not the other way round.
_FALLBACK_LANG = "en"


def lookup(key: str, lang: str) -> str | dict[str, str] | None:
    """Return the catalog value for ``key`` resolving ``lang → en``.

    Returns ``None`` when the key exists in neither the requested language nor
    the English fallback. The value may be a plain ``str`` or a plural-category
    ``dict`` — the caller decides how to render it.
    """
    table = CATALOG.get(lang)
    if table is not None:
        value = table.get(key)
        if value is not None:
            return value
    if lang != _FALLBACK_LANG:
        fallback_table = CATALOG.get(_FALLBACK_LANG)
        if fallback_table is not None:
            return fallback_table.get(key)
    return None


__all__ = ["CATALOG", "lookup"]
