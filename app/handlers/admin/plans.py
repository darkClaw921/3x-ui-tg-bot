"""Plan CRUD handlers driven by inline keyboards and :class:`PlanCreate`/:class:`PlanEdit` FSM.

Flow overview
-------------

List view (``PlanCB(action='list')``):
    pulls every plan via :func:`app.db.repos.plans.list_all` (admins need to
    see inactive ones too) and renders :func:`plans_list_kb`.

Create wizard (``PlanCB(action='create')``):
    1. ``waiting_title``  — any non-empty string.
    2. ``waiting_days``   — positive integer.
    3. ``waiting_price``  — non-negative integer (Stars amount).
    On success, opens the card of the freshly-created plan and clears state.
    Invalid input re-asks without dropping FSM state.

Card view (``PlanCB(action='card', id=…)``):
    fetches the plan, renders title/days/price/is_active + :func:`plan_card_kb`.

Edit wizard (``PlanCB(action='edit', id=…, field=…)``):
    Stores ``plan_id`` and ``field`` in FSM data, transitions to
    :class:`PlanEdit.waiting_value`. The handler validates the value type
    against the field (string for ``title``, ``int>0`` for ``days``,
    ``int>=0`` for ``price_stars``) and calls :func:`plans_repo.update`.

Deactivate (``PlanCB(action='deactivate', id=…)``):
    soft-disable via :func:`plans_repo.deactivate`. Card is re-rendered.

Cancellation in any FSM step is handled by the global cancel callback in
:mod:`app.handlers.admin.menu`.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db.engine import get_conn
from app.db.repos import plans as plans_repo
from app.db.repos.plans import Plan
from app.keyboards.admin import (
    PlanCB,
    cancel_kb,
    plan_card_kb,
    plan_edit_fields_kb,
    plans_list_kb,
)
from app.states.admin import PlanCreate, PlanEdit

router = Router(name="admin_plans")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_plan(plan: Plan) -> str:
    """Return a human-readable plan card body (HTML)."""
    active = "✅ активен" if plan.is_active else "🚫 деактивирован"
    return (
        f"<b>Тариф #{plan.id}</b>\n"
        f"Название: <code>{plan.title}</code>\n"
        f"Срок: <b>{plan.days}</b> дн.\n"
        f"Цена: <b>{plan.price_stars}</b> ⭐\n"
        f"Статус: {active}"
    )


async def _show_card(message: Message, plan_id: int, *, edit: bool = True) -> None:
    """Render a plan card, either editing the source message or sending a new one."""
    async with get_conn() as conn:
        plan = await plans_repo.get(conn, plan_id)
    if plan is None:
        text = f"Тариф #{plan_id} не найден."
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return
    kb = plan_card_kb(plan.id, is_active=plan.is_active)
    if edit:
        await message.edit_text(_format_plan(plan), reply_markup=kb)
    else:
        await message.answer(_format_plan(plan), reply_markup=kb)


async def _show_list(message: Message, *, edit: bool = True) -> None:
    """Render the list of plans (all, active first)."""
    async with get_conn() as conn:
        all_plans = await plans_repo.list_all(conn)
    # Active first, then by id descending for newest-on-top among inactive.
    all_plans = sorted(all_plans, key=lambda p: (not p.is_active, p.price_stars, p.id))
    text = "Тарифы:" if all_plans else "Тарифов пока нет. Создайте первый."
    kb = plans_list_kb(all_plans)
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


# ---------------------------------------------------------------------------
# Navigation callbacks
# ---------------------------------------------------------------------------


@router.callback_query(PlanCB.filter(F.action == "list"))
async def cb_list(callback: CallbackQuery, state: FSMContext) -> None:
    """Open the plan list (also clears any in-progress wizard)."""
    await state.clear()
    if callback.message is not None:
        await _show_list(callback.message, edit=True)
    await callback.answer()


@router.callback_query(PlanCB.filter(F.action == "card"))
async def cb_card(callback: CallbackQuery, callback_data: PlanCB) -> None:
    """Open a plan card by id."""
    if callback.message is not None:
        await _show_card(callback.message, callback_data.id, edit=True)
    await callback.answer()


@router.callback_query(PlanCB.filter(F.action == "edit_menu"))
async def cb_edit_menu(callback: CallbackQuery, callback_data: PlanCB) -> None:
    """Show the «choose field to edit» keyboard for a given plan."""
    plan_id = callback_data.id
    if callback.message is not None:
        await callback.message.edit_text(
            f"Что отредактировать в тарифе #{plan_id}?",
            reply_markup=plan_edit_fields_kb(plan_id),
        )
    await callback.answer()


@router.callback_query(PlanCB.filter(F.action == "deactivate"))
async def cb_deactivate(callback: CallbackQuery, callback_data: PlanCB) -> None:
    """Soft-disable a plan and re-render its card."""
    async with get_conn() as conn:
        await plans_repo.deactivate(conn, callback_data.id)
    if callback.message is not None:
        await _show_card(callback.message, callback_data.id, edit=True)
    await callback.answer("Тариф деактивирован")


# ---------------------------------------------------------------------------
# Create wizard
# ---------------------------------------------------------------------------


@router.callback_query(PlanCB.filter(F.action == "create"))
async def cb_create(callback: CallbackQuery, state: FSMContext) -> None:
    """Start :class:`PlanCreate` — ask for the plan title."""
    await state.set_state(PlanCreate.waiting_title)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите название тарифа (например, «1 месяц»):",
            reply_markup=cancel_kb(),
        )
    await callback.answer()


@router.message(PlanCreate.waiting_title)
async def st_title(message: Message, state: FSMContext) -> None:
    """Accept the plan title and ask for days."""
    title = (message.text or "").strip()
    if not title:
        await message.answer(
            "Название не может быть пустым. Введите ещё раз:",
            reply_markup=cancel_kb(),
        )
        return
    await state.update_data(title=title)
    await state.set_state(PlanCreate.waiting_days)
    await message.answer(
        "Срок действия в днях (целое число > 0):",
        reply_markup=cancel_kb(),
    )


@router.message(PlanCreate.waiting_days)
async def st_days(message: Message, state: FSMContext) -> None:
    """Accept the days count and ask for the price."""
    raw = (message.text or "").strip()
    try:
        days = int(raw)
    except ValueError:
        await message.answer(
            "Нужно целое число > 0. Попробуйте ещё раз:",
            reply_markup=cancel_kb(),
        )
        return
    if days <= 0:
        await message.answer(
            "Срок должен быть > 0. Введите снова:",
            reply_markup=cancel_kb(),
        )
        return
    await state.update_data(days=days)
    await state.set_state(PlanCreate.waiting_price)
    await message.answer(
        "Цена в Stars (целое число ≥ 0):",
        reply_markup=cancel_kb(),
    )


@router.message(PlanCreate.waiting_price)
async def st_price(message: Message, state: FSMContext) -> None:
    """Accept the price, create the plan in DB, show its card."""
    raw = (message.text or "").strip()
    try:
        price = int(raw)
    except ValueError:
        await message.answer(
            "Нужно целое число ≥ 0. Попробуйте ещё раз:",
            reply_markup=cancel_kb(),
        )
        return
    if price < 0:
        await message.answer(
            "Цена не может быть отрицательной. Введите снова:",
            reply_markup=cancel_kb(),
        )
        return

    data = await state.get_data()
    title: str = data["title"]
    days: int = data["days"]

    async with get_conn() as conn:
        plan = await plans_repo.create(conn, title=title, days=days, price_stars=price)
    await state.clear()
    await message.answer(
        f"Тариф создан ✅\n\n{_format_plan(plan)}",
        reply_markup=plan_card_kb(plan.id, is_active=plan.is_active),
    )


# ---------------------------------------------------------------------------
# Edit wizard
# ---------------------------------------------------------------------------


_FIELD_LABELS = {
    "title": "новое название",
    "days": "новый срок в днях (целое > 0)",
    "price_stars": "новую цену в Stars (целое ≥ 0)",
}


@router.callback_query(PlanCB.filter(F.action == "edit"))
async def cb_edit(
    callback: CallbackQuery,
    callback_data: PlanCB,
    state: FSMContext,
) -> None:
    """Start :class:`PlanEdit` — store ``plan_id`` and ``field`` in FSM data."""
    field = callback_data.field
    if field not in _FIELD_LABELS:
        await callback.answer("Неизвестное поле", show_alert=True)
        return
    await state.set_state(PlanEdit.waiting_value)
    await state.update_data(plan_id=callback_data.id, field=field)
    if callback.message is not None:
        await callback.message.edit_text(
            f"Введите {_FIELD_LABELS[field]}:",
            reply_markup=cancel_kb(),
        )
    await callback.answer()


@router.message(PlanEdit.waiting_value)
async def st_edit_value(message: Message, state: FSMContext) -> None:
    """Validate and persist the new field value, then re-render the card."""
    data = await state.get_data()
    field: str = data["field"]
    plan_id: int = data["plan_id"]
    raw = (message.text or "").strip()

    if field == "title":
        if not raw:
            await message.answer(
                "Название не может быть пустым. Введите ещё раз:",
                reply_markup=cancel_kb(),
            )
            return
        value: object = raw
    else:
        try:
            n = int(raw)
        except ValueError:
            await message.answer(
                "Нужно целое число. Попробуйте ещё раз:",
                reply_markup=cancel_kb(),
            )
            return
        if field == "days" and n <= 0:
            await message.answer(
                "Срок должен быть > 0. Введите снова:",
                reply_markup=cancel_kb(),
            )
            return
        if field == "price_stars" and n < 0:
            await message.answer(
                "Цена не может быть отрицательной. Введите снова:",
                reply_markup=cancel_kb(),
            )
            return
        value = n

    async with get_conn() as conn:
        try:
            await plans_repo.update(conn, plan_id, **{field: value})
        except LookupError:
            await state.clear()
            await message.answer(f"Тариф #{plan_id} не найден.")
            return

    await state.clear()
    await _show_card(message, plan_id, edit=False)


__all__ = ["router"]
