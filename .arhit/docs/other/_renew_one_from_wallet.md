# _renew_one_from_wallet

Helper for auto_renew_job (app/scheduler.py): renews one subscription from the wallet. Resolves plan+user, computes price, try_spend with deterministic ref autorenew:<sub>:<period(expires_at)> (replay-safe via idx_wallet_ref). Distinguishes insufficient-balance (DMs user) from replay (silent no-op via get_by_ref). On spend success: create_or_extend(extend_sub_id=sub.id) xui-first, refund (ref refund:autorenew:<txn>) on XuiError, synthetic payment for stats, renewed DM. Returns True on successful renewal.
