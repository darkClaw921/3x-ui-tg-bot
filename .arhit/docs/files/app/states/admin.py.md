# app/states/admin.py

FSM-группы админ-флоу для управления тарифами, промокодами и поиска пользователей.

PlanCreate — мастер создания тарифа:
- waiting_title (text) → waiting_days (int, presets через PlanCB.preset) → waiting_price (int, presets) → waiting_traffic_gb (int, 0 = безлимит, presets) → waiting_inbounds (multi-select callbacks PlanCB.toggle_inbound, завершение через PlanCB.inbounds_done; пустое множество ≡ все доступные inbounds).
- После waiting_inbounds — INSERT в plans и plan_inbounds (если множество не пустое), state.clear().

PlanEdit — редактирование одного поля существующего тарифа:
- waiting_field (callback PlanCB.edit с field ∈ {title, days, price_stars, traffic_gb, inbounds}) → waiting_value (текстовый ввод).
- Для field='inbounds' хендлер не использует waiting_value: вместо этого открывается multi-select экран (plan_inbounds_select_kb), редактирующий plan_id из state-data; завершение сохраняет через plans_repo.set_inbounds.

AdminSearchUser — единственное состояние waiting_query (tg_id число или @username).

PromoCreate — мастер промокода: waiting_code → waiting_type (callback) → waiting_value → waiting_max_uses → waiting_expires_at.
