"""Promo CRUD handlers driven by inline keyboards and :class:`PromoCreate` FSM.

Flow overview
-------------

List view (``PromoCB(action='list')``):
    pulls every promo (active + expired) via raw SQL helper here — the
    repository's :func:`list_active` filters out expired ones, which admins
    still want to see. Falls back to ordering by created_at DESC.

Create wizard (``PromoCB(action='create')``):
    1. ``waiting_code``        — non-empty unique string (case-insensitive
       check via :func:`promos_repo.get_by_code`).
    2. ``waiting_type``        — inline buttons set the type (percent /
       flat_stars / free_days).
    3. ``waiting_value``       — integer; range depends on type
       (1..100 for percent, >0 for flat_stars and free_days).
    4. ``waiting_max_uses``    — integer ≥ 0 (0 → unlimited).
    5. ``waiting_expires_at``  — ``-`` / ``skip`` for no expiry, otherwise
       ``YYYY-MM-DD`` (interpreted as 23:59:59 UTC of that date).
    On success, opens the card of the freshly-created promo.

Card view (``PromoCB(action='card', id=…)``):
    fetches the promo, renders code/type/value/usage/expiry + admin keyboard.

Deactivate (``PromoCB(action='deactivate', id=…)``):
    soft-disable by setting ``expires_at=now`` via :func:`promos_repo.deactivate`.

Redemptions (``PromoCB(action='redemptions', id=…)``):
    shows the redemption history (newest first) with user tg_id and dates.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

import aiosqlite
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db.engine import get_conn
from app.db.repos import promos as promos_repo
from app.db.repos import users as users_repo
from app.db.repos.promos import Promo, PromoType
from app.db.repos.users import User
from app.keyboards.admin import (
    AdminCB,
    PromoCB,
    cancel_kb,
    promo_card_kb,
    promo_expires_presets_kb,
    promo_max_uses_presets_kb,
    promo_type_kb,
    promo_value_presets_kb,
    promos_list_kb,
)
from app.states.admin import PromoCreate

router = Router(name="admin_promos")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_TYPE_LABELS: dict[PromoType, str] = {
    "percent": "Скидка %",
    "flat_stars": "Скидка ⭐",
    "free_days": "Бонусные дни",
}


def _format_promo(promo: Promo) -> str:
    """Return a human-readable promo card body (HTML)."""
    label = _TYPE_LABELS.get(promo.type, promo.type)
    capacity = "∞" if promo.max_uses == 0 else str(promo.max_uses)
    expires = promo.expires_at or "—"

    # Detect "deactivated" — expires_at is in the past (or now).
    now = datetime.now(UTC).replace(microsecond=0).isoformat(sep=" ")
    is_expired = promo.expires_at is not None and promo.expires_at <= now
    is_full = promo.max_uses != 0 and promo.used_count >= promo.max_uses
    if is_expired:
        status = "🚫 истёк/деактивирован"
    elif is_full:
        status = "🔒 исчерпан"
    else:
        status = "✅ активен"

    return (
        f"<b>Промокод #{promo.id}</b>\n"
        f"Код: <code>{promo.code}</code>\n"
        f"Тип: {label} (<code>{promo.type}</code>)\n"
        f"Значение: <b>{promo.value}</b>\n"
        f"Использований: <b>{promo.used_count}</b> / {capacity}\n"
        f"Действует до: <code>{expires}</code>\n"
        f"Статус: {status}"
    )


async def _list_all_promos(conn: aiosqlite.Connection) -> list[Promo]:
    """Return every promo (active + expired), newest first.

    Promo repo does not expose `list_all`; admin UI needs deactivated promos
    visible too, so we inline the query here.
    """
    cursor = await conn.execute(
        "SELECT id, code, type, value, max_uses, used_count, "
        "expires_at, created_at, created_by "
        "FROM promos ORDER BY created_at DESC, id DESC"
    )
    rows = await cursor.fetchall()
    return [Promo.from_row(r) for r in rows]


def _promo_is_active(promo: Promo) -> bool:
    """Return ``True`` iff a promo is currently usable (not deactivated)."""
    if promo.expires_at is None:
        return True
    now = datetime.now(UTC).replace(microsecond=0).isoformat(sep=" ")
    return promo.expires_at > now


async def _show_card(message: Message, promo_id: int, *, edit: bool = True) -> None:
    """Render a promo card."""
    async with get_conn() as conn:
        promo = await promos_repo.get(conn, promo_id)
    if promo is None:
        text = f"Промокод #{promo_id} не найден."
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return
    kb = promo_card_kb(promo.id, is_active=_promo_is_active(promo))
    if edit:
        await message.edit_text(_format_promo(promo), reply_markup=kb)
    else:
        await message.answer(_format_promo(promo), reply_markup=kb)


async def _show_list(message: Message, *, edit: bool = True) -> None:
    """Render the list of promos."""
    async with get_conn() as conn:
        all_promos = await _list_all_promos(conn)
    text = "Промокоды:" if all_promos else "Промокодов пока нет. Создайте первый."
    kb = promos_list_kb(all_promos)
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


def _parse_expires_at(raw: str) -> str | None | bool:
    """Parse user input for ``expires_at``.

    Returns:
    * ``None`` if the user typed ``-`` / ``skip`` / ``нет`` (no expiry).
    * An ISO-8601 UTC timestamp (string, seconds resolution) on success.
    * ``False`` if the input is unparseable — callers re-ask.
    """
    s = raw.strip().lower()
    if s in {"-", "skip", "нет", "no"}:
        return None
    try:
        d = datetime.strptime(raw.strip(), "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=UTC
        )
    except ValueError:
        return False
    return d.isoformat(sep=" ")


# ---------------------------------------------------------------------------
# Navigation callbacks
# ---------------------------------------------------------------------------


@router.callback_query(AdminCB.filter((F.area == "promos") & (F.action == "open")))
async def cb_open(callback: CallbackQuery, state: FSMContext) -> None:
    """Entry point from the admin main menu: render the promo list."""
    await state.clear()
    if callback.message is not None:
        await _show_list(callback.message, edit=True)
    await callback.answer()


@router.callback_query(PromoCB.filter(F.action == "list"))
async def cb_list(callback: CallbackQuery, state: FSMContext) -> None:
    """Open the promo list (also clears any in-progress wizard)."""
    await state.clear()
    if callback.message is not None:
        await _show_list(callback.message, edit=True)
    await callback.answer()


@router.callback_query(PromoCB.filter(F.action == "card"))
async def cb_card(callback: CallbackQuery, callback_data: PromoCB) -> None:
    """Open a promo card by id."""
    if callback.message is not None:
        await _show_card(callback.message, callback_data.id, edit=True)
    await callback.answer()


@router.callback_query(PromoCB.filter(F.action == "deactivate"))
async def cb_deactivate(callback: CallbackQuery, callback_data: PromoCB) -> None:
    """Soft-disable a promo and re-render its card."""
    async with get_conn() as conn:
        await promos_repo.deactivate(conn, callback_data.id)
    if callback.message is not None:
        await _show_card(callback.message, callback_data.id, edit=True)
    await callback.answer("Промокод деактивирован")


@router.callback_query(PromoCB.filter(F.action == "redemptions"))
async def cb_redemptions(callback: CallbackQuery, callback_data: PromoCB) -> None:
    """Render the redemption history for a promo."""
    promo_id = callback_data.id
    async with get_conn() as conn:
        redemptions = await promos_repo.list_redemptions(conn, promo_id)
        # Resolve user tg_ids in one go via simple loop (acceptable: admin UI).
        user_tg: dict[int, int] = {}
        for r in redemptions:
            if r.user_id not in user_tg:
                u = await users_repo.get_by_id(conn, r.user_id)
                user_tg[r.user_id] = u.tg_id if u else 0

    if not redemptions:
        text = f"По промокоду #{promo_id} ещё нет активаций."
    else:
        lines = [f"<b>Активации промокода #{promo_id}</b> ({len(redemptions)}):", ""]
        for r in redemptions:
            lines.append(
                f"• tg_id <code>{user_tg.get(r.user_id, 0)}</code> "
                f"— {r.redeemed_at}"
                + (f" (sub #{r.subscription_id})" if r.subscription_id else "")
            )
        text = "\n".join(lines)

    if callback.message is not None:
        await callback.message.edit_text(
            text,
            reply_markup=promo_card_kb(promo_id, is_active=True),
        )
    await callback.answer()


# ---------------------------------------------------------------------------
# Create wizard
# ---------------------------------------------------------------------------


@router.callback_query(PromoCB.filter(F.action == "create"))
async def cb_create(callback: CallbackQuery, state: FSMContext) -> None:
    """Start :class:`PromoCreate` — ask for the code."""
    await state.set_state(PromoCreate.waiting_code)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите код промокода (буквы/цифры, без пробелов):",
            reply_markup=cancel_kb(),
        )
    await callback.answer()


@router.message(PromoCreate.waiting_code)
async def st_code(message: Message, state: FSMContext) -> None:
    """Accept the code, validate uniqueness, ask for the type."""
    code = (message.text or "").strip()
    if not code or any(ch.isspace() for ch in code):
        await message.answer(
            "Код не может быть пустым и не должен содержать пробелов. Введите ещё раз:",
            reply_markup=cancel_kb(),
        )
        return
    async with get_conn() as conn:
        existing = await promos_repo.get_by_code(conn, code)
    if existing is not None:
        await message.answer(
            f"Код «{code}» уже используется. Введите другой:",
            reply_markup=cancel_kb(),
        )
        return
    await state.update_data(code=code)
    await state.set_state(PromoCreate.waiting_type)
    await message.answer(
        "Выберите тип промокода:",
        reply_markup=promo_type_kb(),
    )


@router.callback_query(
    PromoCreate.waiting_type,
    PromoCB.filter(F.action == "type"),
)
async def cb_type(
    callback: CallbackQuery,
    callback_data: PromoCB,
    state: FSMContext,
) -> None:
    """Accept the chosen type and ask for the value."""
    promo_type = callback_data.field
    if promo_type not in {"percent", "flat_stars", "free_days"}:
        await callback.answer("Неизвестный тип", show_alert=True)
        return
    await state.update_data(type=promo_type)
    await state.set_state(PromoCreate.waiting_value)

    hint = {
        "percent": "Процент скидки (целое 1..100):",
        "flat_stars": "Размер скидки в Stars (целое > 0):",
        "free_days": "Количество бонусных дней (целое > 0):",
    }[promo_type]
    if callback.message is not None:
        await callback.message.edit_text(
            hint,
            reply_markup=promo_value_presets_kb(promo_type),
        )
    await callback.answer()


@router.message(PromoCreate.waiting_value)
async def st_value(message: Message, state: FSMContext) -> None:
    """Accept the value, validate per type, ask for max_uses."""
    raw = (message.text or "").strip()
    try:
        value = int(raw)
    except ValueError:
        await message.answer(
            "Нужно целое число. Попробуйте ещё раз:",
            reply_markup=cancel_kb(),
        )
        return
    data = await state.get_data()
    promo_type = cast(PromoType, data["type"])
    if promo_type == "percent" and not (1 <= value <= 100):
        await message.answer(
            "Процент должен быть в диапазоне 1..100. Введите снова:",
            reply_markup=cancel_kb(),
        )
        return
    if promo_type in {"flat_stars", "free_days"} and value <= 0:
        await message.answer(
            "Значение должно быть > 0. Введите снова:",
            reply_markup=cancel_kb(),
        )
        return

    await state.update_data(value=value)
    await state.set_state(PromoCreate.waiting_max_uses)
    await message.answer(
        "Максимальное число активаций (0 = без лимита):",
        reply_markup=promo_max_uses_presets_kb(),
    )


@router.message(PromoCreate.waiting_max_uses)
async def st_max_uses(message: Message, state: FSMContext) -> None:
    """Accept ``max_uses``, ask for ``expires_at``."""
    raw = (message.text or "").strip()
    try:
        max_uses = int(raw)
    except ValueError:
        await message.answer(
            "Нужно целое число ≥ 0. Попробуйте ещё раз:",
            reply_markup=cancel_kb(),
        )
        return
    if max_uses < 0:
        await message.answer(
            "Значение не может быть отрицательным. Введите снова:",
            reply_markup=cancel_kb(),
        )
        return
    await state.update_data(max_uses=max_uses)
    await state.set_state(PromoCreate.waiting_expires_at)
    await message.answer(
        "Дата истечения (YYYY-MM-DD) или «-» / «skip» для бессрочного:",
        reply_markup=promo_expires_presets_kb(),
    )


@router.message(PromoCreate.waiting_expires_at)
async def st_expires_at(
    message: Message,
    state: FSMContext,
    user: User | None = None,
) -> None:
    """Parse ``expires_at``, persist promo, render its card."""
    raw = message.text or ""
    parsed = _parse_expires_at(raw)
    if parsed is False:
        await message.answer(
            "Не удалось разобрать дату. Введите YYYY-MM-DD или «-»:",
            reply_markup=promo_expires_presets_kb(),
        )
        return
    expires_at = cast("str | None", parsed)
    await _finalize_promo_create(message, state, expires_at=expires_at, user=user)


async def _finalize_promo_create(
    message: Message,
    state: FSMContext,
    *,
    expires_at: str | None,
    user: User | None,
) -> None:
    """Persist the promo with collected FSM data, clear state, render its card.

    Called from both the manual-text path (:func:`st_expires_at`) and the
    preset-button path (:func:`cb_promo_preset` on the ``expires`` step).
    All earlier wizard inputs (``code``/``type``/``value``/``max_uses``)
    come from FSM data populated by previous steps.
    """
    data = await state.get_data()
    created_by = user.id if user is not None else None

    async with get_conn() as conn:
        try:
            promo = await promos_repo.create(
                conn,
                code=data["code"],
                type=data["type"],
                value=data["value"],
                max_uses=data["max_uses"],
                expires_at=expires_at,
                created_by=created_by,
            )
        except aiosqlite.IntegrityError:
            await state.clear()
            await message.answer(
                "Не удалось создать промокод (конфликт уникальности). Попробуйте снова."
            )
            return

    await state.clear()
    await message.answer(
        f"Промокод создан ✅\n\n{_format_promo(promo)}",
        reply_markup=promo_card_kb(promo.id, is_active=_promo_is_active(promo)),
    )


# ---------------------------------------------------------------------------
# Preset / manual callbacks (shared across all 3 wizard input steps)
# ---------------------------------------------------------------------------


# Mapping: PromoCB.field (preset key) → (FSM-data key written, next state,
# next-step prompt, next-step keyboard factory). The ``expires`` row uses
# ``None`` for next-state because it terminates the wizard (the handler
# persists the promo instead of moving on).
_PRESET_FLOW: dict[str, tuple[str, object | None, str, object | None]] = {
    "value": (
        "value",
        PromoCreate.waiting_max_uses,
        "Максимальное число активаций (0 = без лимита):",
        promo_max_uses_presets_kb,
    ),
    "max_uses": (
        "max_uses",
        PromoCreate.waiting_expires_at,
        "Дата истечения (YYYY-MM-DD) или «-» / «skip» для бессрочного:",
        promo_expires_presets_kb,
    ),
    "expires": ("expires_at", None, "", None),
}


def _expires_days_to_iso(days: int) -> str | None:
    """Convert a preset «+N days» value to an ISO-8601 expires_at string.

    Mirrors :func:`_parse_expires_at`: the resulting date is anchored to
    ``23:59:59 UTC`` so the same comparison logic in
    :func:`_promo_is_active` and the repository works unchanged. ``0``
    means «бессрочно» → ``None``.
    """
    if days <= 0:
        return None
    d = (datetime.now(UTC) + timedelta(days=days)).replace(
        hour=23, minute=59, second=59, microsecond=0
    )
    return d.isoformat(sep=" ")


@router.callback_query(PromoCB.filter(F.action == "preset"))
async def cb_promo_preset(
    callback: CallbackQuery,
    callback_data: PromoCB,
    state: FSMContext,
    user: User | None = None,
) -> None:
    """Handle a preset button click on any of the promo wizard steps.

    The button carries the chosen integer in ``callback_data.id`` and the
    step key in ``callback_data.field`` (``value``/``max_uses``/``expires``).
    The handler writes the value into FSM data under the matching key,
    then either moves to the next step (sending its preset keyboard) or —
    for the terminal ``expires`` step — creates the promo and renders its
    card.
    """
    field = callback_data.field
    flow = _PRESET_FLOW.get(field)
    if flow is None:
        await callback.answer("Неизвестный шаг", show_alert=True)
        return
    data_key, next_state, prompt, kb_factory = flow
    value = callback_data.id

    # Final step: persist the promo and exit.
    if field == "expires":
        expires_at = _expires_days_to_iso(value)
        if callback.message is not None:
            await _finalize_promo_create(
                callback.message, state, expires_at=expires_at, user=user
            )
        await callback.answer()
        return

    await state.update_data(**{data_key: value})
    assert next_state is not None  # not the terminal step, narrowed above
    await state.set_state(next_state)
    if callback.message is not None and kb_factory is not None:
        await callback.message.answer(prompt, reply_markup=kb_factory())
    await callback.answer()


@router.callback_query(PromoCB.filter(F.action == "manual"))
async def cb_promo_manual(callback: CallbackQuery, callback_data: PromoCB) -> None:
    """Switch a wizard step from preset-buttons to manual text entry.

    State is intentionally NOT changed — we are already in the right
    ``waiting_*`` state when the preset keyboard was shown. The handler
    just sends a fresh prompt and the user types the value.
    """
    field = callback_data.field
    prompts = {
        "value": "Введите значение (целое число):",
        "max_uses": "Введите максимальное число активаций (целое ≥ 0; 0 = без лимита):",
        "expires": "Введите дату истечения (YYYY-MM-DD) или «-» для бессрочного:",
    }
    text = prompts.get(field)
    if text is None:
        await callback.answer("Неизвестный шаг", show_alert=True)
        return
    if callback.message is not None:
        await callback.message.answer(text, reply_markup=cancel_kb())
    await callback.answer()


__all__ = ["router"]
