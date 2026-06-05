# app/handlers/user/buy.py::on_successful_payment

Финализация платежа (идемпотентно по telegram_charge_id UNIQUE). Ветки по ctx.kind: topup→_credit_topup; gift (или ctx.gift)→_mint_gift (записать payment, make_gift_code(payment_id) внутри not-duplicate ветки, DM покупателю код+ссылку ?start=gift_<code>, БЕЗ провижининга подписки покупателю); иначе buy/extend (create_or_extend, payment, promo apply, Step 6b referral reward best-effort, deliver_keys). Gift-минт защищён UNIQUE charge_id (код минтится максимум один раз).
