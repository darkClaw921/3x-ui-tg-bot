# app/services/subscriptions.py

Единая точка создания и продления подписок (xui-first, DB-after).

Назначение:
- Согласованное создание клиента в 3x-ui и записи в локальной таблице subscriptions. Порядок: сначала xui (add_client/update_client), затем DB (subs_repo.create/extend); при сбое DB остаётся orphan-клиент на панели, который виден админу — это лучше, чем заряд Stars без VPN-доступа.

Публичный API:
- create_or_extend(conn, xui, user, plan, promo, *, inbound_id: int) -> Subscription: создаёт новую подписку в указанном inbound_id или продлевает существующую (тогда inbound_id игнорируется, см. ниже). delta_days = plan.days + bonus_days(promo) (только free_days).
- activate_free_days(conn, xui, user, promo, *, inbound_id: int) -> Subscription: фриф флоу промокодов type=free_days; promo.type != 'free_days' → ValueError. inbound_id используется только при создании fresh-подписки.
- revoke(xui, sub): soft-disable клиента в xui (enable=False) и сделать subs_repo.set_status(..., 'revoked'); ошибки xui логируются как warning и не блокируют DB-обновление.

Логика extend:
- Если у пользователя есть active-подписка: используется existing.xui_inbound_id (а не переданный inbound_id), чтобы не плодить дубликаты клиентов на панели.
- Если переданный inbound_id != existing.xui_inbound_id — логируется WARNING с subscription_id, существующим и запрошенным inbound_id (обычно означает, что UI не должен был показывать выбор inbound на повторной покупке).
- При extend не сбрасываем totalGB (update_client не трогает квоту).

Внутренние хелперы:
- _expiry_ms(dt): UNIX-таймстамп в миллисекундах для xui (0 = бессрочно).
- _parse_iso(value): робастный парсинг ISO-8601 из репо в timezone-aware UTC datetime.
- _bonus_days_from_promo(promo): возвращает int(promo.value) только для type='free_days', иначе 0.
- _make_sub_id(): делегирует app.xui.clients._make_sub_id для совместимости с дефолтом add_client.
- _provision(*, conn, xui, user, delta_days, plan_id, total_gb=0, inbound_id): общий путь create_or_extend и activate_free_days.

Зависимости:
- app.db.repos.subscriptions, app.db.repos.users, app.db.repos.plans, app.db.repos.promos.
- app.xui.clients (add_client, update_client, make_client_uuid, make_client_email).
- loguru для info/warning.

Замечание: settings.XUI_INBOUND_ID более НЕ используется в этом модуле — inbound_id всегда передаётся явно вызывающим (handlers/buy, handlers/promo).
