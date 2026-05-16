"""Plan CRUD handlers driven by inline keyboards and :class:`PlanCreate`/:class:`PlanEdit` FSM.

Flow overview
-------------

List view (``PlanCB(action='list')``):
    pulls every plan via :func:`app.db.repos.plans.list_all` (admins need to
    see inactive ones too) and renders :func:`plans_list_kb`.

Create wizard (``PlanCB(action='create')``):
    1. ``waiting_title``       — any non-empty string (text only).
    2. ``waiting_days``        — preset keyboard OR positive integer text.
    3. ``waiting_price``       — preset keyboard OR non-negative integer text.
    4. ``waiting_traffic_gb``  — preset keyboard OR non-negative integer text
       (``0`` ≡ без лимита, matches xui ``totalGB`` semantics).
    On success, opens the card of the freshly-created plan and clears state.
    Invalid input re-asks without dropping FSM state. The numeric steps
    also accept preset buttons (:func:`plan_days_presets_kb`,
    :func:`plan_price_presets_kb`, :func:`plan_gb_presets_kb`) — both paths
    converge on the same FSM data writes via :func:`cb_plan_preset` /
    :func:`cb_plan_manual`.

Card view (``PlanCB(action='card', id=…)``):
    fetches the plan, renders title/days/price/traffic/is_active + :func:`plan_card_kb`.

Edit wizard (``PlanCB(action='edit', id=…, field=…)``):
    Stores ``plan_id`` and ``field`` in FSM data, transitions to
    :class:`PlanEdit.waiting_value`. The handler validates the value type
    against the field (string for ``title``, ``int>0`` for ``days``,
    ``int>=0`` for ``price_stars`` / ``traffic_gb``) and calls
    :func:`plans_repo.update`.

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
    AdminCB,
    PlanCB,
    cancel_kb,
    plan_card_kb,
    plan_days_presets_kb,
    plan_edit_fields_kb,
    plan_gb_presets_kb,
    plan_price_presets_kb,
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
    traffic = "без лимита" if plan.traffic_gb == 0 else f"{plan.traffic_gb} ГБ"
    return (
        f"<b>Тариф #{plan.id}</b>\n"
        f"Название: <code>{plan.title}</code>\n"
        f"Срок: <b>{plan.days}</b> дн.\n"
        f"Цена: <b>{plan.price_stars}</b> ⭐\n"
        f"Трафик: <b>{traffic}</b>\n"
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


@router.callback_query(AdminCB.filter((F.area == "plans") & (F.action == "open")))
async def cb_open(callback: CallbackQuery, state: FSMContext) -> None:
    """Entry point from the admin main menu: render the plan list."""
    await state.clear()
    if callback.message is not None:
        await _show_list(callback.message, edit=True)
    await callback.answer()


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
    """Accept the plan title and show the days-preset keyboard."""
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
        "Срок действия:",
        reply_markup=plan_days_presets_kb(),
    )


@router.message(PlanCreate.waiting_days)
async def st_days(message: Message, state: FSMContext) -> None:
    """Accept the days count (manual text path) and show price presets."""
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
        "Цена в Stars:",
        reply_markup=plan_price_presets_kb(),
    )


@router.message(PlanCreate.waiting_price)
async def st_price(message: Message, state: FSMContext) -> None:
    """Accept the price (manual text path) and show traffic-GB presets."""
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
    await state.update_data(price=price)
    await state.set_state(PlanCreate.waiting_traffic_gb)
    await message.answer(
        "Лимит трафика на клиента (ГБ; 0 = без лимита):",
        reply_markup=plan_gb_presets_kb(),
    )


@router.message(PlanCreate.waiting_traffic_gb)
async def st_traffic_gb(message: Message, state: FSMContext) -> None:
    """Accept the traffic limit (manual text path), persist the plan, show its card."""
    raw = (message.text or "").strip()
    try:
        traffic_gb = int(raw)
    except ValueError:
        await message.answer(
            "Нужно целое число ≥ 0. Попробуйте ещё раз:",
            reply_markup=plan_gb_presets_kb(),
        )
        return
    if traffic_gb < 0:
        await message.answer(
            "Лимит не может быть отрицательным. Введите снова:",
            reply_markup=plan_gb_presets_kb(),
        )
        return
    await _finalize_plan_create(message, state, traffic_gb=traffic_gb)


async def _finalize_plan_create(
    message: Message,
    state: FSMContext,
    *,
    traffic_gb: int,
) -> None:
    """Persist the plan with collected FSM data, clear state, render its card.

    Called from both the manual-text path (:func:`st_traffic_gb`) and the
    preset-button path (:func:`cb_plan_preset` on the ``gb`` step). All
    earlier wizard inputs (``title``/``days``/``price``) come from FSM
    data populated by previous steps.
    """
    data = await state.get_data()
    title: str = data["title"]
    days: int = data["days"]
    price: int = data["price"]

    async with get_conn() as conn:
        plan = await plans_repo.create(
            conn,
            title=title,
            days=days,
            price_stars=price,
            traffic_gb=traffic_gb,
        )
    await state.clear()
    await message.answer(
        f"Тариф создан ✅\n\n{_format_plan(plan)}",
        reply_markup=plan_card_kb(plan.id, is_active=plan.is_active),
    )


# ---------------------------------------------------------------------------
# Preset / manual callbacks (shared across all 3 numeric wizard steps)
# ---------------------------------------------------------------------------


# Mapping: PlanCB.field (preset key) → (FSM-data key written, next state, next-step prompt+keyboard factory).
# The ``gb`` row has ``None`` for the next-state because it terminates the
# wizard (the handler persists the plan instead of moving on).
_PRESET_FLOW: dict[str, tuple[str, object | None, str, object | None]] = {
    "days": (
        "days",
        PlanCreate.waiting_price,
        "Цена в Stars:",
        plan_price_presets_kb,
    ),
    "price": (
        "price",
        PlanCreate.waiting_traffic_gb,
        "Лимит трафика на клиента (ГБ; 0 = без лимита):",
        plan_gb_presets_kb,
    ),
    "gb": ("traffic_gb", None, "", None),
}


@router.callback_query(PlanCB.filter(F.action == "preset"))
async def cb_plan_preset(
    callback: CallbackQuery,
    callback_data: PlanCB,
    state: FSMContext,
) -> None:
    """Handle a preset button click on any of the numeric wizard steps.

    The button carries the chosen integer in ``callback_data.id`` and the
    step key in ``callback_data.field`` (``days``/``price``/``gb``). The
    handler writes the value into FSM data under the matching key, then
    either moves to the next step (sending its preset keyboard) or — for
    the terminal ``gb`` step — creates the plan and renders its card.
    """
    field = callback_data.field
    flow = _PRESET_FLOW.get(field)
    if flow is None:
        await callback.answer("Неизвестный шаг", show_alert=True)
        return
    data_key, next_state, prompt, kb_factory = flow
    value = callback_data.id

    # Final step: persist the plan and exit.
    if field == "gb":
        if callback.message is not None:
            await _finalize_plan_create(callback.message, state, traffic_gb=value)
        await callback.answer()
        return

    await state.update_data(**{data_key: value})
    assert next_state is not None  # not the terminal step, narrowed above
    await state.set_state(next_state)
    if callback.message is not None and kb_factory is not None:
        await callback.message.answer(prompt, reply_markup=kb_factory())
    await callback.answer()


@router.callback_query(PlanCB.filter(F.action == "manual"))
async def cb_plan_manual(callback: CallbackQuery, callback_data: PlanCB) -> None:
    """Switch a wizard step from preset-buttons to manual text entry.

    State is intentionally NOT changed — we are already in the right
    ``waiting_*`` state when the preset keyboard was shown. The handler
    just sends a fresh prompt and the user types the number.
    """
    field = callback_data.field
    prompts = {
        "days": "Введите срок действия в днях (целое число > 0):",
        "price": "Введите цену в Stars (целое число ≥ 0):",
        "gb": "Введите лимит трафика в ГБ (целое число ≥ 0; 0 = без лимита):",
    }
    text = prompts.get(field)
    if text is None:
        await callback.answer("Неизвестный шаг", show_alert=True)
        return
    if callback.message is not None:
        await callback.message.answer(text, reply_markup=cancel_kb())
    await callback.answer()


# ---------------------------------------------------------------------------
# Edit wizard
# ---------------------------------------------------------------------------


_FIELD_LABELS = {
    "title": "новое название",
    "days": "новый срок в днях (целое > 0)",
    "price_stars": "новую цену в Stars (целое ≥ 0)",
    "traffic_gb": "новый лимит трафика в ГБ (целое ≥ 0; 0 = без лимита)",
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
        if field == "traffic_gb" and n < 0:
            await message.answer(
                "Лимит не может быть отрицательным. Введите снова:",
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
