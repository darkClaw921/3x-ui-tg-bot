# app/handlers/admin/plans.py

Хэндлеры CRUD тарифов с FSM-флоу мастера создания и редактирования.

router = Router(name='admin_plans').

Helpers:
- _format_plan(plan) — HTML-карточка тарифа (включая traffic_gb).
- _show_card(message, plan_id, edit=True), _show_list(message, edit=True) — сортировка active→inactive.

Базовые callback-ы:
- cb_open (AdminCB area=plans action=open) — точка входа из админ-меню, очищает state, рендерит список.
- cb_list (PlanCB action=list) — повторный показ списка.
- cb_card (PlanCB action=card, id=<plan_id>).
- cb_edit_menu (PlanCB action=edit_menu) — клавиатура выбора поля (title/days/price_stars/traffic_gb).
- cb_deactivate (PlanCB action=deactivate).

Wizard PlanCreate (4 шага): cb_create → st_title → st_days → st_price → st_traffic_gb.
- На каждом численном шаге (days/price/gb) выдаётся пресет-клавиатура (plan_days_presets_kb / plan_price_presets_kb / plan_gb_presets_kb), ручной текстовый ввод по-прежнему работает.
- st_traffic_gb принимает non-negative int (0 = без лимита, соответствует xui totalGB).
- Валидация: title непустой, days>0, price_stars≥0, traffic_gb≥0. При невалидном вводе переспрашивает без сброса FSM (повторно шлёт ту же пресет-клавиатуру).
- _finalize_plan_create(message, state, traffic_gb) — общая точка финализации (вызывается и из st_traffic_gb, и из cb_plan_preset на шаге gb). Делает plans_repo.create(title, days, price_stars, traffic_gb) и рендерит карточку.

Общие preset/manual callback-и (PlanCB action ∈ {preset, manual}, field ∈ {days, price, gb}):
- _PLAN_STEP_FLOW: dict[str, tuple[fsm_key, next_state, prompt_factory]] — мапа шага мастера на FSM-ключ, следующее состояние и фабрику клавиатуры/подсказки.
- cb_plan_preset(callback, callback_data, state): записывает callback_data.id в FSM-data под нужным ключом; для шага 'gb' финализирует через _finalize_plan_create; для остальных переходит в следующее состояние и шлёт пресеты следующего шага.
- cb_plan_manual(callback, callback_data): переключает шаг на ручной ввод — state остаётся waiting_*, посылается подсказка с текстом «введите N». Универсальная отмена через AdminCB(area=main, action=cancel).

Wizard PlanEdit:
- cb_edit (PlanCB action=edit, id=<plan_id>, field ∈ title/days/price_stars/traffic_gb) → st_edit_value.
- st_edit_value — записывает значение через plans_repo.update; LookupError на отсутствующий plan_id.

Константа _FIELD_LABELS — подсказки при редактировании.
