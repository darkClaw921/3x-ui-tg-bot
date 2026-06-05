"""Referral program — bind invitees and reward inviters once they pay.

The flow has two halves, both idempotent:

* **Binding** (:func:`register_referral`) — when a new user follows a
  ``t.me/<bot>?start=ref_<tg_id>`` link, :func:`parse_ref_arg` extracts the
  inviter's Telegram id and this function records a ``pending`` row in
  ``referrals`` (one per invitee, enforced by ``UNIQUE(referred_id)``). It
  guards against self-referral and only binds on the user's *first* contact
  (a later ``ref_…`` link is ignored if they are already bound).

* **Reward** (:func:`reward_referrer_after_first_payment`) — after the invitee
  makes their *first* payment, this flips the referral to ``rewarded`` (atomic,
  exactly once) and credits the inviter's wallet with
  :data:`app.config.settings.REFERRAL_BONUS_STARS` via
  :func:`app.services.wallet.credit` (``type='referral_bonus'``, deterministic
  ``ref=f"referral:<referred_id>"``), then DMs the inviter.

Idempotency layers
------------------

The bonus is paid at most once even under retries / races thanks to:

1. :func:`app.db.repos.referrals.try_mark_rewarded` — guarded ``UPDATE WHERE
   status='pending'``; only one caller can flip it.
2. The deterministic wallet ``ref`` — the partial-unique ``idx_wallet_ref``
   rejects a duplicate ``referral:<id>`` credit.

Both are belt-and-suspenders: either alone would suffice, together they make a
double-credit impossible.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from loguru import logger

import aiosqlite

from app.config import settings
from app.db.repos import referrals as referrals_repo
from app.db.repos import users as users_repo
from app.db.repos.users import User
from app.i18n import t

# Deep-link prefix mirrored from ``app.handlers.start`` so the parsing logic
# lives next to the rest of the referral domain. Kept in lockstep with the
# ``_REF_PREFIX`` constant the /start router recognises.
_REF_PREFIX = "ref_"


def parse_ref_arg(arg: str | None) -> int | None:
    """Extract the inviter's Telegram id from a ``ref_<tg_id>`` deep-link.

    Returns the integer ``tg_id`` for a well-formed ``ref_<digits>`` argument,
    or ``None`` for anything else (missing / empty / non-``ref`` / non-numeric
    payload). The ``/start`` router already classifies the deep-link prefix;
    this helper additionally validates that the value is a positive integer so
    a crafted ``ref_abc`` cannot reach the DB layer.
    """
    if not arg:
        return None
    cleaned = arg.strip()
    if not cleaned.startswith(_REF_PREFIX):
        return None
    value = cleaned[len(_REF_PREFIX):]
    if not value.isdigit():
        return None
    tg_id = int(value)
    return tg_id if tg_id > 0 else None


async def register_referral(
    conn: aiosqlite.Connection,
    *,
    referrer_tg_id: int,
    referred: User,
) -> bool:
    """Bind ``referred`` to the inviter identified by ``referrer_tg_id``.

    Returns ``True`` when a fresh ``pending`` referral row was created, ``False``
    otherwise (self-referral, unknown inviter, or the invitee was already bound).

    Guards:

    * **Self-referral** — if ``referrer_tg_id`` resolves to ``referred`` itself
      (same ``users.id``) we refuse to bind.
    * **Already bound** — if a referral row already exists for ``referred``
      (:func:`app.db.repos.referrals.get_by_referred`) we do not re-bind; the
      first inviter keeps the credit. This is what makes the binding "first
      ``/start`` wins".
    * **Unknown inviter** — if no registered user has ``tg_id =
      referrer_tg_id`` the link is treated as invalid and ignored.

    The underlying :func:`app.db.repos.referrals.create_pending` uses
    ``INSERT OR IGNORE`` so even a race past the ``get_by_referred`` check binds
    at most once.
    """
    referrer = await users_repo.get_by_tg_id(conn, int(referrer_tg_id))
    if referrer is None:
        logger.info(
            "register_referral: unknown inviter tg_id={} for referred user {}",
            referrer_tg_id,
            referred.id,
        )
        return False
    if referrer.id == referred.id:
        logger.info(
            "register_referral: self-referral rejected for user {}", referred.id
        )
        return False

    existing = await referrals_repo.get_by_referred(conn, referred.id)
    if existing is not None:
        logger.info(
            "register_referral: user {} already bound to referrer {}",
            referred.id,
            existing.referrer_id,
        )
        return False

    created = await referrals_repo.create_pending(
        conn, referrer_id=referrer.id, referred_id=referred.id
    )
    if created is None:
        # Lost a race against the UNIQUE(referred_id) constraint — already bound.
        return False
    logger.info(
        "register_referral: bound referred user {} to referrer {}",
        referred.id,
        referrer.id,
    )
    return True


async def reward_referrer_after_first_payment(
    conn: aiosqlite.Connection,
    bot: Bot,
    *,
    referred: User,
) -> bool:
    """Pay the referral bonus for ``referred``'s first payment — exactly once.

    Steps:

    1. Skip entirely when :data:`app.config.settings.REFERRAL_BONUS_STARS` is
       ``0`` (reward disabled) — referrals stay tracked but no Stars are paid.
    2. Look up ``referred``'s referral row; bail if absent (organic signup) or
       already ``rewarded``.
    3. Atomically flip it to ``rewarded`` via
       :func:`app.db.repos.referrals.try_mark_rewarded` — a ``None`` return
       means another worker already rewarded it, so we stop (no double-pay).
    4. Credit the inviter's wallet with ``REFERRAL_BONUS_STARS`` using the
       deterministic ``ref=f"referral:<referred_id>"`` (second idempotency
       layer) and DM them.

    Returns ``True`` when the bonus was credited by *this* call, ``False`` in
    every short-circuit case above. Safe to call after every payment — the
    no-referral / already-rewarded / disabled cases are cheap no-ops.
    """
    bonus = int(settings.REFERRAL_BONUS_STARS)
    if bonus <= 0:
        return False

    referral = await referrals_repo.get_by_referred(conn, referred.id)
    if referral is None or referral.status != "pending":
        return False

    marked = await referrals_repo.try_mark_rewarded(conn, referred.id)
    if marked is None:
        # Already rewarded or lost the race — nothing to pay.
        return False

    from app.services import wallet as wallet_service

    credited = await wallet_service.credit(
        conn,
        marked.referrer_id,
        bonus,
        type="referral_bonus",
        ref=f"referral:{referred.id}",
    )
    if not credited:
        # The deterministic ref already existed — the bonus was paid before
        # (e.g. a prior partially-applied run). The referral is rewarded; we
        # simply skip the duplicate credit + DM.
        logger.info(
            "reward_referrer: duplicate referral credit ref=referral:{} — skipped",
            referred.id,
        )
        return False

    # DM the inviter (best-effort — a blocked-bot / deactivated account must not
    # fail the payment that triggered this).
    referrer = await users_repo.get_by_id(conn, marked.referrer_id)
    if referrer is not None:
        try:
            await bot.send_message(
                referrer.tg_id,
                t("referral.reward_dm", referrer.lang, stars=bonus),
            )
        except TelegramAPIError as exc:
            logger.warning(
                "reward_referrer: DM to referrer {} failed: {}",
                referrer.tg_id,
                exc,
            )

    logger.info(
        "reward_referrer: credited {} Stars to referrer {} for referred {}",
        bonus,
        marked.referrer_id,
        referred.id,
    )
    return True


__all__ = [
    "parse_ref_arg",
    "register_referral",
    "reward_referrer_after_first_payment",
]
