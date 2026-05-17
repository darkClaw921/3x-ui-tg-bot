# app/services/billing.py

Расчёт цены Stars-инвойсов и сериализация состояния в payload.

Назначение:
- Единственный канал передачи стейта между send_invoice → pre_checkout_query → successful_payment: Telegram эхом возвращает invoice_payload, и это единственный надёжный канал, поскольку FSM может быть очищен.

Публичный API:
- InvoicePrice (dataclass frozen slots): {stars:int >= _STARS_MIN, raw_discount:DiscountResult, extra_days:int}.
- calc_price(plan, promo) -> InvoicePrice: вызывает promos.compute_discount и поднимает цену до _STARS_MIN=1 (Telegram запрещает invoice с amount=0; полностью бесплатные сценарии должны идти через free_days флоу).
- build_invoice_payload(plan_id:int, promo_id:int|None, inbound_id:int) -> str: возвращает компактный JSON {'p':plan_id, 'r':promo_id|null, 'i':inbound_id} (короткие ключи, <128 байт даже для 99999/99999/99999).
- parse_invoice_payload(payload:str) -> tuple[int, int|None, int]: возвращает (plan_id, promo_id, inbound_id). Принимает И новые ('p','r','i'), И legacy ('plan_id','promo_id', без 'i') payload-ы. Если ключа 'i' нет — fallback на settings.XUI_INBOUND_ID с WARNING-логом (для in-flight invoice-ов созданных до раскатки). Невалидный JSON / неверные типы → ValueError.
- send_invoice(bot, chat_id, plan, promo, *, inbound_id:int) -> Message: обёртка над bot.send_invoice; currency='XTR', provider_token='', payload включает inbound_id.

Константы:
- _STARS_MIN = 1 — минимум Stars (Telegram возвращает 400 при amount=0).
- _PAYLOAD_BYTE_LIMIT = 128 — sanity check на JSON.

Внутренние хелперы:
- _invoice_title(plan), _invoice_description(plan, price, promo): локализованные заголовок и описание для invoice-карты.

Зависимости:
- aiogram (Bot, LabeledPrice, Message).
- app.services.promos.compute_discount, DiscountResult.
- app.config.settings для legacy-fallback inbound_id.
- loguru для warning о legacy-payload.
