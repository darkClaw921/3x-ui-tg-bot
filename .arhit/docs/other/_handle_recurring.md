# _handle_recurring

Handler helper (app/handlers/user/buy.py): finalises native recurring Star subscription payments. First charge (is_first_recurring) -> create_or_extend(extend_sub_id=None) + set_auto_renew(True, tg_sub_charge_id=charge_id) + payment + deliver_keys. Subsequent charge -> get_active_auto_renew_for(user,plan), extend to subscription_expiration_date (Unix->UTC) + update_client expiryTime + payment + DM. Idempotent via UNIQUE charge_id. Routed from on_successful_payment when payment.is_recurring is True or ctx.kind=='sub'.
