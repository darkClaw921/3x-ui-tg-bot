"""``/start`` command router.

Branches on the resolved domain user (injected by
:class:`app.middlewares.user_ctx.UserContextMiddleware` into ``data['user']``):

* If the user has ``is_admin=True`` — show the admin main menu so admins land
  straight into management. Mirror of ``/admin``.
* Otherwise — show the user main menu (:func:`app.keyboards.user.user_main_menu`)
  with the "Моя подписка" / "Купить" priority decided by the presence of an
  active subscription.

Deep-link arguments
-------------------

Telegram passes anything after ``/start`` (e.g. ``t.me/bot?start=ref_123``)
as :attr:`aiogram.filters.CommandObject.args`. We recognise two prefixes and
parse them *before* the greeting so later phases can wire the real flows:

* ``ref_<tg_id>`` — referral link (real reward logic lands in Ф3).
* ``gift_<code>`` — gift-code redemption (real redeem logic lands in Ф3).

For now :func:`_parse_deep_link` only classifies + logs the payload; the
handlers branch on the result so the wiring point is ready.
"""

from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message
from loguru import logger

from app.config import settings
from app.db.engine import get_conn
from app.db.repos import subscriptions as subs_repo
from app.db.repos.users import User
from app.handlers.user._keys import deliver_keys
from app.i18n import DEFAULT_LANG, t
from app.keyboards.admin import admin_main_menu
from app.keyboards.user import user_main_menu
from app.services import gifts as gifts_service
from app.services import referrals as referrals_service
from app.xui import XuiError, get_xui_client

router = Router(name="start")

# Deep-link prefixes recognised in the ``/start`` argument.
_REF_PREFIX = "ref_"
_GIFT_PREFIX = "gift_"


def _parse_deep_link(args: str | None) -> tuple[str, str] | None:
    """Classify a ``/start`` deep-link argument.

    Returns ``(kind, value)`` where ``kind`` is ``"ref"`` or ``"gift"``:

    * ``"ref_123"``  → ``("ref", "123")``
    * ``"gift_ABC"`` → ``("gift", "ABC")``

    Returns ``None`` for an empty / unrecognised argument (plain ``/start``),
    or when the prefix is present but the value is empty (e.g. ``ref_``) —
    callers treat that as "no actionable deep-link".
    """
    if not args:
        return None
    arg = args.strip()
    if arg.startswith(_REF_PREFIX):
        value = arg[len(_REF_PREFIX):]
        return ("ref", value) if value else None
    if arg.startswith(_GIFT_PREFIX):
        value = arg[len(_GIFT_PREFIX):]
        return ("gift", value) if value else None
    return None


async def _handle_ref_deep_link(value: str, user: User | None) -> None:
    """Bind the new user to a referrer from a ``ref_<tg_id>`` deep-link.

    Resolves the inviter via :func:`app.services.referrals.parse_ref_arg` +
    :func:`register_referral`. Binding only happens on the user's *first*
    ``/start`` (the service no-ops a re-bind) and self-referrals are rejected.
    A missing / anonymous ``user`` (no domain row) is skipped.
    """
    if user is None:
        return
    referrer_tg_id = referrals_service.parse_ref_arg(f"ref_{value}")
    if referrer_tg_id is None:
        return
    try:
        async with get_conn() as conn:
            await referrals_service.register_referral(
                conn, referrer_tg_id=referrer_tg_id, referred=user
            )
    except Exception as exc:  # noqa: BLE001 — binding must never break /start
        logger.warning(
            "start: register_referral failed for ref_{} user {}: {}",
            value,
            user.id,
            exc,
        )


async def _handle_gift_deep_link(
    message: Message,
    bot: Bot,
    code: str,
    user: User | None,
    lang: str,
) -> bool:
    """Redeem a ``gift_<code>`` deep-link and deliver keys to the recipient.

    Returns ``True`` when the gift was redeemed (keys delivered) so the caller
    skips the normal greeting, ``False`` otherwise (unknown code / inactive /
    panel error / anonymous user) so the user still lands in the main menu with
    a short error notice already sent.
    """
    if user is None:
        return False
    try:
        xui = await get_xui_client()
        async with get_conn() as conn:
            gift, sub = await gifts_service.redeem_gift(
                conn, xui, code=code, redeemer=user
            )
    except gifts_service.GiftRedeemError as exc:
        key = (
            "gift.code_not_found"
            if exc.reason == "not_found"
            else "gift.code_not_active"
        )
        await message.answer(t(key, lang))
        return False
    except XuiError as exc:
        logger.error("start: gift redeem xui failed for code {}: {}", code, exc)
        await message.answer(t("gift.redeem_failed", lang))
        return False

    await deliver_keys(
        bot,
        xui,
        chat_id=message.chat.id,
        sub=sub,
        header=t("gift.redeemed_header", lang),
        lang=lang,
    )
    from app.handlers.user.gift import notify_gift_buyer

    await notify_gift_buyer(bot, gift)
    return True


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject | None = None,
    bot: Bot | None = None,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Greet the user. Admins land in the admin menu, everyone else in the user menu.

    Parses an optional deep-link argument before greeting:

    * ``ref_<tg_id>`` — bind the new user to the inviting referrer
      (:func:`_handle_ref_deep_link`); the inviter's bonus is paid later, after
      the new user's first payment (:mod:`app.services.referrals`).
    * ``gift_<code>`` — redeem a gift code for this user
      (:func:`_handle_gift_deep_link`); on success the keys are delivered and we
      return early (no greeting on top).

    Plain ``/start`` (no argument) behaves exactly as before.
    """
    deep_link = _parse_deep_link(command.args if command is not None else None)
    if deep_link is not None:
        kind, value = deep_link
        if kind == "ref":
            await _handle_ref_deep_link(value, user)
        elif kind == "gift" and bot is not None:
            # Redeeming a gift needs the gift service + key delivery; handle it
            # and return early so the greeting menu is not also sent on top of
            # the delivered keys.
            if await _handle_gift_deep_link(message, bot, value, user, lang):
                return

    if user is not None and user.is_admin:
        await message.answer(
            t("menu.admin_greeting", lang),
            reply_markup=admin_main_menu(),
        )
        return

    has_sub = False
    can_trial = False
    if user is not None:
        async with get_conn() as conn:
            existing = await subs_repo.get_active_for_user(conn, user.id)
            has_sub = existing is not None
            if int(settings.TRIAL_DAYS) > 0:
                can_trial = not await subs_repo.has_trial(conn, user.id)

    await message.answer(
        t("menu.start_greeting", lang),
        reply_markup=user_main_menu(has_subscription=has_sub, can_trial=can_trial),
    )
