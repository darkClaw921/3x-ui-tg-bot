"""Tests for :mod:`app.db.repos.plans`."""

from __future__ import annotations

import pytest

from app.db.repos import plans as plans_repo


async def test_create_and_get(db_conn):
    p = await plans_repo.create(db_conn, title="1 мес", days=30, price_stars=100)
    assert p.title == "1 мес"
    assert p.days == 30
    assert p.price_stars == 100
    assert p.is_active is True

    got = await plans_repo.get(db_conn, p.id)
    assert got is not None
    assert got.id == p.id


async def test_get_missing(db_conn):
    assert await plans_repo.get(db_conn, 999) is None


async def test_list_active_filters_and_sorts(db_conn):
    p1 = await plans_repo.create(db_conn, title="cheap", days=7, price_stars=50)
    p2 = await plans_repo.create(db_conn, title="mid", days=30, price_stars=100)
    p3 = await plans_repo.create(db_conn, title="dead", days=30, price_stars=80)
    await plans_repo.deactivate(db_conn, p3.id)

    active = await plans_repo.list_active(db_conn)
    ids = [p.id for p in active]
    assert ids == [p1.id, p2.id]  # sorted by price asc


async def test_list_all_includes_inactive(db_conn):
    p1 = await plans_repo.create(db_conn, title="a", days=1, price_stars=1)
    p2 = await plans_repo.create(db_conn, title="b", days=1, price_stars=1)
    await plans_repo.deactivate(db_conn, p2.id)

    all_plans = await plans_repo.list_all(db_conn)
    assert {p.id for p in all_plans} == {p1.id, p2.id}


async def test_update_title(db_conn):
    p = await plans_repo.create(db_conn, title="x", days=10, price_stars=50)
    updated = await plans_repo.update(db_conn, p.id, title="new")
    assert updated.title == "new"


async def test_update_multiple_fields(db_conn):
    p = await plans_repo.create(db_conn, title="x", days=10, price_stars=50)
    updated = await plans_repo.update(db_conn, p.id, days=20, price_stars=200)
    assert updated.days == 20
    assert updated.price_stars == 200


async def test_update_is_active_bool_coercion(db_conn):
    p = await plans_repo.create(db_conn, title="x", days=10, price_stars=50)
    updated = await plans_repo.update(db_conn, p.id, is_active=False)
    assert updated.is_active is False


async def test_update_empty_kwargs_returns_current(db_conn):
    p = await plans_repo.create(db_conn, title="x", days=10, price_stars=50)
    same = await plans_repo.update(db_conn, p.id)
    assert same.id == p.id


async def test_update_empty_kwargs_missing(db_conn):
    with pytest.raises(LookupError):
        await plans_repo.update(db_conn, 999)


async def test_update_unknown_field_rejected(db_conn):
    p = await plans_repo.create(db_conn, title="x", days=10, price_stars=50)
    with pytest.raises(ValueError):
        await plans_repo.update(db_conn, p.id, evil="x")


async def test_update_missing_plan(db_conn):
    with pytest.raises(LookupError):
        await plans_repo.update(db_conn, 9999, title="x")


async def test_deactivate(db_conn):
    p = await plans_repo.create(db_conn, title="x", days=10, price_stars=50)
    await plans_repo.deactivate(db_conn, p.id)
    got = await plans_repo.get(db_conn, p.id)
    assert got.is_active is False


# --------------------------------------------------------------------------- #
# traffic_gb coverage
# --------------------------------------------------------------------------- #


async def test_create_default_traffic_gb_is_zero(db_conn):
    """When ``traffic_gb`` is omitted, the row is persisted with the SQL default 0."""
    p = await plans_repo.create(db_conn, title="t", days=30, price_stars=100)
    assert p.traffic_gb == 0
    got = await plans_repo.get(db_conn, p.id)
    assert got is not None
    assert got.traffic_gb == 0


async def test_create_with_explicit_traffic_gb(db_conn):
    """Explicit ``traffic_gb`` is stored and read back."""
    p = await plans_repo.create(
        db_conn, title="50gb", days=30, price_stars=150, traffic_gb=50
    )
    assert p.traffic_gb == 50
    got = await plans_repo.get(db_conn, p.id)
    assert got is not None
    assert got.traffic_gb == 50


async def test_update_traffic_gb(db_conn):
    p = await plans_repo.create(
        db_conn, title="t", days=30, price_stars=100, traffic_gb=10
    )
    updated = await plans_repo.update(db_conn, p.id, traffic_gb=100)
    assert updated.traffic_gb == 100
    # Persisted value matches.
    got = await plans_repo.get(db_conn, p.id)
    assert got is not None
    assert got.traffic_gb == 100


async def test_list_active_returns_traffic_gb(db_conn):
    await plans_repo.create(
        db_conn, title="a", days=7, price_stars=50, traffic_gb=5
    )
    await plans_repo.create(
        db_conn, title="b", days=30, price_stars=100, traffic_gb=200
    )
    active = await plans_repo.list_active(db_conn)
    by_title = {p.title: p.traffic_gb for p in active}
    assert by_title["a"] == 5
    assert by_title["b"] == 200


async def test_list_all_returns_traffic_gb(db_conn):
    p1 = await plans_repo.create(
        db_conn, title="a", days=7, price_stars=50, traffic_gb=15
    )
    p2 = await plans_repo.create(
        db_conn, title="b", days=30, price_stars=100, traffic_gb=0
    )
    await plans_repo.deactivate(db_conn, p2.id)
    rows = {p.id: p.traffic_gb for p in await plans_repo.list_all(db_conn)}
    assert rows[p1.id] == 15
    assert rows[p2.id] == 0
