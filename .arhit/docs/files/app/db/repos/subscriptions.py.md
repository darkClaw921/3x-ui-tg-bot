# app/db/repos/subscriptions.py

Репозиторий подписок + traffic_snapshots + subscription_notifications.

Литералы:
- SubscriptionStatus = Literal['active','expired','revoked'].
- NotificationKind = Literal['3d','1d','0d','expired'].

Dataclasses:
- Subscription(id, user_id, xui_inbound_id, xui_client_uuid, xui_client_email, xui_sub_id, expires_at, created_at, plan_id, status).
- TrafficSnapshot(id, subscription_id, up, down, taken_at).

Helpers:
- _to_iso(value), _utcnow_iso().

Основные функции:
- create(conn, user_id, xui_inbound_id, xui_client_uuid, xui_client_email, expires_at, plan_id, xui_sub_id='') -> Subscription.
- get(conn, sub_id) -> Subscription | None.
- get_active_for_user(conn, user_id) -> Subscription | None — одна последняя active с expires_at>now (используется для backward-compat 'есть ли вообще активная').
- list_for_user(conn, user_id) -> list[Subscription] — все подписки (active+expired+revoked), ORDER BY created_at DESC, id DESC. Используется в 'Моя подписка'.
- list_active_for_user(conn, user_id) -> list[Subscription] — все active с expires_at>now, ORDER BY expires_at DESC, id DESC. Используется handlers/UI для рендера action-экранов (buy/promo) и кнопок 'Продлить #N'. Базовая функция для модели 'N активных подписок на пользователя'.
- list_active(conn), list_expired_active(conn, now=None) (для expire-job), list_expiring_in(conn, days) (для reminder-job), extend(conn, sub_id, new_expires_at), set_status(conn, sub_id, status).
- add_traffic_snapshot, last_traffic_snapshot.
- try_mark_notification_sent(conn, sub_id, kind) -> bool — INSERT OR IGNORE в subscription_notifications с UNIQUE(sub_id,kind). True если запись вставлена, False если уже существовала. Используется scheduler-job-ами для дедупликации напоминаний.

Бизнес-логика: подписка = один xui-client на конкретном inbound. У одного пользователя может быть N активных одновременно (поэтому list_active_for_user отдаёт массив, а get_active_for_user — одну для legacy-вызовов).
