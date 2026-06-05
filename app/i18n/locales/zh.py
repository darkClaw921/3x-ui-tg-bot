"""Chinese locale catalog (stub).

Intentionally a thin stub: keys not present here fall back to the English
catalog (:data:`app.i18n.FALLBACK_LANG`) via :func:`app.i18n.t`. Add real
translations incrementally; the fallback chain keeps the bot fully usable in
the meantime.
"""

from __future__ import annotations

MESSAGES: dict[str, str | dict[str, str]] = {}


__all__ = ["MESSAGES"]
