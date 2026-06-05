# app/services/subscriptions.py::activate_trial

Сервис активации пробной подписки (один trial на юзера). Сигнатура: activate_trial(conn, xui, user, *, inbound_id, days, traffic_gb). Переиспользует _provision (xui-first, DB-after) с plan_id=None, is_trial=True. Защита 'один trial': (1) дешёвый pre-check subs_repo.has_trial → TrialAlreadyUsedError до обращения к панели (без orphan-клиента); (2) backstop — IntegrityError от partial-unique idx_subscriptions_one_trial при гонке → TrialAlreadyUsedError. Конфиг TRIAL_DAYS (0=выкл), TRIAL_TRAFFIC_GB. Также добавлен класс TrialAlreadyUsedError.
