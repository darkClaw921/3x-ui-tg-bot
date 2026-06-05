"""Locale catalogs for the i18n module.

Each module in this package exposes a single ``MESSAGES`` dict mapping a
namespaced key (``<area>.<name>``) to either:

* a plain ``str`` (optionally containing ``str.format_map`` placeholders), or
* a ``dict`` of plural categories (``one``/``few``/``many``/``other``) used by
  :func:`app.i18n.pluralize`.

``ru`` is the source of truth (verbatim copies of the strings previously
hard-coded in handlers/keyboards); ``en`` is the full fallback translation.
``uk``/``fa``/``zh`` are intentionally thin stubs — keys missing from them fall
back to ``en`` (then to the raw key) via :func:`app.i18n.t`.
"""

from __future__ import annotations

__all__: list[str] = []
