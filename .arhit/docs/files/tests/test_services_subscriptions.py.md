# tests/test_services_subscriptions.py

Юнит-тесты для app.services.subscriptions. Покрытие: _expiry_ms, _parse_iso, _bonus_days_from_promo, create_or_extend (новая подписка, продление, аноморал прошлой даты, провал xui блокирует DB), activate_free_days (валидация типа, провижен), revoke (зелёный/чёрный путь), проброс username в make_client_email, и проброс traffic_gb: total_gb=plan.traffic_gb для create_or_extend (case 0 и 50), total_gb=0 для activate_free_days, и отсутствие totalGB в update_client при продлении (сохранение квоты).
