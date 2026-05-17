# app/handlers/user/buy.py

Buy-flow handlers: plan selection → optional promo → Stars invoice → pre_checkout → successful_payment. Now supports both 'new subscription' and 'extend existing subscription #N' flows via sub_id threaded through BuyCB/FSM/invoice payload.

UI callbacks (FSM-driven):
- cb_open (BuyCB.open): show action screen (buy_action_kb with 'Продлить #N' + 'Новая подписка') if user has 1+ active subs, otherwise show plan list directly.
- cb_pick_action_extend (BuyCB.extend, NO state filter): pin sub_id+inbound_id from existing sub into FSM, jump to choosing_plan. Validates ownership defensively (rejects foreign or non-active sub). Works as standalone entry point from Phase 4 'Моя подписка' card.
- cb_pick_action_new (BuyCB.new, NO state filter): clear FSM (sub_id=0), jump to choosing_plan.
- cb_pick_plan (BuyCB.plan): extend branch (sub_id>0 in FSM) always skips inbound selection and goes straight to confirming with extend-aware card; new branch keeps original single/multi-inbound routing.
- cb_pick_inbound (BuyFlow.choosing_inbound + InboundCB.pick): only reachable in new-sub branch; persists chosen inbound and renders confirm card.
- cb_pick_inbound_back / cb_apply_promo / msg_promo_code: thread sub_id through FSM.
- cb_confirm (BuyCB.confirm): extend branch re-verifies ownership, skips plan-inbound allow-list (existing sub may live on a detached inbound), and calls billing.send_invoice(sub_id=N). New branch keeps allow-list check and sends sub_id=0.

Payment callbacks (stateless, invoice payload carries sub_id):
- on_pre_checkout: parses 4-tuple; for sub_id>0 loads user via users_repo.get_by_tg_id, verifies sub.user_id == buyer.id and status='active', skips allow-list. For sub_id=0 keeps original allow-list check.
- on_successful_payment: parses 4-tuple, logs 'extend sub N' or 'create new sub', passes extend_sub_id=sub_id (or None) into subs_service.create_or_extend. Idempotency via payments_repo unique constraint on telegram_charge_id.

Helpers:
- _format_confirm(plan, promo, inbound_remark, extending_sub: Subscription | None): renders '🔄 Продление подписки #N · remark · Действует до DATE' when extending_sub is set, else '🆕 Новая подписка на remark'. Replaces old has_active_sub boolean.
- _shift_expiry(current_expires_at, plus_days): returns 'YYYY-MM-DD' for the new expiry shown on the extend confirm card.
- _send_plan_list: shared 'choosing_plan + plans_kb' helper for action-screen exit branches.
- _has_active_sub: removed (replaced by direct subs_repo.list_active_for_user check in cb_open).

Idempotency: payments.telegram_charge_id UNIQUE — duplicate updates short-circuit before xui calls.
