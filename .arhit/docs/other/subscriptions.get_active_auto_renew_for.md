# subscriptions.get_active_auto_renew_for

Repo query returning the user's active native Star-subscription for a given plan_id (status='active' AND auto_renew=1 AND tg_sub_charge_id IS NOT NULL), latest-expiring first. Used by on_successful_payment to locate the subscription a subsequent recurring charge extends.
