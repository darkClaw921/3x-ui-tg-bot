# app/states/admin.py

FSM-стейты админ-флоу (aiogram StatesGroup).

- PlanCreate(waiting_title, waiting_days, waiting_price) — wizard создания тарифа.
- PlanEdit(waiting_field, waiting_value) — wizard редактирования одного поля; plan_id и field хранятся в FSMContext data.
- PromoCreate(waiting_code, waiting_type, waiting_value, waiting_max_uses, waiting_expires_at) — wizard создания промокода.
- AdminSearchUser(waiting_query) — поиск пользователя по tg_id (цифры) или @username; handler сразу резолвит и чистит state.
