"""Referral screen — the «👥 Пригласить друга» invite link + counter.

Renders the user's personal invite link
(``https://t.me/<bot_username>?start=ref_<tg_id>``) plus how many friends they
have invited so far (:func:`app.db.repos.referrals.count_for_referrer`). The
actual binding happens in :func:`app.handlers.start.cmd_start` when an invitee
follows the link; the reward is paid after their first payment by
:mod:`app.services.referrals`.

The bot username is resolved once via :meth:`aiogram.Bot.get_me` and cached
module-side, because it never changes during a process lifetime and
``get_me`` is a network round-trip we don't want to repeat on every render.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot_meta import get_bot_username
from app.db.engine import get_conn
from app.db.repos import referrals as referrals_repo
from app.db.repos.users import User
from app.config import settings
from app.i18n import DEFAULT_LANG, t
from app.keyboards.user import ReferralCB, UserCB

router = Router(name="user_referral")


def _build_ref_link(bot_username: str, tg_id: int) -> str:
    """Return the personal ``t.me`` invite link for ``tg_id``."""
    return f"https://t.me/{bot_username}?start=ref_{tg_id}"


@router.callback_query(ReferralCB.filter(F.action == "open"))
async def cb_open(
    callback: CallbackQuery,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Render the referral screen: invite link + invited-friends counter.

    When :data:`app.config.settings.REFERRAL_BONUS_STARS` > 0 the body
    advertises the Stars bonus; when the reward is disabled it shows the
    neutral "share your link" copy instead (referrals are still tracked).
    """
    if user is None:
        await callback.answer(t("referral.need_start", lang), show_alert=True)
        return

    bot = callback.bot
    bot_username = await get_bot_username(bot)
    link = _build_ref_link(bot_username, user.tg_id)

    async with get_conn() as conn:
        count = await referrals_repo.count_for_referrer(conn, user.id)

    bonus = int(settings.REFERRAL_BONUS_STARS)
    body = (
        t("referral.screen_body", lang, stars=bonus)
        if bonus > 0
        else t("referral.screen_body_no_bonus", lang)
    )
    text = "\n\n".join(
        [
            t("referral.screen_title", lang),
            body,
            t("referral.link_line", lang, link=link),
            t("referral.count_line", lang, count=count),
        ]
    )

    builder = InlineKeyboardBuilder()
    builder.button(text=t("menu.btn_back", lang), callback_data=UserCB(area="menu"))
    builder.adjust(1)
    if callback.message is not None:
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


__all__ = ["router"]
