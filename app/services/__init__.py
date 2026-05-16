"""Business-logic services that orchestrate repositories and the 3x-ui client.

Submodules:

* :mod:`app.services.promos` — promo code validation / discount calculation /
  atomic redemption.
* :mod:`app.services.billing` — final price computation and Stars invoice
  construction.
* :mod:`app.services.subscriptions` — single source of truth for creating
  and extending a subscription (keeps the DB and the 3x-ui panel
  consistent).
"""

from __future__ import annotations
