"""Lightweight, dependency-free internationalization (i18n) for the bot.

Why a custom module (and not aiogram's gettext middleware)? The test-suite
calls handlers directly (no dispatcher, no middleware context), and aiogram's
gettext relies on a context-var populated by its middleware. A pure function
``t(key, lang, **params)`` keeps handlers testable and lets every call site pass
the language explicitly (defaulting to Russian so legacy call sites that omit
``lang`` keep producing the original Russian strings).

Public API
----------

* :func:`t` — translate a key for a language with safe ``format_map``.
* :func:`pluralize` — pick the correct plural form for a count.
* :func:`resolve_lang` — normalize a Telegram ``language_code`` to a supported
  language (falling back to :data:`DEFAULT_LANG`).
* :data:`SUPPORTED_LANGS`, :data:`DEFAULT_LANG`, :data:`FALLBACK_LANG`,
  :data:`LANG_NAMES`.

Resolution policy (mirrored in :func:`app.i18n.catalog.lookup`):

    requested lang → FALLBACK_LANG ("en") → the raw key itself

so a call never raises ``KeyError`` and never returns ``None``.
"""

from __future__ import annotations

from app.i18n.catalog import lookup
from app.i18n.plural import plural_category

# Languages the bot ships catalogs for. ``ru``/``en`` are full; the rest are
# stubs that fall back to ``en``.
SUPPORTED_LANGS: tuple[str, ...] = ("ru", "en", "uk", "fa", "zh")

# Default language used when none is supplied and for unknown ``language_code``s.
# Russian by design — legacy call sites omit ``lang`` and must keep producing
# the original Russian strings so the existing tests stay green.
DEFAULT_LANG = "ru"

# Language every other language falls back to when a key is missing.
FALLBACK_LANG = "en"

# Human-readable, self-describing language names (used by the language picker).
LANG_NAMES: dict[str, str] = {
    "ru": "🇷🇺 Русский",
    "en": "🇬🇧 English",
    "uk": "🇺🇦 Українська",
    "fa": "🇮🇷 فارسی",
    "zh": "🇨🇳 中文",
}


class _SafeDict(dict):
    """``dict`` subclass that renders missing ``format_map`` keys as ``{key}``.

    Using this with :meth:`str.format_map` makes substitution total: a template
    referencing a placeholder the caller forgot to pass renders the literal
    ``{placeholder}`` instead of raising ``KeyError``. This protects the bot
    from crashing on a typo in a translation string.
    """

    def __missing__(self, key: str) -> str:  # noqa: D105 — see class docstring
        return "{" + key + "}"


def _safe_format(template: str, params: dict[str, object]) -> str:
    """Apply ``params`` to ``template`` via ``format_map``, never raising.

    Besides missing keys (handled by :class:`_SafeDict`), a malformed template
    (stray ``{`` / ``}`` or an unsupported format spec) would raise
    ``ValueError``/``IndexError`` — we swallow those and return the template
    verbatim so a bad string degrades gracefully instead of crashing a handler.
    """
    if not params:
        return template
    try:
        return template.format_map(_SafeDict(params))
    except (ValueError, IndexError, KeyError):
        return template


def resolve_lang(language_code: str | None) -> str:
    """Normalize a Telegram ``language_code`` to a supported language code.

    Telegram sends IETF tags like ``"en"``, ``"en-US"``, ``"ru"``, ``"zh-Hans"``.
    We match on the primary subtag (lower-cased text before the first ``-``).
    Unknown or missing codes resolve to :data:`DEFAULT_LANG`.
    """
    if not language_code:
        return DEFAULT_LANG
    primary = language_code.strip().lower().split("-", 1)[0]
    if primary in SUPPORTED_LANGS:
        return primary
    return DEFAULT_LANG


def t(key: str, lang: str | None = None, /, **params: object) -> str:
    """Translate ``key`` into ``lang`` and apply ``**params`` substitutions.

    ``lang`` and ``key`` are positional-only so ``**params`` can include any
    keyword (even ``key``/``lang``) without colliding with the signature.

    Resolution: requested ``lang`` → :data:`FALLBACK_LANG` → the raw ``key``.
    When the resolved value is a plural-category ``dict`` (an entry meant for
    :func:`pluralize`), the raw ``key`` is returned to signal misuse rather than
    rendering an arbitrary form.

    Substitution is total and crash-proof (see :func:`_safe_format`): missing
    placeholders render as ``{name}`` and malformed templates return verbatim.
    """
    resolved_lang = lang if lang is not None else DEFAULT_LANG
    value = lookup(key, resolved_lang)
    if value is None or isinstance(value, dict):
        # Missing key, or a plural-only entry queried via ``t`` by mistake.
        return key
    return _safe_format(value, params)


def pluralize(key: str, n: int, lang: str | None = None, /, **params: object) -> str:
    """Return the plural form of ``key`` for count ``n`` in ``lang``.

    The catalog entry for ``key`` must be a dict of plural categories
    (``one``/``few``/``many``/``other``). The category for ``n`` is chosen by
    :func:`app.i18n.plural.plural_category` for the requested language; if that
    exact category is absent we degrade to ``other`` → ``one`` → any value.

    ``n`` is exposed to the chosen template as the ``n`` placeholder (so a form
    like ``"{n} subscriptions"`` works) alongside any extra ``**params``.
    Returns the raw ``key`` when no plural entry exists in any language.
    """
    resolved_lang = lang if lang is not None else DEFAULT_LANG
    value = lookup(key, resolved_lang)
    if not isinstance(value, dict):
        # Not a plural entry (missing, or a plain string). Return the key so the
        # mistake is visible rather than silently rendering a wrong form.
        return key

    category = plural_category(n, resolved_lang)
    form = (
        value.get(category)
        or value.get("other")
        or value.get("one")
        or next(iter(value.values()), key)
    )
    merged: dict[str, object] = {"n": n, **params}
    return _safe_format(form, merged)


__all__ = [
    "DEFAULT_LANG",
    "FALLBACK_LANG",
    "LANG_NAMES",
    "SUPPORTED_LANGS",
    "pluralize",
    "resolve_lang",
    "t",
]
