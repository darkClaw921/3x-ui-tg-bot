# on_successful_payment

app/handlers/user/buy.py — финализация оплаченного Stars-инвойса (идемпотентно по telegram_payment_charge_id). Парсит payload в InvoiceContext (ctx.kind — точка расширения для Ф2-4), доступ через ctx.plan_id/promo_id/inbound_id/sub_id. Шаги: idempotency → parse → refresh plan/promo → create_or_extend (xui-first) → record payment → redeem promo (best-effort) → deliver keys.
