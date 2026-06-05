# create_subscription_invoice_link

app/services/billing.py — создаёт нативную recurring Star-подписку через bot.create_invoice_link(subscription_period=SUBSCRIPTION_PERIOD_SECONDS=2592000, currency='XTR', provider_token=''). Telegram биллит каждые 30 дней. subscription_period есть ТОЛЬКО в create_invoice_link, не в send_invoice, значение строго 2592000. Промо не применяются к recurring. Payload через build_subscription_payload {'k':'sub'}. Используется в Ф4.
