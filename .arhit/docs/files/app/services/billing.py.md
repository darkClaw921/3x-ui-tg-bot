# app/services/billing.py

Билдер Stars-инвойсов и роутинг состояния платежа через payload.

Публичные:
- calc_price(plan, promo) -> InvoicePrice — конечная Stars-цена с floor=1 (Telegram-минимум). Дельта дней (для free_days) возвращается в extra_days.
- build_invoice_payload(plan_id, promo_id, inbound_id, *, sub_id=0) -> str — компактный JSON ('p'/'r'/'i'/'s' single-letter keys), под 128-байтовый лимит Telegram. Ключ 's' опускается при sub_id=0 (обратная совместимость и экономия байт).
- parse_invoice_payload(payload) -> tuple[int, int|None, int, int] — возвращает (plan_id, promo_id, inbound_id, sub_id). Принимает legacy-payloads (long-keys 'plan_id'/'promo_id', отсутствие 'i'/'s'). Отсутствующий 's' → sub_id=0.
- send_invoice(bot, chat_id, plan, promo, *, inbound_id, sub_id=0) -> Message — отправляет Stars-инвойс. При sub_id>0 в описании ('Продление подписки #N') и payload.

Контекст: payload — единственный канал состояния между sendInvoice и successfulPayment (FSM может быть очищен Telegram-ом). sub_id>0 сигналит handler-у, что эту оплату нужно применить как extend конкретной подписки.
