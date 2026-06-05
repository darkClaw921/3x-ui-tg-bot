# cb_subscribe

Handler (app/handlers/user/buy.py) for BuyCB(action='sub'): offers a native recurring Telegram Star subscription. Gated by AUTO_RENEW_ENABLED; re-validates plan + inbound allow-list, then calls billing.create_subscription_invoice_link (kind='sub', subscription_period=2592000) and edits the message to show a subscription_link_kb URL button. Surfaced on the confirm card only for eligible 30-day, new, non-gift purchases (_offers_subscription).
