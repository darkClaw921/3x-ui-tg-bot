# app/keyboards/admin.py

Inline-клавиатуры админ-флоу через aiogram InlineKeyboardBuilder.

CallbackData-фабрики (короткие prefix-ы — payload <= 64 байта):
- AdminCB(prefix='adm', area, action) — навигация (area ∈ main/plans/promos/users/stats, action ∈ open/back/cancel).
- PlanCB(prefix='admp', action, id=0, field='') — plan CRUD + пресет-кнопки мастера. action ∈ list/create/card/edit_menu/edit/deactivate/preset/manual. Для preset поле id несёт выбранное целочисленное значение; field ∈ title/days/price_stars/traffic_gb (edit) или days/price/gb (preset/manual).
- PromoCB(prefix='admpr', action, id=0, field='') — promo CRUD + пресет-кнопки мастера. action ∈ list/create/card/deactivate/redemptions/type/preset/manual. field ∈ percent/flat_stars/free_days (type) или value/max_uses/expires (preset/manual). Для preset/expires id = число дней от now, 0 = бессрочно.
- UserCB(prefix='admu', action, id=0, user_id=0) — поиск/карточка/мутации.
- StatsCB(prefix='adms', action, field='') — экран статистики.

Базовые клавиатуры: admin_main_menu, back_to_main_kb, cancel_kb.

Plans:
- plans_list_kb(plans) — список тарифов + Создать + В меню.
- plan_card_kb(plan_id, is_active=True) — Редактировать / Деактивировать / Назад.
- plan_edit_fields_kb(plan_id) — Название / Срок / Цена / Лимит трафика (ГБ) / Назад.

Пресет-клавиатуры мастера тарифа (общий помощник _plan_preset_kb, кнопки несут PlanCB(action='preset', field=<step>, id=<value>) + PlanCB(action='manual', field=<step>) + AdminCB cancel):
- plan_days_presets_kb() — для PlanCreate.waiting_days: 7/14/30/90/180/365.
- plan_price_presets_kb() — для PlanCreate.waiting_price: 0/50/100/200/500/1000 ⭐.
- plan_gb_presets_kb() — для PlanCreate.waiting_traffic_gb: 0/10/50/100/250/500 ГБ (0 = без лимита, как и в xui totalGB).

Promos:
- promos_list_kb, promo_type_kb, promo_card_kb.

Пресет-клавиатуры мастера промокода (общий помощник _promo_preset_kb):
- promo_value_presets_kb(promo_type) — для PromoCreate.waiting_value, набор зависит от типа: percent 5/10/15/25/50%, flat_stars 25/50/100/250/500 ⭐, free_days 1/3/7/14/30 дней; неизвестный тип → manual-only.
- promo_max_uses_presets_kb() — для PromoCreate.waiting_max_uses: 0/1/5/10/50/100 (0 = ∞).
- promo_expires_presets_kb() — для PromoCreate.waiting_expires_at: бессрочно/+7д/+30д/+90д/+365д; id несёт число дней.

Users: user_card_kb. Stats: stats_kb.
