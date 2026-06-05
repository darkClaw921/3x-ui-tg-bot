"""Wallet screen — balance, transaction history, and top-up.

Handlers
--------

* :func:`cb_open`  — ``WalletCB(action='open')``: render the «👛 Кошелёк»
  screen (current balance + the last :func:`app.db.repos.wallet.list_for_user`
  transactions).
* :func:`cb_topup` — ``WalletCB(action='topup')``: show the top-up preset menu
  (the Stars amounts in :data:`app.config.settings.WALLET_TOPUP_PRESETS`).
* :func:`cb_pick`  — ``WalletCB(action='pick', stars=...)``: send a Stars
  top-up invoice for the chosen preset via
  :func:`app.services.billing.send_topup_invoice`. The actual balance credit
  happens later in :func:`app.handlers.user.buy.on_successful_payment` when
  Telegram confirms the payment.

All texts are localized through :func:`app.i18n.t` (``wallet.*`` namespace).
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from loguru import logger

from app.config import settings
from app.db.engine import get_conn
from app.db.repos import wallet as wallet_repo
from app.db.repos.users import User
from app.db.repos.wallet import WalletTxn
from app.i18n import DEFAULT_LANG, t
from app.keyboards.user import WalletCB, wallet_screen_kb, wallet_topup_kb
from app.services import billing

router = Router(name="user_wallet")


def _txn_label(txn: WalletTxn, lang: str) -> str:
    """Return a localized human label for a ledger row's ``type``.

    Falls back to the raw ``type`` string when (unexpectedly) no ``wallet.type_*``
    key exists, so a new ledger type added later still renders something.
    """
    return t(f"wallet.type_{txn.type}", lang)


def _render_wallet_text(balance: int, txns: list[WalletTxn], lang: str) -> str:
    """Build the «👛 Кошелёк» screen body: title + balance + history.

    Each history row is ``<sign><abs amount>⭐ · <label>`` where the sign is
    ``+`` for credits and ``−`` for debits (the ledger stores debits as negative
    so ``txn.amount`` already carries the sign; we surface ``abs`` with an
    explicit sign for readability).
    """
    lines = [
        t("wallet.screen_title", lang),
        t("wallet.balance_line", lang, balance=balance),
        "",
        t("wallet.history_title", lang),
    ]
    if not txns:
        lines.append(t("wallet.history_empty", lang))
    else:
        for txn in txns:
            sign = "+" if txn.amount >= 0 else "−"
            lines.append(
                t(
                    "wallet.history_row",
                    lang,
                    sign=sign,
                    amount=abs(txn.amount),
                    label=_txn_label(txn, lang),
                )
            )
    return "\n".join(lines)


@router.callback_query(WalletCB.filter(F.action == "open"))
async def cb_open(
    callback: CallbackQuery,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Render the wallet screen: balance + recent transactions."""
    if user is None:
        await callback.answer(t("menu.need_start", lang), show_alert=True)
        return

    async with get_conn() as conn:
        balance = await wallet_repo.balance(conn, user.id)
        txns = await wallet_repo.list_for_user(conn, user.id, limit=20)

    has_presets = bool(settings.WALLET_TOPUP_PRESETS)
    text = _render_wallet_text(balance, txns, lang)
    if callback.message is not None:
        await callback.message.edit_text(
            text,
            reply_markup=wallet_screen_kb(has_presets=has_presets, lang=lang),
        )
    await callback.answer()


@router.callback_query(WalletCB.filter(F.action == "topup"))
async def cb_topup(
    callback: CallbackQuery,
    lang: str = DEFAULT_LANG,
) -> None:
    """Show the top-up preset menu."""
    presets = list(settings.WALLET_TOPUP_PRESETS)
    if callback.message is not None:
        if not presets:
            await callback.message.edit_text(
                t("wallet.no_presets", lang),
                reply_markup=wallet_screen_kb(has_presets=False, lang=lang),
            )
        else:
            await callback.message.edit_text(
                t("wallet.topup_prompt", lang),
                reply_markup=wallet_topup_kb(presets, lang=lang),
            )
    await callback.answer()


@router.callback_query(WalletCB.filter(F.action == "pick"))
async def cb_pick(
    callback: CallbackQuery,
    callback_data: WalletCB,
    bot: Bot,
    lang: str = DEFAULT_LANG,
) -> None:
    """Send a Stars top-up invoice for the chosen preset amount.

    The balance is credited later, in
    :func:`app.handlers.user.buy.on_successful_payment`, once Telegram confirms
    the payment — this handler only *initiates* the invoice.
    """
    stars = int(callback_data.stars or 0)
    if stars <= 0:
        await callback.answer(t("wallet.no_presets", lang), show_alert=True)
        return
    chat_id = callback.message.chat.id if callback.message is not None else None
    if chat_id is None:
        await callback.answer(t("buy.chat_undetermined", lang), show_alert=True)
        return
    try:
        await billing.send_topup_invoice(bot, chat_id, stars, lang=lang)
    except ValueError as exc:
        logger.warning("wallet topup: bad preset {} stars: {}", stars, exc)
        await callback.answer(t("wallet.no_presets", lang), show_alert=True)
        return
    await callback.answer()


__all__ = ["router"]
