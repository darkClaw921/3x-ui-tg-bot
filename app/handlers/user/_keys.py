"""Shared helper for delivering subscription keys to a user.

Used by both :mod:`app.handlers.user.buy` (after a successful payment)
and :mod:`app.handlers.user.promo` (after a free-days activation). The
output is a triple of (summary text, vless URI + QR PNG, subscription
URL) plus a single keyboard with two link buttons — see the relevant
handler docstrings for the precise wording.

The function lives here (rather than inside :mod:`app.services`) because
it owns Telegram-side formatting and ``aiogram`` types; keeping it next
to the handlers keeps :mod:`app.services` framework-agnostic.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.types import (
    BufferedInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from loguru import logger

from app.db.repos.subscriptions import Subscription
from app.keyboards.user import subscription_kb
from app.xui import XuiClient, XuiError
from app.xui.inbounds import get_inbound
from app.xui.links import build_subscription_url, build_vless_link, make_qr_png


async def deliver_keys(
    bot: Bot,
    xui: XuiClient,
    chat_id: int,
    sub: Subscription,
    *,
    header: str = "✅ Подписка активна.",
) -> None:
    """Send the user their vless URI, a QR PNG, and the subscription URL.

    Layout (three Telegram messages):

    1. Plain-text summary with the expiry date and a clickable ``vless://``
       wrapped in monospace.
    2. The QR PNG as a photo (caption: short hint about scanning).
    3. Subscription URL in a separate message plus two URL buttons
       («vless://» link, «Subscription URL» link) and a "back / re-send"
       keyboard.

    The 3x-ui panel call (:func:`app.xui.inbounds.get_inbound`) is needed
    to extract ``streamSettings`` for the vless URI. If it fails we
    degrade gracefully by sending the subscription URL and QR over the
    plain vless URL — the user is still able to connect.
    """
    sub_url = build_subscription_url(sub.xui_sub_id) if sub.xui_sub_id else ""

    vless_uri: str
    try:
        inbound = await get_inbound(xui, sub.xui_inbound_id)
        vless_uri = build_vless_link(inbound, sub.xui_client_uuid, sub.xui_client_email)
    except XuiError as exc:
        # The panel will only refuse this when something is structurally
        # off (deleted inbound etc.); log loudly so an admin can react,
        # but don't break the user's purchase flow — the subscription URL
        # is enough for v2rayNG / Streisand / Hiddify to fetch the
        # config.
        logger.warning(
            "deliver_keys: get_inbound({}) failed for sub={}: {}",
            sub.xui_inbound_id,
            sub.id,
            exc,
        )
        vless_uri = ""

    summary_lines = [
        header,
        "",
        f"Срок действия: <code>{sub.expires_at}</code> UTC",
    ]
    if vless_uri:
        summary_lines.append("")
        summary_lines.append(f"<code>{vless_uri}</code>")
    summary_text = "\n".join(summary_lines)
    await bot.send_message(chat_id, summary_text)

    # QR for the vless URI (preferred — it carries the whole config). Fall
    # back to the subscription URL if the panel call failed above.
    qr_target = vless_uri or sub_url
    if qr_target:
        png_bytes = make_qr_png(qr_target)
        await bot.send_photo(
            chat_id,
            photo=BufferedInputFile(png_bytes, filename="vpn-qr.png"),
            caption="📱 Отсканируйте QR-код в клиенте, чтобы добавить подключение.",
        )

    # Final message: subscription URL (in code-block for copy) + two
    # URL buttons + a "re-send keys / back to menu" keyboard.
    if sub_url:
        url_text = f"<b>Subscription URL</b>\n<code>{sub_url}</code>"
    else:
        url_text = "<b>Subscription URL</b>\n<i>недоступен</i>"

    # Build the final keyboard. Telegram only accepts ``http(s)://``,
    # ``tg://``, ``mailto:`` and a few other schemes for ``InlineKeyboardButton.url``
    # — ``vless://`` is NOT accepted. So we surface the vless URI as a
    # tappable copyable code block (already in ``summary_text`` above) and
    # only use a URL button for the subscription URL. The
    # "Получить ключ ещё раз" / "В меню" buttons come from
    # :func:`app.keyboards.user.subscription_kb`.
    url_rows: list[list[InlineKeyboardButton]] = []
    if sub_url:
        url_rows.append(
            [InlineKeyboardButton(text="🌐 Subscription URL", url=sub_url)]
        )
    sub_kb = subscription_kb(sub.id)
    combined = InlineKeyboardMarkup(
        inline_keyboard=url_rows + list(sub_kb.inline_keyboard)
    )

    await bot.send_message(chat_id, url_text, reply_markup=combined)


__all__ = ["deliver_keys"]
