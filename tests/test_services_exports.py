"""Tests for :mod:`app.services.exports` (CSV dumps of core tables)."""

from __future__ import annotations

import csv
import io

from app.services import exports as exports_service


def _parse(data: bytes) -> list[list[str]]:
    """Decode CSV bytes (utf-8-sig) into a list of rows."""
    assert isinstance(data, bytes)
    text = data.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


# --------------------------------------------------------------------------- #
# Empty tables — header only, still valid CSV
# --------------------------------------------------------------------------- #


async def test_exports_empty_tables_have_headers(file_db):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        for builder, first_col in (
            (exports_service.export_payments_csv, "id"),
            (exports_service.export_subscriptions_csv, "id"),
            (exports_service.export_users_csv, "id"),
        ):
            rows = _parse(await builder(conn))
            assert len(rows) == 1  # header only
            assert rows[0][0] == first_col


# --------------------------------------------------------------------------- #
# Populated tables — header + data rows
# --------------------------------------------------------------------------- #


async def test_export_users_csv(file_db, make_user):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        await make_user(conn, tg_id=111, username="alice", first_name="Алиса")
        data = await exports_service.export_users_csv(conn)

    rows = _parse(data)
    assert rows[0] == [
        "id",
        "tg_id",
        "username",
        "first_name",
        "is_admin",
        "lang",
        "is_blocked",
        "created_at",
    ]
    assert len(rows) == 2
    # Cyrillic survives the utf-8-sig round-trip.
    assert "Алиса" in rows[1]
    assert "alice" in rows[1]


async def test_export_payments_csv(file_db, make_user, make_plan):
    from app.db.engine import get_conn
    from app.db.repos import payments as payments_repo

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=222)
        plan = await make_plan(conn, inbound_ids=[1])
        await payments_repo.create(
            conn,
            user_id=user.id,
            subscription_id=None,
            telegram_charge_id="charge-1",
            stars_amount=150,
            plan_id=plan.id,
            promo_id=None,
            status="paid",
        )
        data = await exports_service.export_payments_csv(conn)

    rows = _parse(data)
    assert rows[0] == [
        "id",
        "user_id",
        "subscription_id",
        "telegram_charge_id",
        "stars_amount",
        "plan_id",
        "promo_id",
        "status",
        "created_at",
    ]
    assert len(rows) == 2
    assert "charge-1" in rows[1]
    assert "150" in rows[1]
    # NULL columns render as empty cells (promo_id / subscription_id).
    assert rows[1][2] == ""  # subscription_id NULL
    assert rows[1][6] == ""  # promo_id NULL


async def test_export_subscriptions_csv_omits_uuid_secret(
    file_db, make_user, make_plan, make_subscription
):
    from app.db.engine import get_conn

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=333)
        plan = await make_plan(conn, inbound_ids=[1])
        await make_subscription(
            conn,
            user_id=user.id,
            plan_id=plan.id,
            xui_inbound_id=1,
            xui_client_uuid="TOP-SECRET-UUID",
            xui_client_email="bob@x",
        )
        data = await exports_service.export_subscriptions_csv(conn)

    text = data.decode("utf-8-sig")
    rows = _parse(data)
    assert rows[0] == [
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
    ]
    assert len(rows) == 2
    assert "bob@x" in rows[1]
    # The cryptographic uuid is a connection secret and must NOT be exported.
    assert "TOP-SECRET-UUID" not in text
