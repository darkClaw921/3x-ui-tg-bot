# parse_invoice_payload

app/services/billing.py — декодирует строку invoice payload в InvoiceContext. Дискриминатор 'k': отсутствует → kind='buy' (вся legacy-совместимость); 'topup' → пополнение кошелька (несёт 't' Stars, plan/inbound=0); 'gift' → подарок (gift=1, ключи p/r/i); 'sub' → нативная Star-подписка. Принимает legacy long-keys plan_id/promo_id и fallback inbound_id на settings.XUI_INBOUND_ID с WARNING-логом. Ключ 's' (sub_id) опционален → 0. Бросает ValueError на битый payload.
