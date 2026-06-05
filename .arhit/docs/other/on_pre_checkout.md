# on_pre_checkout

app/handlers/user/buy.py — обработчик pre_checkout_query. Парсит payload в InvoiceContext через billing.parse_invoice_payload, обращается к полям ctx.plan_id/promo_id/inbound_id/sub_id. ctx.kind — точка расширения (buy сейчас; topup/gift/sub в Ф2-4). Re-валидирует план+промо read-only, для extend-флоу (sub_id>0) проверяет владение подпиской, для нового — allow-list inbound.
