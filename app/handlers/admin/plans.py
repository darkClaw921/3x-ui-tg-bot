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
    5. ``waiting_inbounds``    — multi-select keyboard over xui inbounds
       (:func:`plan_inbounds_select_kb`). The user must confirm at least one
       inbound via :func:`cb_inbounds_done`; tapping rows toggles selection
       via :func:`cb_toggle_inbound`. The plan row is persisted only after
       the user confirms the inbound set — see
       :func:`_finalize_plan_create`.
    On success, opens the card of the freshly-created plan and clears state.
    Invalid input re-asks without dropping FSM state. The numeric steps
    also accept preset buttons (:func:`plan_days_presets_kb`,
    :func:`plan_price_presets_kb`, :func:`plan_gb_presets_kb`) — both paths
    converge on the same FSM data writes via :func:`cb_plan_preset` /
    :func:`cb_plan_manual`.

Card view (``PlanCB(action='card', id=…)``):
    fetches the plan, renders title/days/price/traffic/is_active/inbounds +
    :func:`plan_card_kb`. Inbound remarks are resolved through
    :func:`app.services.inbounds.list_user_inbounds`; if the xui panel is
    unavailable the card degrades gracefully and shows raw ids without
    remarks. Inbounds attached to the plan but missing from the panel
    response are rendered as ``id=NN (удалён)``.

Edit wizard (``PlanCB(action='edit', id=…, field=…)``):
    Text-valued fields (``title``/``days``/``price_stars``/``traffic_gb``)
    store ``plan_id`` and ``field`` in FSM data, transition to
    :class:`PlanEdit.waiting_value`, validate the value type against the
    field, and call :func:`plans_repo.update`.
    The ``field='inbounds'`` branch is handled separately
    (:func:`cb_edit_inbounds`) — it reuses the same multi-select keyboard
    as the create wizard and is differentiated by the ``editing_plan_id``
    key in FSM data (present → edit mode, absent → create mode).

Deactivate (``PlanCB(action='deactivate', id=…)``):
    soft-disable via :func:`plans_repo.deactivate`. Card is re-rendered.

Cancellation in any FSM step is handled by the global cancel callback in
:mod:`app.handlers.admin.menu`.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger

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
    plan_inbounds_select_kb,
    plan_price_presets_kb,
    plans_list_kb,
)
from app.services.inbounds import InboundOption, list_user_inbounds
from app.states.admin import PlanCreate, PlanEdit
from app.xui import XuiError, get_xui_client

router = Router(name="admin_plans")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_plan(plan: Plan, inbound_remarks: dict[int, str] | None = None) -> str:
    """Return a human-readable plan card body (HTML).

    ``inbound_remarks`` maps ``inbound_id`` → display name (``remark`` from
    the panel, or ``""`` if the panel response was unavailable). The card
    appends a «Подключения» line built from this mapping plus the list of
    inbound ids attached to the plan. If an inbound id present on the plan
    is missing from ``inbound_remarks`` (admin deleted it on the panel) it
    is rendered as ``id=NN (удалён)``; if the mapping is ``None`` or empty
    the line is rendered with raw ``id=NN`` tokens (graceful degrade when
    the panel is unreachable).
    """
    active = "✅ активен" if plan.is_active else "🚫 деактивирован"
    traffic = "без лимита" if plan.traffic_gb == 0 else f"{plan.traffic_gb} ГБ"
    lines = [
        f"<b>Тариф #{plan.id}</b>",
        f"Название: <code>{plan.title}</code>",
        f"Срок: <b>{plan.days}</b> дн.",
        f"Цена: <b>{plan.price_stars}</b> ⭐",
        f"Трафик: <b>{traffic}</b>",
        f"Статус: {active}",
    ]
    if inbound_remarks is not None:
        if not inbound_remarks:
            lines.append("Подключения: <i>не настроены</i>")
        else:
            parts: list[str] = []
            for inbound_id, remark in inbound_remarks.items():
                if remark:
                    parts.append(remark)
                else:
                    parts.append(f"id={inbound_id} (удалён)")
            lines.append("Подключения: " + ", ".join(parts))
    return "\n".join(lines)


async def _resolve_inbound_remarks(inbound_ids: list[int]) -> dict[int, str]:
    """Resolve panel remarks for the given inbound ids.

    Returns a dict mapping each id in ``inbound_ids`` (preserving order via
    insertion order) to its remark; ids missing from the panel response
    receive an empty string, which the renderer turns into «(удалён)».
    On xui errors (panel down, auth failure, …) returns a dict with empty
    string values for every id — the card still renders, just without
    remarks (graceful degrade).
    """
    if not inbound_ids:
        return {}
    try:
        xui = await get_xui_client()
        options = await list_user_inbounds(xui)
    except XuiError as exc:
        logger.warning("plans card: xui unavailable, degrading: {}", exc)
        return {inbound_id: "" for inbound_id in inbound_ids}
    by_id = {option.id: option.remark for option in options}
    return {inbound_id: by_id.get(inbound_id, "") for inbound_id in inbound_ids}


async def _show_card(message: Message, plan_id: int, *, edit: bool = True) -> None:
    """Render a plan card, either editing the source message or sending a new one.

    Fetches the plan + its attached inbounds (:func:`plans_repo.get_inbounds`)
    and resolves remarks via :func:`_resolve_inbound_remarks` before
    rendering. The latter swallows :class:`XuiError` so panel outages do
    not crash the admin UI.
    """
    async with get_conn() as conn:
        plan = await plans_repo.get(conn, plan_id)
        if plan is None:
            text = f"Тариф #{plan_id} не найден."
            if edit:
                await message.edit_text(text)
            else:
                await message.answer(text)
            return
        inbound_ids = await plans_repo.get_inbounds(conn, plan_id)
    remarks = await _resolve_inbound_remarks(inbound_ids)
    kb = plan_card_kb(plan.id, is_active=plan.is_active)
    text = _format_plan(plan, remarks)
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


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
    """Accept the traffic limit (manual text path) and move to inbound select."""
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
    await state.update_data(traffic_gb=traffic_gb)
    await _enter_inbounds_step(message, state)


async def _enter_inbounds_step(
    message: Message, state: FSMContext, *, edit: bool = False
) -> None:
    """Load xui inbounds and switch the wizard into :class:`PlanCreate.waiting_inbounds`.

    Fetches the list via :func:`list_user_inbounds`, caches the options
    inside FSM data (``inbound_options``) so subsequent toggle/done
    callbacks can redraw the keyboard without another panel round-trip,
    and primes ``selected_inbounds`` to an empty list. If the panel is
    unavailable the wizard stays on the previous step and the user gets
    a popup error — there is nothing actionable to do without a list of
    inbounds.

    Called both from the manual-text traffic-gb path
    (:func:`st_traffic_gb`, ``edit=False`` — answers the user's text
    message) and from the preset-button path (:func:`cb_plan_preset` on
    the ``gb`` step, ``edit=True`` — edits the message that carried the
    inline keyboard in place instead of sending a new one).
    """
    send = message.edit_text if edit else message.answer
    try:
        xui = await get_xui_client()
        options = await list_user_inbounds(xui)
    except XuiError as exc:
        logger.warning("plans wizard: xui unavailable: {}", exc)
        await send(
            "Не удалось получить список подключений из 3x-ui. Попробуйте позже.",
            reply_markup=cancel_kb(),
        )
        return
    if not options:
        await send(
            "В 3x-ui нет активных подключений. Сначала включите хотя бы один inbound.",
            reply_markup=cancel_kb(),
        )
        return
    await state.set_state(PlanCreate.waiting_inbounds)
    await state.update_data(
        selected_inbounds=[],
        inbound_options=[
            {
                "id": opt.id,
                "remark": opt.remark,
                "port": opt.port,
                "enabled": opt.enabled,
            }
            for opt in options
        ],
    )
    await send(
        "Выберите подключения для тарифа:",
        reply_markup=plan_inbounds_select_kb(options, selected=set()),
    )


def _options_from_data(data: dict[str, object]) -> list[InboundOption]:
    """Rebuild :class:`InboundOption` list from FSM data.

    The wizard stores option dicts under ``inbound_options`` so we can
    redraw the multi-select keyboard on toggles without re-hitting the
    panel. This helper reconstructs the typed list back from raw dicts.
    """
    raw = data.get("inbound_options") or []
    options: list[InboundOption] = []
    for item in raw:  # type: ignore[union-attr]
        if not isinstance(item, dict):
            continue
        try:
            options.append(
                InboundOption(
                    id=int(item["id"]),
                    remark=str(item.get("remark") or ""),
                    port=int(item.get("port") or 0),
                    enabled=bool(item.get("enabled", True)),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return options


@router.callback_query(PlanCB.filter(F.action == "toggle_inbound"))
async def cb_toggle_inbound(
    callback: CallbackQuery,
    callback_data: PlanCB,
    state: FSMContext,
) -> None:
    """Flip the selection of one inbound in the multi-select screen.

    Works in both modes:

    * create wizard — FSM data has ``inbound_options`` populated and
      no ``editing_plan_id``;
    * edit flow — FSM data has ``editing_plan_id`` and ``inbound_options``
      populated by :func:`cb_edit_inbounds`.

    The actual differentiation is irrelevant here — both modes share the
    same ``selected_inbounds`` list and ``inbound_options`` cache, and
    this handler only mutates the former and redraws the keyboard from
    the latter.
    """
    inbound_id = callback_data.id
    data = await state.get_data()
    selected_raw = data.get("selected_inbounds") or []
    selected: list[int] = [int(x) for x in selected_raw]  # type: ignore[union-attr]
    if inbound_id in selected:
        selected.remove(inbound_id)
    else:
        selected.append(inbound_id)
    await state.update_data(selected_inbounds=selected)

    options = _options_from_data(data)
    if callback.message is not None and options:
        try:
            await callback.message.edit_reply_markup(
                reply_markup=plan_inbounds_select_kb(options, selected=set(selected))
            )
        except Exception as exc:  # noqa: BLE001 — best-effort redraw
            # Telegram raises if the markup did not change or the message
            # is too old; either way we can swallow it and just answer
            # the callback so the spinner stops.
            logger.debug("plans inbounds: redraw skipped: {}", exc)
    await callback.answer()


@router.callback_query(PlanCB.filter(F.action == "inbounds_done"))
async def cb_inbounds_done(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """Confirm the multi-select and either create or update the plan.

    Differentiates the two modes by the presence of ``editing_plan_id``
    in FSM data:

    * present → edit mode: call :func:`plans_repo.set_inbounds` on the
      existing plan and re-render its card;
    * absent → create mode: persist the plan via :func:`plans_repo.create`
      and attach the chosen inbounds.

    Empty selection in either mode triggers an alert without state
    transition — the user must pick at least one inbound to proceed.
    """
    data = await state.get_data()
    selected_raw = data.get("selected_inbounds") or []
    selected: list[int] = [int(x) for x in selected_raw]  # type: ignore[union-attr]
    if not selected:
        await callback.answer(
            "Выберите хотя бы одно подключение",
            show_alert=True,
        )
        return

    editing_plan_id = data.get("editing_plan_id")
    if editing_plan_id is not None:
        # Edit mode: update inbound set on an existing plan.
        async with get_conn() as conn:
            try:
                await plans_repo.set_inbounds(conn, int(editing_plan_id), selected)
            except LookupError:
                await state.clear()
                if callback.message is not None:
                    await callback.message.edit_text(
                        f"Тариф #{editing_plan_id} не найден."
                    )
                await callback.answer()
                return
        await state.clear()
        if callback.message is not None:
            await _show_card(callback.message, int(editing_plan_id), edit=True)
        await callback.answer("Подключения обновлены")
        return

    # Create mode: persist the plan with the collected wizard data.
    if callback.message is not None:
        await _finalize_plan_create(
            callback.message, state, selected_inbounds=selected, edit=True
        )
    await callback.answer()


async def _finalize_plan_create(
    message: Message,
    state: FSMContext,
    *,
    selected_inbounds: list[int],
    edit: bool = False,
) -> None:
    """Persist the plan with collected FSM data, clear state, render its card.

    Called from :func:`cb_inbounds_done` after the user confirms the
    inbound multi-select. All earlier wizard inputs (``title``/``days``/
    ``price``/``traffic_gb``) come from FSM data populated by previous
    steps; ``selected_inbounds`` is the just-confirmed inbound id list.

    ``edit=True`` edits the inbound multi-select message into the plan
    card instead of sending a new message (the inline-button path).
    """
    data = await state.get_data()
    title: str = data["title"]
    days: int = data["days"]
    price: int = data["price"]
    traffic_gb: int = data["traffic_gb"]

    async with get_conn() as conn:
        plan = await plans_repo.create(
            conn,
            title=title,
            days=days,
            price_stars=price,
            traffic_gb=traffic_gb,
        )
        await plans_repo.set_inbounds(conn, plan.id, selected_inbounds)
        inbound_ids = await plans_repo.get_inbounds(conn, plan.id)
    await state.clear()
    remarks = await _resolve_inbound_remarks(inbound_ids)
    send = message.edit_text if edit else message.answer
    await send(
        f"Тариф создан ✅\n\n{_format_plan(plan, remarks)}",
        reply_markup=plan_card_kb(plan.id, is_active=plan.is_active),
    )


# ---------------------------------------------------------------------------
# Preset / manual callbacks (shared across all 3 numeric wizard steps)
# ---------------------------------------------------------------------------


# Mapping: PlanCB.field (preset key) → (FSM-data key written, next state, next-step prompt+keyboard factory).
# The ``gb`` row has ``None`` for the next-state because it leaves the
# numeric path entirely — the handler hands off to
# :func:`_enter_inbounds_step` instead of moving to another preset step.
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
    either moves to the next numeric step (sending its preset keyboard)
    or — for the ``gb`` step — stores ``traffic_gb`` and hands off to
    :func:`_enter_inbounds_step`, which loads xui inbounds and renders
    the multi-select keyboard.
    """
    field = callback_data.field
    flow = _PRESET_FLOW.get(field)
    if flow is None:
        await callback.answer("Неизвестный шаг", show_alert=True)
        return
    data_key, next_state, prompt, kb_factory = flow
    value = callback_data.id

    # GB step: store and move to the inbound multi-select.
    if field == "gb":
        await state.update_data(traffic_gb=value)
        if callback.message is not None:
            await _enter_inbounds_step(callback.message, state, edit=True)
        await callback.answer()
        return

    await state.update_data(**{data_key: value})
    assert next_state is not None  # not the terminal step, narrowed above
    await state.set_state(next_state)
    if callback.message is not None and kb_factory is not None:
        await callback.message.edit_text(prompt, reply_markup=kb_factory())
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
        await callback.message.edit_text(text, reply_markup=cancel_kb())
    await callback.answer()


# ---------------------------------------------------------------------------
# Edit wizard
# ---------------------------------------------------------------------------


# Text-valued fields that route through :class:`PlanEdit.waiting_value`.
# The ``inbounds`` field is intentionally NOT here — it is handled by a
# dedicated multi-select branch (:func:`cb_edit_inbounds`).
_FIELD_LABELS = {
    "title": "новое название",
    "days": "новый срок в днях (целое > 0)",
    "price_stars": "новую цену в Stars (целое ≥ 0)",
    "traffic_gb": "новый лимит трафика в ГБ (целое ≥ 0; 0 = без лимита)",
}


@router.callback_query(PlanCB.filter((F.action == "edit") & (F.field == "inbounds")))
async def cb_edit_inbounds(
    callback: CallbackQuery,
    callback_data: PlanCB,
    state: FSMContext,
) -> None:
    """Open the inbound multi-select in edit mode for an existing plan.

    Loads the plan's current inbound set via :func:`plans_repo.get_inbounds`,
    fetches the full list of xui inbounds (:func:`list_user_inbounds`),
    stores both in FSM data (``editing_plan_id`` flags edit mode for
    :func:`cb_toggle_inbound` and :func:`cb_inbounds_done`), and renders
    the multi-select keyboard with the currently-attached ids pre-checked.

    On xui error the call is aborted with a popup — there is nothing to
    edit without a panel response. State is NOT advanced and the user
    can retry by tapping the field again.
    """
    plan_id = callback_data.id
    async with get_conn() as conn:
        plan = await plans_repo.get(conn, plan_id)
        if plan is None:
            await callback.answer(f"Тариф #{plan_id} не найден.", show_alert=True)
            return
        current = await plans_repo.get_inbounds(conn, plan_id)

    try:
        xui = await get_xui_client()
        options = await list_user_inbounds(xui)
    except XuiError as exc:
        logger.warning("plans edit inbounds: xui unavailable: {}", exc)
        await callback.answer(
            "Не удалось получить список подключений из 3x-ui. Попробуйте позже.",
            show_alert=True,
        )
        return
    if not options:
        await callback.answer(
            "В 3x-ui нет активных подключений.",
            show_alert=True,
        )
        return

    await state.set_state(PlanCreate.waiting_inbounds)
    await state.update_data(
        editing_plan_id=plan_id,
        selected_inbounds=list(current),
        inbound_options=[
            {
                "id": opt.id,
                "remark": opt.remark,
                "port": opt.port,
                "enabled": opt.enabled,
            }
            for opt in options
        ],
    )
    if callback.message is not None:
        await callback.message.edit_text(
            f"Подключения тарифа #{plan_id}:",
            reply_markup=plan_inbounds_select_kb(options, selected=set(current)),
        )
    await callback.answer()


@router.callback_query(PlanCB.filter(F.action == "edit"))
async def cb_edit(
    callback: CallbackQuery,
    callback_data: PlanCB,
    state: FSMContext,
) -> None:
    """Start :class:`PlanEdit` for a text-valued field.

    The ``field='inbounds'`` case is handled by :func:`cb_edit_inbounds`
    (its filter is more specific and is matched first by aiogram's router).
    """
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
