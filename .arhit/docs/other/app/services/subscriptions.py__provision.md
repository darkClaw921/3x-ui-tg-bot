# app/services/subscriptions.py:_provision

Внутренняя функция провижена/продления подписки. Параметры (kwargs only): conn, xui, user, delta_days, plan_id, total_gb (default 0). Сначала xui (add_client при первом провижене, update_client при продлении), затем DB (subs_repo). На продлении НЕ передаёт totalGB в update_client — это сохраняет остаток квоты пользователя. total_gb применяется только при свежем add_client (передаётся из plan.traffic_gb через create_or_extend; 0 для activate_free_days).
