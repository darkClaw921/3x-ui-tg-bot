# app/states/user.py

FSM state groups для user-facing флоу.

## BuyFlow (5 состояний)
- choosing_action: показывается только при наличии active подписок (list_active_for_user). Юзер выбирает '🔄 Продлить #N' или '🆕 Новая подписка' через buy_action_kb. При отсутствии active — шаг пропускается, флоу стартует с choosing_plan.
- choosing_plan: выбор тарифа из plans_kb.
- choosing_inbound: выбор inbound из inbound_select_kb. Пропускается автоматически при единственном inbound в allow-list плана; **всегда** пропускается при extend (sub_id>0) — inbound наследуется.
- entering_promo: ввод промокода (для discount-промо в составе платной покупки).
- confirming: финальный экран с confirm_kb (Оплатить/Применить промокод/Отмена).

## PromoActivate (3 состояния)
- waiting_code: ввод free_days-промокода.
- choosing_action: показывается при наличии active подписок (зеркало BuyFlow.choosing_action). Юзер выбирает '🔄 Продлить #N' через promo_action_kb или '🆕 Новая подписка'. Extend-ветка минует choosing_inbound и сразу вызывает activate_free_days(extend_sub_id=N, inbound_id=sub.xui_inbound_id). New-ветка переходит в choosing_inbound.
- choosing_inbound: выбор inbound через inbound_select_kb для новой подписки.

## FSM storage keys (через FSMContext.update_data)
- plan_id, promo_id, inbound_id, inbound_options (jsonable list of InboundOption), inbound_remarks ({inbound_id: remark}), active_sub_ids (list of int), sub_id (0 = new, >0 = extend that subscription).

## Контракт sub_id (multi-subscription)
sub_id в FSM — расходный канал между choosing_action и confirming/payment. Пробрасывается в BuyCB при confirm, далее в billing.send_invoice(sub_id=...), далее в JSON payload как ключ 's', далее в subs_service.create_or_extend(extend_sub_id=sub_id or None). Pre_checkout/successful_payment приходят stateless — payload единственный носитель состояния через границу Telegram.
