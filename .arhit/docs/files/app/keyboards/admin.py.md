# app/keyboards/admin.py

Inline-клавиатуры админ-флоу (плюс CallbackData-фабрики).

CallbackData-фабрики:
- AdminCB(area, action) — навигация верхнего уровня (main/plans/promos/users/stats × open/back/cancel).
- PlanCB(action, id=0, field='') — CRUD тарифов. action ∈ {list, create, card, edit_menu, edit, deactivate, preset, manual, toggle_inbound, inbounds_done}. Поле id переиспользуется: для toggle_inbound оно хранит inbound_id, для preset — выбранное числовое значение. field ∈ {title, days, price_stars, traffic_gb, inbounds} в режиме edit; {days, price, gb} в режиме preset/manual.
- UserCB(action, id=0, user_id=0) — действия над user card.
- StatsCB(action, field='') — статистика.
- PromoCB(action, id=0, field='') — CRUD промокодов.

Ключевые клавиатуры:
- admin_main_menu — Тарифы/Промокоды/Пользователи/Статистика.
- plans_list_kb(plans) — список тарифов с пометкой 🔒 для неактивных.
- plan_card_kb(plan_id, is_active) — карточка тарифа: Редактировать / Деактивировать / Назад.
- plan_edit_fields_kb(plan_id) — выбор поля для редактирования: Название / Срок / Цена / Лимит трафика / 🔌 Подключения / Назад. Кнопка «Подключения» отправляет PlanCB(action='edit', id=plan_id, field='inbounds') — хендлер открывает multi-select экран.
- plan_inbounds_select_kb(options, selected) — multi-select inbounds (Phase 3). Каждый InboundOption отображается строкой '☑/☐ <remark> (port <port>)' (☑ если option.id ∈ selected). callback_data: PlanCB(action='toggle_inbound', id=inbound_id). Внизу '✅ Готово' (PlanCB action='inbounds_done') и '✖ Отмена' (AdminCB area='main', action='cancel').
- Пресет-клавиатуры мастера: plan_days_presets_kb, plan_price_presets_kb, plan_gb_presets_kb.
- promos_list_kb / promo_card_kb / promo_type_kb + пресеты promo_value/max_uses/expires.
- user_card_kb, stats_kb.
