"""Repository modules — thin async wrappers around aiosqlite queries.

Each repository module exposes plain ``async def`` functions that accept an
:class:`aiosqlite.Connection` and operate on a single table (or a tightly
related pair of tables). No ORM is used — queries are hand-written SQL.

Modules:

* :mod:`app.db.repos.users` — users CRUD.
* :mod:`app.db.repos.plans` — tariff plans CRUD.
* :mod:`app.db.repos.promos` — promo codes CRUD and atomic redemption.
* :mod:`app.db.repos.subscriptions` — subscriptions and traffic snapshots.
* :mod:`app.db.repos.payments` — Stars payment history.
"""
