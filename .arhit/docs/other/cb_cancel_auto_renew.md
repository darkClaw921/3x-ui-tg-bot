# cb_cancel_auto_renew

Handlers in app/handlers/user/my_subscription.py: cb_cancel_auto_renew (SubCB action=cancel_renew) and cb_enable_auto_renew (action=enable_renew) toggle a native Star subscription's recurring billing via bot.edit_user_star_subscription(user_id, telegram_payment_charge_id=sub.tg_sub_charge_id, is_canceled=...) then mirror locally via set_auto_renew. Shared by _toggle_auto_renew with ownership + tg_sub_charge_id guards. Buttons rendered per-sub in _build_subs_keyboard for subscriptions with a charge id.
