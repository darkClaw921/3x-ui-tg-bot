# test_services_billing

tests/test_services_billing.py — тесты app/services/billing: price math, payload (build/parse), send_invoice. Покрытие Ф0: InvoiceContext (frozen, итерация как legacy 4-tuple), legacy-совместимость (payload без 'k' → kind='buy'), новые kind topup/gift/sub (round-trip билдеров), байт-лимит _PAYLOAD_BYTE_LIMIT=128 для всех билдеров, create_subscription_invoice_link (subscription_period=2592000, XTR, provider_token='').
