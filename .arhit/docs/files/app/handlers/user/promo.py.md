# app/handlers/user/promo.py

Standalone promo activation flow with free-days inbound selection.

Implements a 3-step FSM (PromoActivate) for redeeming free-days promo codes
without payment. Discount-type promos (percent / flat_stars) are rejected
here because they require a plan; the user is routed to the buy flow.

Handlers:
- cb_open(callback, state): PromoActCB(action='open') entry point.
  Enters PromoActivate.waiting_code and prompts for the code with a cancel
  keyboard.
- msg_code(message, state, user): bound to PromoActivate.waiting_code.
  Steps:
  1. promos_service.validate the typed code.
  2. If invalid → re-prompt with the error.
  3. If promo.type != 'free_days' → clear state, instruct to use buy flow.
  4. Otherwise list_user_inbounds via 3x-ui. On XuiError or empty list,
     clear state and apologise. On success stash promo_id + jsonable
     inbound_options in FSM and enter PromoActivate.choosing_inbound,
     rendering inbound_select_kb(plan_id=0, options, promo_id=promo.id)
     with the prompt 'Выберите подключение для активации промокода:'.
- cb_pick_inbound_for_promo(callback, callback_data, state, bot, user):
  Bound to PromoActivate.choosing_inbound + InboundCB(action='pick').
  The state filter is what separates this handler from buy.cb_pick_inbound
  (which binds to BuyFlow.choosing_inbound). Steps:
  1. Read promo_id from FSM (fallback to callback_data.promo_id) and
     inbound_id from callback_data.
  2. Re-fetch and re-validate the promo (anti-race: capacity/expiry/
     already-redeemed may have changed since msg_code).
  3. Verify inbound_id is in the offered options snapshot (FSM).
  4. subs_service.activate_free_days(conn, xui, user, promo,
     inbound_id=inbound_id). On XuiError the promo is NOT redeemed —
     user can retry.
  5. Best-effort promos_service.apply.
  6. deliver_keys with the success header, clear FSM state.
- cb_back_inbound_for_promo(callback, state): bound to
  PromoActivate.choosing_inbound + InboundCB(action='back'). Returns to
  PromoActivate.waiting_code and clears promo_id/inbound_options.

Helpers:
- _options_to_jsonable / _jsonable_to_options: mirror the buy-flow
  helpers — aiogram's FSM storage round-trips JSON, so dataclasses must
  be flattened.

Idempotency / race guards:
- promos_service.validate runs in msg_code AND again in
  cb_pick_inbound_for_promo before activation.
- promos_repo.try_redeem (inside promos_service.apply) is atomic via
  BEGIN IMMEDIATE.

State separation from buy.py:
- InboundCB is shared, so handlers must filter on the correct FSM state.
  buy.py uses BuyFlow.choosing_inbound; promo.py uses
  PromoActivate.choosing_inbound. State filter is the first positional
  argument to @router.callback_query so both handlers coexist.

Dependencies:
- app.services.inbounds.list_user_inbounds (TTL-cached panel call)
- app.services.subscriptions.activate_free_days (inbound_id kwarg)
- app.services.promos.validate / apply
- app.keyboards.user.{InboundCB, PromoActCB, inbound_select_kb, cancel_kb}
- app.states.user.PromoActivate (waiting_code, choosing_inbound)
- app.handlers.user._keys.deliver_keys
