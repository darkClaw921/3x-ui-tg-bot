"""Tests for :mod:`app.services.wallet` — credit and atomic spend."""

from __future__ import annotations

import pytest

from app.db.repos import wallet as wallet_repo
from app.services import wallet as wallet_service


# --------------------------------------------------------------------------- #
# credit
# --------------------------------------------------------------------------- #


async def test_credit_adds_balance(db_conn, make_user):
    user = await make_user(db_conn)
    ok = await wallet_service.credit(db_conn, user.id, 100, type="topup", ref="topup:1")
    assert ok is True
    assert await wallet_repo.balance(db_conn, user.id) == 100


async def test_credit_duplicate_ref_is_noop(db_conn, make_user):
    user = await make_user(db_conn)
    assert await wallet_service.credit(db_conn, user.id, 100, type="topup", ref="r") is True
    # Same ref → rejected, balance unchanged (idempotent top-up).
    assert await wallet_service.credit(db_conn, user.id, 100, type="topup", ref="r") is False
    assert await wallet_repo.balance(db_conn, user.id) == 100


async def test_credit_null_ref_always_applies(db_conn, make_user):
    user = await make_user(db_conn)
    assert await wallet_service.credit(db_conn, user.id, 5, type="admin_grant") is True
    assert await wallet_service.credit(db_conn, user.id, 5, type="admin_grant") is True
    assert await wallet_repo.balance(db_conn, user.id) == 10


async def test_credit_rejects_non_positive_amount(db_conn, make_user):
    user = await make_user(db_conn)
    with pytest.raises(ValueError):
        await wallet_service.credit(db_conn, user.id, 0, type="topup")
    with pytest.raises(ValueError):
        await wallet_service.credit(db_conn, user.id, -5, type="topup")


# --------------------------------------------------------------------------- #
# try_spend
# --------------------------------------------------------------------------- #


async def test_try_spend_succeeds_when_funded(db_conn, make_user):
    user = await make_user(db_conn)
    await wallet_service.credit(db_conn, user.id, 100, type="topup", ref="topup:1")
    assert await wallet_service.try_spend(db_conn, user.id, 40, ref="buy:1") is True
    assert await wallet_repo.balance(db_conn, user.id) == 60


async def test_try_spend_overdraw_is_rejected(db_conn, make_user):
    user = await make_user(db_conn)
    await wallet_service.credit(db_conn, user.id, 30, type="topup", ref="topup:1")
    # Spend exceeds balance → rejected, ledger untouched.
    assert await wallet_service.try_spend(db_conn, user.id, 31, ref="buy:1") is False
    assert await wallet_repo.balance(db_conn, user.id) == 30


async def test_try_spend_exact_balance_succeeds(db_conn, make_user):
    user = await make_user(db_conn)
    await wallet_service.credit(db_conn, user.id, 50, type="topup", ref="topup:1")
    assert await wallet_service.try_spend(db_conn, user.id, 50, ref="buy:1") is True
    assert await wallet_repo.balance(db_conn, user.id) == 0


async def test_try_spend_replay_same_ref_does_not_double_spend(db_conn, make_user):
    user = await make_user(db_conn)
    await wallet_service.credit(db_conn, user.id, 100, type="topup", ref="topup:1")
    assert await wallet_service.try_spend(db_conn, user.id, 40, ref="buy:dup") is True
    # Replay with the SAME ref → rejected by the partial-unique index.
    assert await wallet_service.try_spend(db_conn, user.id, 40, ref="buy:dup") is False
    assert await wallet_repo.balance(db_conn, user.id) == 60


async def test_two_sequential_spends_second_misses_when_drained(db_conn, make_user):
    """Two sequential spends: the second is rejected once funds run out.

    Exercises the BEGIN IMMEDIATE re-read — after the first spend commits the
    balance the second spend re-computes a now-insufficient balance and is
    rejected rather than overdrawing.
    """
    user = await make_user(db_conn)
    await wallet_service.credit(db_conn, user.id, 100, type="topup", ref="topup:1")
    assert await wallet_service.try_spend(db_conn, user.id, 70, ref="buy:1") is True
    # Only 30 left — a second 70-spend must fail.
    assert await wallet_service.try_spend(db_conn, user.id, 70, ref="buy:2") is False
    assert await wallet_repo.balance(db_conn, user.id) == 30
    # A 30-spend succeeds and empties the wallet.
    assert await wallet_service.try_spend(db_conn, user.id, 30, ref="buy:3") is True
    assert await wallet_repo.balance(db_conn, user.id) == 0


async def test_try_spend_rejects_non_positive_amount(db_conn, make_user):
    user = await make_user(db_conn)
    with pytest.raises(ValueError):
        await wallet_service.try_spend(db_conn, user.id, 0, ref="buy:1")
    with pytest.raises(ValueError):
        await wallet_service.try_spend(db_conn, user.id, -10, ref="buy:1")
