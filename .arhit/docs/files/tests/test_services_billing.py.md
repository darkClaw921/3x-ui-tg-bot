# tests/test_services_billing.py

Тесты для app.services.billing — расчёт цены, payload и send_invoice.

Покрывает:
- calc_price: проценты, flat_stars, free_days, clamp (>100% → 100%, <0 → 0), floor на Stars-min (=1), unknown type fallback.
- build_invoice_payload: новый формат с короткими ключами p/r/i (plan_id/promo_id/inbound_id), promo_id=0 → None, promo_id=None.
- parse_invoice_payload: возвращает 3-tuple (plan_id, promo_id, inbound_id); валидирует bad json / not object / missing plan_id / bad types.
- Legacy payload: payload без 'i' (старые ключи plan_id/promo_id) → fallback на settings.XUI_INBOUND_ID + WARNING лог.
- Patched fallback: настраиваемый settings.XUI_INBOUND_ID через monkey_settings.
- Payload byte limit: <=128 байт для 10-значных id; превышение → ValueError.
- send_invoice: currency='XTR', provider_token='', amount = price, inbound_id вшит в payload (data['i']), promo_id вшит как 'r'.

Использует mock_bot фикстуру для AsyncMock(Bot).

См. также: app/services/billing.py.
