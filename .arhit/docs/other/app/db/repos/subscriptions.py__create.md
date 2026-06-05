# app/db/repos/subscriptions.py::create

Вставляет новую активную подписку. Поддерживает is_trial (по умолчанию False) — при True insert подчиняется partial-unique индексу idx_subscriptions_one_trial (UNIQUE(user_id) WHERE is_trial=1); второй trial для того же юзера => IntegrityError. Колонки: user_id, xui_inbound_id, xui_client_uuid, xui_client_email, xui_sub_id, expires_at, plan_id, status='active', is_trial.
