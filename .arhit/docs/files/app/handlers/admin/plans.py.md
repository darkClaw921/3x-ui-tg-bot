# app/handlers/admin/plans.py

Хендлеры CRUD тарифов для админ-флоу (роутер 'admin_plans').

Структура:
- _format_plan(plan, inbound_remarks=None) — карточка тарифа (HTML): id, название, срок, цена, трафик, статус. Если передан inbound_remarks (dict[int,str]) — добавляется строка 'Подключения: <remark1>, <remark2>'. Для inbound, отсутствующих в панели (пустая строка), рендерится 'id=NN (удалён)'. Если inbound_remarks=None, строка про подключения опускается.
- _resolve_inbound_remarks(inbound_ids) — резолвит remark'и через app.services.inbounds.list_user_inbounds. При XuiError graceful degrade: возвращает dict с пустыми remark для всех id (карточка рендерится без названий).
- _show_card(message, plan_id, edit=True) — рендер карточки: тянет plan + plans_repo.get_inbounds + _resolve_inbound_remarks.
- _show_list — список тарифов (active first), используется в plans_list_kb.

Навигация (callback handlers):
- cb_open — вход из admin_main_menu (AdminCB area=plans, action=open).
- cb_list — список (PlanCB action=list).
- cb_card — карточка (PlanCB action=card, id=plan_id).
- cb_edit_menu — клавиатура выбора поля для редактирования.
- cb_deactivate — soft-disable + перерисовка.

Мастер PlanCreate (5 шагов):
- cb_create — вход (PlanCB action=create) → state PlanCreate.waiting_title.
- st_title → waiting_days, показ plan_days_presets_kb.
- st_days → waiting_price, показ plan_price_presets_kb.
- st_price → waiting_traffic_gb, показ plan_gb_presets_kb.
- st_traffic_gb → переход в _enter_inbounds_step.
- _enter_inbounds_step(message, state) — загружает list_user_inbounds, кэширует options в FSM data ('inbound_options', сериализованные dict'ы), инициализирует selected_inbounds=[], показывает plan_inbounds_select_kb. При XuiError или пустом списке — сообщение об ошибке, state не двигается.
- _options_from_data(data) — реконструирует list[InboundOption] из FSM data для перерисовки клавиатуры без повторного запроса к 3x-ui.
- cb_toggle_inbound (PlanCB action=toggle_inbound, id=inbound_id) — XOR id в selected_inbounds, перерисовывает клавиатуру (edit_reply_markup). Общий для create и edit.
- cb_inbounds_done (PlanCB action=inbounds_done) — финализация. Пустой selected → callback.answer('Выберите хотя бы одно подключение', show_alert=True). Иначе: если в state есть editing_plan_id → edit-режим (plans_repo.set_inbounds + _show_card); иначе → _finalize_plan_create.
- _finalize_plan_create(message, state, *, selected_inbounds) — plans_repo.create(...) + plans_repo.set_inbounds(plan.id, selected) + рендер карточки с подключениями.

Preset/manual callbacks:
- _PRESET_FLOW — мапа field → (data_key, next_state, prompt, kb_factory). Шаг gb имеет None для next_state (передаёт управление _enter_inbounds_step).
- cb_plan_preset — обрабатывает preset-кнопки на шагах days/price/gb. На gb: записывает traffic_gb + вызывает _enter_inbounds_step.
- cb_plan_manual — переключение шага в ручной ввод.

Edit wizard:
- _FIELD_LABELS — словарь для текстовых полей (title/days/price_stars/traffic_gb). inbounds НЕ входит — у него отдельный multi-select handler.
- cb_edit_inbounds (PlanCB action=edit, field=inbounds) — отдельная ветка. Загружает текущие inbound'ы из БД + options через list_user_inbounds. Кладёт в state: editing_plan_id, selected_inbounds=list(current), inbound_options. Отображает plan_inbounds_select_kb(options, selected=set(current)). State устанавливается в PlanCreate.waiting_inbounds (общий с мастером, различение через editing_plan_id). При XuiError — alert.
- cb_edit (PlanCB action=edit, field в _FIELD_LABELS) — текстовое редактирование через PlanEdit.waiting_value. Регистрируется ПОСЛЕ cb_edit_inbounds (фильтр менее специфичен).
- st_edit_value — валидация + plans_repo.update.

Зависимости:
- app.db.repos.plans (plans_repo): get/create/list_all/update/deactivate, get_inbounds/set_inbounds.
- app.keyboards.admin: AdminCB, PlanCB, cancel_kb, plan_card_kb, plan_*_presets_kb, plan_inbounds_select_kb, plan_edit_fields_kb, plans_list_kb.
- app.services.inbounds: InboundOption, list_user_inbounds (с TTL-кэшем).
- app.states.admin: PlanCreate (5 состояний), PlanEdit.
- app.xui: XuiError, get_xui_client.
