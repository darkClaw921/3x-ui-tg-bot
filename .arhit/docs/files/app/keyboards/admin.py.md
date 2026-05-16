# app/keyboards/admin.py

Inline-клавиатуры админ-флоу через InlineKeyboardBuilder.

CallbackData-фабрики:
- AdminCB(prefix='adm', area, action) — навигация (area ∈ main/plans/promos/users/stats, action ∈ open/back/cancel).
- PlanCB(prefix='admp', action, id=0, field='') — list/create/card/edit_menu/edit/deactivate; field ∈ title/days/price_stars.
- PromoCB(prefix='admpr', action, id=0, field='') — list/create/card/deactivate/redemptions/type; field ∈ percent/flat_stars/free_days.
- UserCB(prefix='admu', action, id=0, user_id=0) — поиск/карточка/мутации в админском 'Пользователи'; action ∈ search/card/revoke/toggle_admin. Для revoke: id=sub_id, user_id=users.id.
- StatsCB(prefix='adms', action, field='') — экран статистики; action ∈ open/period/refresh; field несёт период (7d/30d/all) — stateless через callback.

Функции:
- admin_main_menu() — 4 кнопки (Тарифы / Промокоды / Пользователи / Статистика).
- back_to_main_kb() — одна кнопка «В меню».
- cancel_kb() — одна кнопка «✖ Отмена» для FSM-wizard'ов.
- plans_list_kb(plans) — список тарифов + «Создать» + «В меню». Inactive с префиксом 🔒.
- plan_card_kb(plan_id, is_active=True) — Редактировать / Деактивировать / Назад.
- plan_edit_fields_kb(plan_id) — выбор поля (Название/Срок/Цена) + Назад.
- promos_list_kb(promos) — список промокодов + «Создать» + «В меню». Исчерпанные с префиксом 🔒.
- promo_type_kb() — percent / flat_stars / free_days + Отмена.
- promo_card_kb(promo_id, is_active=True) — Redemptions / Деактивировать / Назад.
- user_card_kb(user_id, *, active_sub_id=None, is_admin=False) — кнопки карточки пользователя: «Отозвать активную подписку» (если active_sub_id), «Сделать/Снять админа», «Найти другого», «В меню».
- stats_kb(active_period='30d') — переключатель 7д/30д/Всё время (текущий с обёрткой «· text ·»), «🔄 Обновить» с current_period в payload, «В меню».

callback_data всегда укладывается в Telegram-лимит 64 байта.
