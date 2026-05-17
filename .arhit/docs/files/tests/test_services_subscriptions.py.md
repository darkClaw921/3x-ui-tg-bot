# tests/test_services_subscriptions.py

Тесты для app.services.subscriptions — create_or_extend, activate_free_days, revoke.

Покрытие (20 тестов):
- Хелперы: _expiry_ms, _parse_iso (T/space separator, microseconds fallback), _bonus_days_from_promo.
- create_or_extend: создаёт новый sub при отсутствии активной подписки, продлевает существующую (update_client с новым expiryTime), free_days promo добавляет дни.
- create_or_extend kwargs: пробрасывает user.username в make_client_email, traffic_gb plan'а в add_client(total_gb=), inbound_id kwarg.
- extend path: update_client НЕ получает totalGB (сохраняем накопленный квоту юзера).
- create_or_extend xui failure: XuiError → DB-запись не создаётся, sub не появляется в БД.
- create_or_extend anchor: stale active row с past expires_at → новый sub от now (full delta).
- activate_free_days: provisions для free_days promo (sub.plan_id=None, total_gb=0), отказ для non-free_days (ValueError).
- revoke: вызывает update_client(enable=False) + переводит status в revoked; даже при xui failure флипает status.

Все тесты обновлены под новый kwarg inbound_id=1 в create_or_extend/activate_free_days (после Phase 2).

См. также: app/services/subscriptions.py.
