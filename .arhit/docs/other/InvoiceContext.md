# InvoiceContext

Frozen+slots dataclass (app/services/billing.py) — структурированный декод invoice payload, единственный канал состояния между отправкой Stars-инвойса и successful_payment. Поля: plan_id, promo_id, inbound_id, sub_id, kind (Literal 'buy'/'topup'/'gift'/'sub', по умолчанию 'buy'), gift (int marker), topup (int Stars). Итерируется как legacy 4-tuple (plan_id, promo_id, inbound_id, sub_id) через __iter__ для обратной совместимости со старыми распаковками. Возвращается из parse_invoice_payload.
