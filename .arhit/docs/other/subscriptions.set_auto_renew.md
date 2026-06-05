# subscriptions.set_auto_renew

Repo method toggling subscriptions.auto_renew (and optionally tg_sub_charge_id). When tg_sub_charge_id is None only auto_renew is written so toggling off never clobbers a stored charge id. Used by native Star subscriptions (first recurring payment sets True + charge id; cancel sets False) and the wallet fallback (True, no charge id).
