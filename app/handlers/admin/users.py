"""Admin "Пользователи" — search + user card with subs, traffic, payments.

Flow overview
-------------

Search (``UserCB(action='search')``):
    Sets :class:`AdminSearchUser.waiting_query`. The admin replies with
    either a digit-only string (interpreted as ``tg_id``) or an
    ``@username`` / bare ``username`` (case-insensitive lookup).

User card (``UserCB(action='card', id=<users.id>)``):
    Renders:

    * Header — first_name, tg_id, username, is_admin, created_at.
    * Active subscriptions with live 3x-ui traffic (wrapped in
      try/except :class:`XuiError` — panel outages must not crash the
      card).
    * Inactive subscriptions (expired / revoked) — compact list.
    * Last 10 payments — charge id, stars, plan, promo, status.
    * Inline keyboard: «Отозвать активную подписку» (when there is one),
      «Сделать/Снять админа», «Найти другого», «В меню».

Revoke (``UserCB(action='revoke', id=<sub_id>, user_id=<users.id>)``):
    Delegates to :func:`app.services.subscriptions.revoke` — the single
    point that owns the "disable panel client + flip DB status to
    revoked" sequence. Re-renders the card afterwards.

Toggle admin (``UserCB(action='toggle_admin', id=<users.id>)``):
    Flips :attr:`User.is_admin` via
    :func:`app.db.repos.users.set_admin`. Note: the admin status is
    re-synchronised with ``settings.ADMIN_IDS`` on the next update by
    :class:`UserContextMiddleware`, so granting admin to a tg_id NOT
    in ``ADMIN_IDS`` will be reverted on their next message. The
    button is still useful for revoking from users that are no longer
    in the env file.

All handlers live behind :class:`AdminOnlyMiddleware` (router-level on
the parent admin router); no per-handler admin checks needed.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger

from app.db.engine import get_conn
from app.db.repos import payments as payments_repo
from app.db.repos import subscriptions as subs_repo
from app.db.repos import users as users_repo
from app.db.repos.payments import Payment
from app.db.repos.subscriptions import Subscription
from app.db.repos.users import User
from app.handlers.user.my_subscription import (  # internal helper reuse
    _format_bytes,
    _is_active,
)
from app.keyboards.admin import AdminCB, UserCB, cancel_kb, user_card_kb
from app.services import subscriptions as subs_service
from app.states.admin import AdminSearchUser
from app.xui import XuiError, get_xui_client
from app.xui.clients import get_client_traffics

router = Router(name="admin_users")


# --------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------- #


_MAX_PAYMENTS = 10


def _safe(value: object) -> str:
    """Return ``value`` as a plain string for HTML rendering.

    Telegram HTML mode is forgiving inside ``<code>`` tags, but
    usernames and first-names may contain ``<``/``>``/``&``. We strip
    those characters to keep the message valid without pulling in a
    full HTML-escaper.
    """
    if value is None:
        return "—"
    text = str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def _fetch_traffic_line(sub: Subscription) -> str:
    """Return the traffic display line for one active subscription.

    Hits :func:`app.xui.clients.get_client_traffics`; on any panel
    error returns a soft "панель недоступна" notice rather than
    propagating. Returns ``""`` for inactive subs (caller decides not
    to print traffic for expired/revoked rows).
    """
    if not _is_active(sub):
        return ""
    try:
        xui = await get_xui_client()
        info = await get_client_traffics(xui, sub.xui_client_email)
    except XuiError as exc:
        logger.warning(
            "admin_users: traffic fetch failed sub={}: {}", sub.id, exc
        )
        return "📊 Трафик: панель недоступна"
    except Exception as exc:  # noqa: BLE001 — defensive: never crash the card
        logger.warning(
            "admin_users: unexpected traffic error sub={}: {}", sub.id, exc
        )
        return "📊 Трафик: ошибка"
    if not info:
        return "📊 Трафик: клиент не найден в панели"
    try:
        up = int(info.get("up", 0))
        down = int(info.get("down", 0))
    except (TypeError, ValueError):
        return "📊 Трафик: некорректный ответ"
    return f"📊 Трафик: ↑ {_format_bytes(up)} / ↓ {_format_bytes(down)}"


def _sub_status_glyph(sub: Subscription) -> str:
    """Return the emoji for the subscription's effective status."""
    if sub.status == "revoked":
        return "🚫"
    if _is_active(sub):
        return "✅"
    return "❌"


def _format_payment(p: Payment) -> str:
    """Return a single-line summary of a payment."""
    plan_part = f" plan#{p.plan_id}" if p.plan_id is not None else ""
    promo_part = f" promo#{p.promo_id}" if p.promo_id is not None else ""
    status_glyph = "✅" if p.status == "paid" else "↩"
    return (
        f"{status_glyph} {p.stars_amount}⭐ "
        f"<code>{_safe(p.telegram_charge_id)}</code>"
        f"{plan_part}{promo_part} · {p.created_at}"
    )


async def _build_card(target: User) -> tuple[str, int | None, bool]:
    """Build the HTML card body for ``target``.

    Returns ``(text, active_sub_id, is_admin)`` so the caller can wire
    the keyboard's "Отозвать" / "Сделать админа" buttons correctly
    without re-querying.
    """
    async with get_conn() as conn:
        all_subs = await subs_repo.list_for_user(conn, target.id)
        all_payments = await payments_repo.list_for_user(conn, target.id)

    header = [
        f"<b>Пользователь #{target.id}</b>",
        f"Имя: <b>{_safe(target.first_name)}</b>",
        f"tg_id: <code>{target.tg_id}</code>",
        f"username: <code>@{_safe(target.username) if target.username else '—'}</code>",
        f"Админ: {'✅ да' if target.is_admin else '— нет'}",
        f"Зарегистрирован: <code>{target.created_at}</code>",
    ]

    active = [s for s in all_subs if _is_active(s)]
    inactive = [s for s in all_subs if not _is_active(s)]
    active_sub_id: int | None = None

    sub_lines: list[str] = [""]
    if not all_subs:
        sub_lines.append("<b>Подписки:</b> нет")
    else:
        sub_lines.append("<b>Подписки:</b>")
        if active:
            # Pick the latest as the "primary" — that's what the revoke
            # button targets.
            primary = max(active, key=lambda s: s.expires_at)
            active_sub_id = primary.id
            for sub in sorted(active, key=lambda s: s.expires_at, reverse=True):
                traffic_line = await _fetch_traffic_line(sub)
                sub_lines.append(
                    f"{_sub_status_glyph(sub)} #{sub.id} "
                    f"plan#{sub.plan_id} · до <code>{sub.expires_at}</code> UTC"
                )
                if traffic_line:
                    sub_lines.append(f"   {traffic_line}")
        for sub in inactive[:5]:
            sub_lines.append(
                f"{_sub_status_glyph(sub)} #{sub.id} "
                f"plan#{sub.plan_id} · до <code>{sub.expires_at}</code> · {sub.status}"
            )
        if len(inactive) > 5:
            sub_lines.append(f"   … и ещё {len(inactive) - 5} истёкших/отозванных")

    pay_lines: list[str] = ["", "<b>Платежи:</b>"]
    if not all_payments:
        pay_lines.append("нет")
    else:
        for p in all_payments[:_MAX_PAYMENTS]:
            pay_lines.append(f"• {_format_payment(p)}")
        if len(all_payments) > _MAX_PAYMENTS:
            pay_lines.append(f"… и ещё {len(all_payments) - _MAX_PAYMENTS}")

    text = "\n".join(header + sub_lines + pay_lines)
    # Telegram message hard limit is 4096; if we ever blow past it (many
    # subs + many payments), truncate trailing lines politely.
    if len(text) > 4000:
        text = text[:3900] + "\n…\n(вывод обрезан)"
    return text, active_sub_id, target.is_admin


async def _render_card_message(
    message: Message,
    target: User,
    *,
    edit: bool = True,
) -> None:
    """Render ``target``'s card, either editing or sending a new message."""
    text, active_sub_id, is_admin = await _build_card(target)
    kb = user_card_kb(
        target.id,
        active_sub_id=active_sub_id,
        is_admin=is_admin,
    )
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


async def _resolve_user_query(query: str) -> User | None:
    """Resolve a free-form search query to a :class:`User` row.

    Accepts:

    * digit-only string — interpreted as ``tg_id`` and looked up via
      :func:`users_repo.get_by_tg_id`.
    * ``@handle`` / bare ``handle`` — case-insensitive lookup via
      :func:`users_repo.get_by_username`.

    Returns ``None`` if nothing matches.
    """
    cleaned = query.strip()
    if not cleaned:
        return None
    async with get_conn() as conn:
        if cleaned.isdigit():
            return await users_repo.get_by_tg_id(conn, int(cleaned))
        return await users_repo.get_by_username(conn, cleaned)


# --------------------------------------------------------------------- #
# Navigation callbacks
# --------------------------------------------------------------------- #


@router.callback_query(AdminCB.filter((F.area == "users") & (F.action == "open")))
async def cb_open_users(callback: CallbackQuery, state: FSMContext) -> None:
    """Entry point from the admin main menu — kick off the search FSM."""
    await state.set_state(AdminSearchUser.waiting_query)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите <b>tg_id</b> (только цифры) или <b>@username</b>:",
            reply_markup=cancel_kb(),
        )
    await callback.answer()


@router.callback_query(UserCB.filter(F.action == "search"))
async def cb_search(callback: CallbackQuery, state: FSMContext) -> None:
    """Re-enter the search FSM (e.g. from a user card's "Найти другого")."""
    await state.set_state(AdminSearchUser.waiting_query)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите <b>tg_id</b> (только цифры) или <b>@username</b>:",
            reply_markup=cancel_kb(),
        )
    await callback.answer()


@router.message(AdminSearchUser.waiting_query)
async def st_query(message: Message, state: FSMContext) -> None:
    """Accept the search query, resolve a user, render the card."""
    raw = (message.text or "").strip()
    if not raw:
        await message.answer(
            "Запрос не может быть пустым. Введите tg_id или @username:",
            reply_markup=cancel_kb(),
        )
        return

    target = await _resolve_user_query(raw)
    if target is None:
        await state.clear()
        await message.answer(
            f"Пользователь по запросу «{_safe(raw)}» не найден.",
            reply_markup=user_card_kb(0, active_sub_id=None, is_admin=False),
        )
        return

    await state.clear()
    await _render_card_message(message, target, edit=False)


@router.callback_query(UserCB.filter(F.action == "card"))
async def cb_card(
    callback: CallbackQuery,
    callback_data: UserCB,
) -> None:
    """Open a user card by ``users.id`` (used by callbacks that already know it)."""
    async with get_conn() as conn:
        target = await users_repo.get_by_id(conn, callback_data.id)
    if target is None:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return
    if callback.message is not None:
        await _render_card_message(callback.message, target, edit=True)
    await callback.answer()


# --------------------------------------------------------------------- #
# Mutations
# --------------------------------------------------------------------- #


@router.callback_query(UserCB.filter(F.action == "revoke"))
async def cb_revoke(
    callback: CallbackQuery,
    callback_data: UserCB,
) -> None:
    """Revoke a subscription (services.subscriptions.revoke) and refresh card."""
    sub_id = callback_data.id
    user_id = callback_data.user_id
    if not sub_id or not user_id:
        await callback.answer("Некорректный запрос.", show_alert=True)
        return

    async with get_conn() as conn:
        sub = await subs_repo.get(conn, sub_id)
        target = await users_repo.get_by_id(conn, user_id)

    if sub is None or target is None:
        await callback.answer("Подписка или пользователь не найдены.", show_alert=True)
        return
    if sub.user_id != target.id:
        # Defensive: a crafted callback should not be able to revoke a
        # subscription that does not belong to the displayed user.
        await callback.answer("Подписка не принадлежит этому пользователю.", show_alert=True)
        return

    try:
        xui = await get_xui_client()
        await subs_service.revoke(xui, sub)
    except Exception as exc:  # noqa: BLE001 — surface to admin, don't crash
        logger.error(
            "admin_users: revoke failed sub={} user={}: {}",
            sub.id,
            target.id,
            exc,
        )
        await callback.answer(
            f"Не удалось отозвать подписку: {exc}",
            show_alert=True,
        )
        return

    logger.info(
        "admin_users: revoked sub={} for user={} by admin",
        sub.id,
        target.id,
    )
    if callback.message is not None:
        await _render_card_message(callback.message, target, edit=True)
    await callback.answer("Подписка отозвана")


@router.callback_query(UserCB.filter(F.action == "toggle_admin"))
async def cb_toggle_admin(
    callback: CallbackQuery,
    callback_data: UserCB,
) -> None:
    """Flip the ``is_admin`` flag for the target user."""
    user_id = callback_data.id
    async with get_conn() as conn:
        target = await users_repo.get_by_id(conn, user_id)
        if target is None:
            await callback.answer("Пользователь не найден.", show_alert=True)
            return
        new_value = not target.is_admin
        await users_repo.set_admin(conn, target.id, new_value)
        # Re-read so the card shows the new state.
        refreshed = await users_repo.get_by_id(conn, target.id)
    if refreshed is None:
        await callback.answer("Пользователь исчез после обновления.", show_alert=True)
        return
    logger.info(
        "admin_users: toggle_admin user={} → is_admin={}",
        refreshed.id,
        refreshed.is_admin,
    )
    if callback.message is not None:
        await _render_card_message(callback.message, refreshed, edit=True)
    await callback.answer(
        "Назначен админом" if new_value else "Снят флаг админа",
    )


__all__ = ["router"]
