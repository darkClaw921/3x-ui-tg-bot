# app/services/billing.py::send_gift_invoice

Отправляет Stars-инвойс на покупку подарочного кода. Та же цена что send_invoice (промо применяется), но payload через build_gift_payload (kind='gift', gift=1) — successful_payment минтит код вместо подписки покупателю. Всегда новая подписка получателю (без sub_id/extend).
