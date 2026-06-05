# app/services/billing.py

Добавлена async send_topup_invoice(bot,chat_id,stars,*,lang=DEFAULT_LANG)->Message: отправляет Stars-инвойс пополнения кошелька. Payload через build_topup_payload(stars) (kind='topup'), без plan/inbound. stars=max(_STARS_MIN,stars). LabeledPrice=stars, currency='XTR', provider_token=''. Тексты title/label/description локализованы через t() (wallet.invoice_*). Импортированы DEFAULT_LANG,t из app.i18n. Добавлен в __all__.
