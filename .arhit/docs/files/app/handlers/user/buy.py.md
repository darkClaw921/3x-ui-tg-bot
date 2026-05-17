# app/handlers/user/buy.py

Хендлеры пользовательского buy-флоу: выбор тарифа → выбор inbound (skip при 1 inbound) → confirm → Stars invoice → pre_checkout → successful_payment.

Маршрутизация по FSM (BuyFlow):
- choosing_plan → choosing_inbound (если у тарифа >1 inbound) или сразу в confirming (1 inbound)
- choosing_inbound → confirming
- confirming → (entering_promo, обратно в confirming) → инвойс отправлен, state.clear()

Callbacks (FSM-driven):
- cb_open (BuyCB action='open'): показывает список тарифов, переходит в choosing_plan.
- cb_pick_plan (BuyCB action='plan'): загружает inbound_ids через plans_repo.get_inbounds; если 1 → resolved через list_user_inbounds для remark, FSM(inbound_id=…), confirming; если N>1 → list_user_inbounds + фильтр по allow-list плана, FSM(inbound_options=[…]), choosing_inbound, рендер inbound_select_kb. На XuiError — answer alert.
- cb_pick_inbound (InboundCB action='pick' в choosing_inbound): валидирует inbound_id ∈ get_inbounds(plan_id), сохраняет в FSM, рендерит _format_confirm + confirm_kb(plan_id, promo_id, inbound_id).
- cb_pick_inbound_back (InboundCB action='back' в choosing_inbound): возврат в choosing_plan + plans_kb.
- cb_apply_promo (BuyCB action='apply_promo'): сохраняет plan_id+inbound_id, переходит в entering_promo.
- msg_promo_code (message в entering_promo): валидирует код через promos_service.validate, при успехе → confirming + рендер confirm с remark и has_active_sub.
- cb_confirm (BuyCB action='confirm'): резолвит inbound_id из callback_data (fallback на FSM), валидирует ∈ get_inbounds; при mismatch — возвращает в choosing_inbound с обновлённым списком; иначе billing.send_invoice(..., inbound_id=…) и state.clear().

Payment-callbacks (stateless, IDs из invoice payload):
- on_pre_checkout: parse_invoice_payload → (plan_id, promo_id, inbound_id); валидирует plan активен, promo usable, inbound_id ∈ get_inbounds(plan_id); answer_pre_checkout_query(ok=…).
- on_successful_payment: idempotency check по telegram_payment_charge_id; parse payload; логирует WARNING при legacy-payload без 'i' (fallback на settings.XUI_INBOUND_ID); subs_service.create_or_extend(..., inbound_id=…); payments_repo.create; promos_service.apply (best-effort); deliver_keys.

Хелперы:
- _format_confirm(plan, promo, inbound_remark, has_active_sub): HTML текст confirm-карточки с remark подключения; если has_active_sub=True — добавляет ⚠️-предупреждение что подписка продлится на текущем подключении.
- _has_active_sub(conn, user_id): обертка над subs_repo.get_active_for_user.
- _remark_for(options, inbound_id): резолвит remark из FSM-options (list[InboundOption] или list[dict]).
- _options_to_jsonable / _jsonable_to_options: сериализация InboundOption в/из FSM JSON-storage.
- _fetch_plan / _fetch_promo: тонкие обертки.
- _plan_is_buyable / _promo_is_usable: предикаты доступности.

Зависимости:
- app.db.repos.plans (get_inbounds), app.db.repos.subscriptions (get_active_for_user), app.db.repos.promos, app.db.repos.payments.
- app.services.billing (send_invoice с inbound_id, parse_invoice_payload возвращает 3-tuple), app.services.subscriptions (create_or_extend kwarg inbound_id), app.services.inbounds (list_user_inbounds, InboundOption), app.services.promos.
- app.keyboards.user: BuyCB, InboundCB, confirm_kb, inbound_select_kb, plans_kb.
- app.states.user: BuyFlow.choosing_inbound.
- app.xui (get_xui_client, XuiError).
- app.config.settings (XUI_INBOUND_ID для логирования legacy-fallback).
