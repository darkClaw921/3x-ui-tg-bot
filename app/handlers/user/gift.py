"""Gift redemption flow — the «🎁 У меня есть подарок» code-entry screen.

Two activation paths exist for a gift code:

* **Deep-link** — ``t.me/<bot>?start=gift_<code>`` is handled directly in
  :func:`app.handlers.start.cmd_start` (no FSM).
* **Manual entry** — this module: the «🎁 У меня есть подарок» button enters
  :class:`app.states.user.GiftRedeem.waiting_code`, the recipient types the
  ``GIFT-…`` code, and it is redeemed here.

Both paths converge on :func:`app.services.gifts.redeem_gift` (atomic claim →
provision → link, with compensation on panel failure) followed by
:func:`app.handlers.user._keys.deliver_keys` for the recipient and a best-effort
DM to the buyer (:func:`notify_gift_buyer`, shared with the deep-link path).
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger

from app.db.engine import get_conn
from app.db.repos import users as users_repo
from app.db.repos.gift_codes import GiftCode
from app.db.repos.users import User
from app.handlers.user._keys import deliver_keys
from app.i18n import DEFAULT_LANG, t
from app.keyboards.user import GiftCB, cancel_kb
from app.services import gifts as gifts_service
from app.states.user import GiftRedeem
from app.xui import XuiError, get_xui_client

router = Router(name="user_gift")


async def notify_gift_buyer(bot: Bot, gift: GiftCode) -> None:
    """DM the gift buyer that their code was redeemed (best-effort).

    Shared by both redemption paths (deep-link in :mod:`app.handlers.start` and
    the manual-entry flow here). Resolves the buyer's Telegram id + language and
    sends a short confirmation; a blocked-bot / deactivated buyer must never
    fail the recipient's redemption, so all errors are swallowed with a warning.
    """
    try:
        async with get_conn() as conn:
            buyer = await users_repo.get_by_id(conn, int(gift.buyer_id))
        if buyer is None:
            return
        await bot.send_message(
            buyer.tg_id,
            t("gift.buyer_notified_dm", buyer.lang, code=gift.code),
        )
    except TelegramAPIError as exc:
        logger.warning(
            "notify_gift_buyer: DM to buyer {} failed: {}", gift.buyer_id, exc
        )


@router.callback_query(GiftCB.filter(F.action == "redeem"))
async def cb_redeem(
    callback: CallbackQuery,
    state: FSMContext,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Enter :class:`GiftRedeem.waiting_code` and prompt for the code."""
    if user is None:
        await callback.answer(t("gift.need_start", lang), show_alert=True)
        return
    await state.set_state(GiftRedeem.waiting_code)
    if callback.message is not None:
        await callback.message.edit_text(
            t("gift.enter_code", lang),
            reply_markup=cancel_kb(lang),
        )
    await callback.answer()


@router.message(GiftRedeem.waiting_code)
async def msg_code(
    message: Message,
    state: FSMContext,
    bot: Bot,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Redeem the typed gift code and deliver keys to the recipient.

    On a missing / inactive code the user is told why and stays in
    :class:`GiftRedeem.waiting_code` so they can retry or cancel. On success the
    keys are delivered, the buyer is notified, and the FSM is cleared.
    """
    if user is None:
        await message.answer(t("gift.need_start", lang))
        return

    code = (message.text or "").strip()
    if not code:
        await message.answer(t("gift.enter_code", lang), reply_markup=cancel_kb(lang))
        return

    xui = await get_xui_client()
    try:
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
        await message.answer(t(key, lang), reply_markup=cancel_kb(lang))
        return
    except XuiError as exc:
        logger.error("gift msg_code: redeem xui failed for code {}: {}", code, exc)
        await message.answer(t("gift.redeem_failed", lang), reply_markup=cancel_kb(lang))
        return

    await state.clear()
    await deliver_keys(
        bot,
        xui,
        chat_id=message.chat.id,
        sub=sub,
        header=t("gift.redeemed_header", lang),
        lang=lang,
    )
    await notify_gift_buyer(bot, gift)


__all__ = ["router", "notify_gift_buyer"]
