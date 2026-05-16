"""Database layer package.

Public surface:

* :func:`app.db.engine.init_db` — initialize the SQLite schema at startup.
* :func:`app.db.engine.get_conn` — async context manager yielding an
  :class:`aiosqlite.Connection` with row factory set to :class:`aiosqlite.Row`.
* :func:`app.db.engine.transaction` — async context manager wrapping a
  ``BEGIN IMMEDIATE`` / ``COMMIT`` / ``ROLLBACK`` block for critical sections.

Repositories live in :mod:`app.db.repos`.
"""
