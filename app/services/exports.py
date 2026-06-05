"""CSV exports of the bot's core tables for the admin dashboard.

The admin "Статистика" screen can dump three datasets as UTF-8 CSV files:
payments, subscriptions and users. Each exporter streams a table to an
in-memory buffer and returns ``bytes`` ready to hand to
``aiogram.types.BufferedInputFile`` — no temp files touch disk.

Design notes
------------

* Standard-library :mod:`csv` writing into a :class:`io.StringIO`, then encoded
  ``utf-8-sig`` (BOM) so Excel on Windows opens Cyrillic correctly. ``\r\n`` line
  endings (the CSV default via ``newline=''`` semantics of ``StringIO``) keep
  the output RFC-4180-friendly.
* Every exporter writes a *header row* first, then one row per record. The
  column order is fixed and documented per function so downstream consumers can
  rely on it.
* Rows are pulled straight from the table with a single ``SELECT ... ORDER BY
  id`` — the heavy lifting stays in SQLite; we only materialise to build the
  CSV. ``NULL`` columns render as the empty string (csv default).

All functions are ``async`` and accept a caller-owned
:class:`aiosqlite.Connection` (same DI pattern as the repos / stats service).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence

import aiosqlite

# Excel-friendly UTF-8 with BOM so Cyrillic opens correctly on Windows.
_ENCODING = "utf-8-sig"


def _rows_to_csv_bytes(
    header: Sequence[str], rows: Iterable[Sequence[object]]
) -> bytes:
    """Render ``header`` + ``rows`` to CSV ``bytes`` (``utf-8-sig``).

    ``None`` values are written as empty cells (the :mod:`csv` default). Values
    are stringified by the writer, so ints/strs/None all work without
    pre-formatting.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow(["" if v is None else v for v in row])
    return buffer.getvalue().encode(_ENCODING)


async def export_payments_csv(conn: aiosqlite.Connection) -> bytes:
    """Export the ``payments`` table as CSV bytes.

    Columns (in order): ``id, user_id, subscription_id, telegram_charge_id,
    stars_amount, plan_id, promo_id, status, created_at``. Ordered by ``id``.
    """
    header = (
        "id",
        "user_id",
        "subscription_id",
        "telegram_charge_id",
        "stars_amount",
        "plan_id",
        "promo_id",
        "status",
        "created_at",
    )
    cursor = await conn.execute(
        "SELECT id, user_id, subscription_id, telegram_charge_id, "
        "stars_amount, plan_id, promo_id, status, created_at "
        "FROM payments ORDER BY id"
    )
    rows = await cursor.fetchall()
    return _rows_to_csv_bytes(header, [tuple(r) for r in rows])


async def export_subscriptions_csv(conn: aiosqlite.Connection) -> bytes:
    """Export the ``subscriptions`` table as CSV bytes.

    Columns (in order): ``id, user_id, xui_inbound_id, xui_client_email,
    xui_sub_id, plan_id, status, is_trial, auto_renew, expires_at,
    created_at``. The cryptographic ``xui_client_uuid`` is deliberately omitted
    — it is a connection secret and has no place in an analytics export. Ordered
    by ``id``.
    """
    header = (
        "id",
        "user_id",
        "xui_inbound_id",
        "xui_client_email",
        "xui_sub_id",
        "plan_id",
        "status",
        "is_trial",
        "auto_renew",
        "expires_at",
        "created_at",
    )
    cursor = await conn.execute(
        "SELECT id, user_id, xui_inbound_id, xui_client_email, xui_sub_id, "
        "plan_id, status, is_trial, auto_renew, expires_at, created_at "
        "FROM subscriptions ORDER BY id"
    )
    rows = await cursor.fetchall()
    return _rows_to_csv_bytes(header, [tuple(r) for r in rows])


async def export_users_csv(conn: aiosqlite.Connection) -> bytes:
    """Export the ``users`` table as CSV bytes.

    Columns (in order): ``id, tg_id, username, first_name, is_admin, lang,
    is_blocked, created_at``. Ordered by ``id``.
    """
    header = (
        "id",
        "tg_id",
        "username",
        "first_name",
        "is_admin",
        "lang",
        "is_blocked",
        "created_at",
    )
    cursor = await conn.execute(
        "SELECT id, tg_id, username, first_name, is_admin, lang, "
        "is_blocked, created_at "
        "FROM users ORDER BY id"
    )
    rows = await cursor.fetchall()
    return _rows_to_csv_bytes(header, [tuple(r) for r in rows])


__all__ = [
    "export_payments_csv",
    "export_subscriptions_csv",
    "export_users_csv",
]
