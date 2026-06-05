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

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger

from app.config import settings
from app.db.engine import get_conn
from app.db.repos import payments as payments_repo
from app.db.repos import plans as plans_repo
from app.db.repos import subscriptions as subs_repo
from app.db.repos import users as users_repo
from app.db.repos.payments import Payment
from app.db.repos.subscriptions import Subscription
from app.db.repos.users import User
from app.handlers.user._keys import deliver_keys
from app.handlers.user.my_subscription import (  # internal helper reuse
    _format_bytes,
    _is_active,
)
from app.i18n import DEFAULT_LANG, t
from app.keyboards.admin import (
    AdminCB,
    GrantCB,
    UserCB,
    cancel_kb,
    grant_plans_kb,
    user_card_kb,
)
from app.services import audit as audit_service
from app.services import subscriptions as subs_service
from app.states.admin import AdminGrantSub, AdminSearchUser
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
    without re-querying. The blocked state is read from ``target.is_blocked``
    by the caller for the block-toggle button.
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
        f"Блокировка: {'🚫 да' if target.is_blocked else '— нет'}",
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
        is_blocked=target.is_blocked,
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


def _admin_id(user: User | None) -> int | None:
    """Return the acting admin's ``users.id`` for audit rows, or ``None``.

    The admin user row is injected as ``data['user']`` by
    :class:`app.middlewares.user_ctx.UserContextMiddleware` and surfaced to the
    handler signature; mutation handlers declare ``user`` so the audit trail can
    record who acted.
    """
    return user.id if user is not None else None


@router.callback_query(UserCB.filter(F.action == "revoke"))
async def cb_revoke(
    callback: CallbackQuery,
    callback_data: UserCB,
    user: User | None = None,
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
    async with get_conn() as conn:
        await audit_service.log_action(
            conn,
            _admin_id(user),
            "user.revoke_sub",
            target_type="subscription",
            target_id=sub.id,
            details={"user_id": target.id},
        )
    if callback.message is not None:
        await _render_card_message(callback.message, target, edit=True)
    await callback.answer("Подписка отозвана")


@router.callback_query(UserCB.filter(F.action == "toggle_admin"))
async def cb_toggle_admin(
    callback: CallbackQuery,
    callback_data: UserCB,
    user: User | None = None,
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
    async with get_conn() as conn:
        await audit_service.log_action(
            conn,
            _admin_id(user),
            "user.toggle_admin",
            target_type="user",
            target_id=refreshed.id,
            details={"is_admin": refreshed.is_admin},
        )
    if callback.message is not None:
        await _render_card_message(callback.message, refreshed, edit=True)
    await callback.answer(
        "Назначен админом" if new_value else "Снят флаг админа",
    )


@router.callback_query(UserCB.filter(F.action == "toggle_block"))
async def cb_toggle_block(
    callback: CallbackQuery,
    callback_data: UserCB,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Flip the ``is_blocked`` flag for the target user (ban / unban).

    Guards: an admin cannot block themselves, and a target that is an admin (by
    flag or by :data:`settings.ADMIN_IDS`) cannot be blocked — blocking must
    never lock an admin out of the bot (the middleware also never blocks admins,
    but we keep the UI honest).
    """
    user_id = callback_data.id
    async with get_conn() as conn:
        target = await users_repo.get_by_id(conn, user_id)
    if target is None:
        await callback.answer(t("admin.tickets.not_found", lang), show_alert=True)
        return

    new_value = not target.is_blocked
    if new_value:
        if user is not None and target.id == user.id:
            await callback.answer(t("admin.ban.self", lang), show_alert=True)
            return
        if target.is_admin or target.tg_id in set(settings.ADMIN_IDS):
            await callback.answer(
                t("admin.ban.cannot_block_admin", lang), show_alert=True
            )
            return

    async with get_conn() as conn:
        await users_repo.set_blocked(conn, target.id, new_value)
        refreshed = await users_repo.get_by_id(conn, target.id)
        await audit_service.log_action(
            conn,
            _admin_id(user),
            "user.block" if new_value else "user.unblock",
            target_type="user",
            target_id=target.id,
            details={"is_blocked": new_value, "tg_id": target.tg_id},
        )
    if refreshed is None:
        await callback.answer(t("admin.tickets.not_found", lang), show_alert=True)
        return
    logger.info(
        "admin_users: toggle_block user={} → is_blocked={}",
        refreshed.id,
        refreshed.is_blocked,
    )
    if callback.message is not None:
        await _render_card_message(callback.message, refreshed, edit=True)
    await callback.answer(
        t("admin.ban.blocked", lang) if new_value else t("admin.ban.unblocked", lang)
    )


# --------------------------------------------------------------------- #
# Manual subscription grant (AdminGrantSub FSM)
# --------------------------------------------------------------------- #


async def _resolve_plan_inbound(plan_id: int) -> int:
    """Return the inbound to provision a granted subscription on.

    Picks the plan's first attached inbound, falling back to
    :data:`app.config.settings.XUI_INBOUND_ID` when the plan has none attached
    (defence — every active plan should have at least one inbound after the
    migration backfill). Keeps the admin grant a one-tap action without an
    extra inbound-picker step.
    """
    async with get_conn() as conn:
        inbound_ids = await plans_repo.get_inbounds(conn, plan_id)
    if inbound_ids:
        return int(inbound_ids[0])
    return int(settings.XUI_INBOUND_ID)


@router.callback_query(UserCB.filter(F.action == "grant_sub"))
async def cb_grant_open(
    callback: CallbackQuery,
    callback_data: UserCB,
    state: FSMContext,
    lang: str = DEFAULT_LANG,
) -> None:
    """Start the manual-grant wizard: pick a plan for the target user."""
    target_id = callback_data.id
    async with get_conn() as conn:
        target = await users_repo.get_by_id(conn, target_id)
        plans = await plans_repo.list_active(conn)
    if target is None:
        await callback.answer(t("admin.grant.plan_not_found", lang), show_alert=True)
        return
    if not plans:
        await callback.answer(t("admin.grant.no_plans", lang), show_alert=True)
        return

    await state.set_state(AdminGrantSub.waiting_plan)
    await state.update_data(grant_user_id=target.id)
    if callback.message is not None:
        await callback.message.edit_text(
            t("admin.grant.choose_plan", lang),
            reply_markup=grant_plans_kb(plans, lang=lang),
        )
    await callback.answer()


@router.callback_query(
    AdminGrantSub.waiting_plan, GrantCB.filter(F.action == "plan")
)
async def cb_grant_plan(
    callback: CallbackQuery,
    callback_data: GrantCB,
    state: FSMContext,
    lang: str = DEFAULT_LANG,
) -> None:
    """Record the chosen plan and ask for the term (days or '-')."""
    plan_id = callback_data.plan_id
    async with get_conn() as conn:
        plan = await plans_repo.get(conn, plan_id)
    if plan is None:
        await callback.answer(t("admin.grant.plan_not_found", lang), show_alert=True)
        return

    inbound_id = await _resolve_plan_inbound(plan.id)
    await state.update_data(grant_plan_id=plan.id, grant_inbound_id=inbound_id)
    await state.set_state(AdminGrantSub.waiting_days)
    if callback.message is not None:
        await callback.message.edit_text(
            t("admin.grant.enter_days", lang, days=plan.days),
            reply_markup=cancel_kb(lang),
        )
    await callback.answer()


@router.message(AdminGrantSub.waiting_days)
async def st_grant_days(
    message: Message,
    state: FSMContext,
    bot: Bot,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Accept the term, provision the subscription, notify the user, audit."""
    raw = (message.text or "").strip()
    data = await state.get_data()
    target_id = int(data.get("grant_user_id", 0))
    plan_id = int(data.get("grant_plan_id", 0))
    inbound_id = int(data.get("grant_inbound_id", 0))

    days: int | None
    if raw in {"-", "—"}:
        days = None
    else:
        if not raw.isdigit() or int(raw) <= 0:
            await message.answer(t("admin.grant.bad_days", lang), reply_markup=cancel_kb(lang))
            return
        days = int(raw)

    async with get_conn() as conn:
        target = await users_repo.get_by_id(conn, target_id)
        plan = await plans_repo.get(conn, plan_id)
    if target is None or plan is None:
        await state.clear()
        await message.answer(t("admin.grant.plan_not_found", lang))
        return

    try:
        xui = await get_xui_client()
        async with get_conn() as conn:
            sub = await subs_service.grant_subscription(
                conn,
                xui,
                target,
                plan=plan,
                inbound_id=inbound_id,
                days=days,
            )
    except XuiError as exc:
        logger.error(
            "admin_users: grant failed user={} plan={}: {}",
            target.id,
            plan.id,
            exc,
        )
        await state.clear()
        await message.answer(t("admin.grant.failed", lang, error=str(exc)))
        return

    granted_days = plan.days if days is None else days
    async with get_conn() as conn:
        await audit_service.log_action(
            conn,
            _admin_id(user),
            "user.grant_sub",
            target_type="user",
            target_id=target.id,
            details={"plan_id": plan.id, "days": granted_days, "sub_id": sub.id},
        )

    await state.clear()
    logger.info(
        "admin_users: granted sub={} to user={} plan={} days={}",
        sub.id,
        target.id,
        plan.id,
        granted_days,
    )

    # Best-effort: deliver keys + a notice to the target user.
    try:
        await bot.send_message(
            target.tg_id,
            t("admin.grant.user_notified", target.lang, days=granted_days),
        )
        await deliver_keys(
            bot,
            xui,
            chat_id=target.tg_id,
            sub=sub,
            lang=target.lang,
        )
    except Exception as exc:  # noqa: BLE001 — delivery best-effort, never break
        logger.warning(
            "admin_users: grant delivery to user={} failed: {}", target.id, exc
        )

    await message.answer(
        t(
            "admin.grant.success",
            lang,
            user=_safe(target.first_name or target.tg_id),
            days=granted_days,
            sub_id=sub.id,
            expires_at=sub.expires_at,
        )
    )
    async with get_conn() as conn:
        refreshed = await users_repo.get_by_id(conn, target.id)
    await _render_card_message(message, refreshed or target, edit=False)


__all__ = ["router"]
