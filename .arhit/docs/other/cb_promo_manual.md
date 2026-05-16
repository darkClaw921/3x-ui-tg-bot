# cb_promo_manual

Callback-хендлер кнопки '✏ Ввести вручную' в мастере промокода (app/handlers/admin/promos.py). Фильтр: PromoCB.filter(F.action == 'manual'). По callback_data.field (value/max_uses/expires) шлёт подсказку с cancel_kb(). State НЕ меняет — уже в waiting_*, текстовый хендлер примет ввод.
