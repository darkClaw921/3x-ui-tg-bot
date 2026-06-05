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
from app.i18n import DEFAULT_LANG, t
from app.keyboards.user import subscription_kb
from app.xui import XuiClient, XuiError
from app.xui.inbounds import get_inbound
from app.xui.links import (
    build_import_links,
    build_subscription_url,
    build_vless_link,
    make_qr_png,
)


def build_howto_text(sub_url: str, lang: str = DEFAULT_LANG) -> str:
    """Compose the localized "How to connect" guide for a subscription URL.

    Telegram rejects the clients' custom-scheme deep links
    (``v2rayng://`` / ``hiddify://`` / ``streisand://``) both as inline-button
    URLs and as HTML ``<a href>`` links, so we render each one inside a
    copyable ``<code>`` block (the user taps to copy, then pastes into the
    client or opens it manually). The deep links themselves come from
    :func:`app.xui.links.build_import_links`.

    Returns the HTML body (title + intro + one block per client + a manual
    fallback hint). When ``sub_url`` is empty there is nothing to import, so an
    empty string is returned and callers skip the message.
    """
    if not sub_url:
        return ""
    links = build_import_links(sub_url)
    parts = [
        t("keys.howto.title", lang),
        "",
        t("keys.howto.intro", lang),
        "",
        t("keys.howto.happ", lang, link=links["happ"], sub_url=sub_url),
        "",
        t("keys.howto.v2rayng", lang, link=links["v2rayng"]),
        "",
        t("keys.howto.hiddify", lang, link=links["hiddify"]),
        "",
        t("keys.howto.streisand", lang, link=links["streisand"]),
        "",
        t("keys.howto.manual", lang),
    ]
    return "\n".join(parts)


async def deliver_keys(
    bot: Bot,
    xui: XuiClient,
    chat_id: int,
    sub: Subscription,
    *,
    header: str | None = None,
    lang: str = DEFAULT_LANG,
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
    if header is None:
        header = t("keys.header_active", lang)
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
        t("keys.valid_until", lang, expires_at=sub.expires_at),
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
            caption=t("keys.qr_caption", lang),
        )

    # Final message: subscription URL (in code-block for copy) + two
    # URL buttons + a "re-send keys / back to menu" keyboard.
    if sub_url:
        url_text = t("keys.sub_url_title", lang, sub_url=sub_url)
    else:
        url_text = t("keys.sub_url_unavailable", lang)

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
            [InlineKeyboardButton(text=t("keys.btn_sub_url", lang), url=sub_url)]
        )
    sub_kb = subscription_kb(sub.id)
    combined = InlineKeyboardMarkup(
        inline_keyboard=url_rows + list(sub_kb.inline_keyboard)
    )

    await bot.send_message(chat_id, url_text, reply_markup=combined)

    # Connection guide: per-client deep-link import URLs as copyable code
    # blocks (Telegram rejects their custom schemes as buttons/links). Only
    # sent when we actually have a subscription URL to import.
    howto_text = build_howto_text(sub_url, lang)
    if howto_text:
        await bot.send_message(chat_id, howto_text)


__all__ = ["build_howto_text", "deliver_keys"]
