# app/handlers/user/promo.py

Standalone free_days-промокод флоу с экраном выбора 'продлить vs новая подписка' и выбором inbound. Discount-промокоды (percent/flat_stars) сюда не попадают — для них юзер направляется в buy flow.

## FSM: PromoActivate
Три состояния: waiting_code → (опционально) choosing_action → choosing_inbound (для новой подписки) или прямой переход к activate (для extend).

## Handlers

- cb_open (PromoActCB.open): entry point. state.set_state(PromoActivate.waiting_code) + cancel_kb.

- msg_code (state=PromoActivate.waiting_code): 
  1. promos_service.validate(plan=None).
  2. Если type != 'free_days' → подсказка использовать buy flow + state.clear().
  3. На ошибке валидации остаётся в стейте.
  4. list_user_inbounds (XuiError/пусто → извинение + state.clear()).
  5. **subs_repo.list_active_for_user(user.id)**: если есть активные подписки → state.set_state(PromoActivate.choosing_action), сохраняет promo_id + inbound_options (jsonable), рендерит promo_action_kb(active, remarks). Иначе — стандартный путь: state.set_state(choosing_inbound) + inbound_select_kb.

- cb_pick_action_extend_promo (state=PromoActivate.choosing_action + PromoActCB.extend): юзер выбрал '🔄 Продлить #N'. Проверка sub_id>0, promo_id в FSM, subs_repo.get(sub_id) + ownership check (user_id) + status='active' (анти-подделка callback). Вызывает _activate_promo_for_sub(extend_sub_id=sub.id, inbound_id=sub.xui_inbound_id) — inbound наследуется от существующей подписки, allow-list не проверяется.

- cb_pick_action_new_promo (state=PromoActivate.choosing_action + PromoActCB.new): юзер выбрал '🆕 Новая подписка'. Переиспользует inbound_options из FSM (положенный msg_code); fallback list_user_inbounds. state.set_state(choosing_inbound), рендерит inbound_select_kb(0, options, promo_id=promo_id).

- cb_pick_inbound_for_promo (state=PromoActivate.choosing_inbound + InboundCB.pick): 
  1. Read promo_id (FSM/callback fallback) + inbound_id из callback.
  2. Re-validate промо (анти-race против msg_code).
  3. Verify inbound_id в FSM-snapshot.
  4. subs_service.activate_free_days(conn, xui, user, promo, inbound_id=inbound_id, extend_sub_id=None). На XuiError промо НЕ редимится.
  5. Best-effort promos_service.apply.
  6. deliver_keys + state.clear().

- cb_back_inbound_for_promo (state=PromoActivate.choosing_inbound + InboundCB.back): возврат в waiting_code + сброс promo_id/inbound_options.

## Helpers

- _options_to_jsonable / _jsonable_to_options: сериализация InboundOption для FSM storage (зеркало buy.py).
- _activate_promo_for_sub(callback, state, bot, user, promo_id, extend_sub_id, inbound_id): общий tail для extend-ветки action-экрана. Re-валидирует промо, вызывает subs_service.activate_free_days(extend_sub_id=...), best-effort apply, deliver_keys с заголовком 'применён к подписке #N' (extend) или 'активирован' (new), очищает FSM.

## Separation от buy.py
- InboundCB общая фабрика, handlers фильтруются по своему стейту (BuyFlow.choosing_inbound vs PromoActivate.choosing_inbound) — не конфликтуют.
- PromoActCB extend/new фильтруются по PromoActivate.choosing_action, что не конфликтует с BuyCB extend/new под BuyFlow.choosing_action.

## Race guards
- promos_service.validate в msg_code И в cb_pick_inbound_for_promo (и в _activate_promo_for_sub).
- promos_repo.try_redeem (внутри promos_service.apply) атомарно через BEGIN IMMEDIATE.

## Dependencies
- app.services.inbounds.list_user_inbounds (TTL-кэш panel call)
- app.services.subscriptions.activate_free_days (inbound_id + extend_sub_id kwargs)
- app.services.promos.validate / apply
- app.db.repos.subscriptions.list_active_for_user, subs_repo.get
- app.keyboards.user.{InboundCB, PromoActCB, inbound_select_kb, promo_action_kb, cancel_kb}
- app.states.user.PromoActivate (waiting_code, choosing_action, choosing_inbound)
- app.handlers.user._keys.deliver_keys
