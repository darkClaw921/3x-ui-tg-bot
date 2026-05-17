# app/keyboards/user.py

Inline-клавиатуры пользовательского флоу и CallbackData-фабрики.

CallbackData-фабрики:
- UserCB(area) — area ∈ {menu, help, my, cancel}; навигация верхнего уровня.
- BuyCB(action, plan_id=0, promo_id=0, inbound_id=0) — мастер покупки. action ∈ {open, plan, apply_promo, confirm, cancel}. Поле inbound_id добавлено в Phase 3 и пробрасывается через все шаги после выбора inbound; 0 означает, что выбор был автоматически пропущен (один inbound в allow-list тарифа).
- InboundCB(action, plan_id=0, promo_id=0, inbound_id=0) — выбор inbound (Phase 3). action ∈ {pick, back}. Используется и в buy-флоу (plan_id>0), и в free-days promo-флоу (plan_id=0, promo_id>0); хендлер маршрутизирует по тому, какой из id ненулевой.
- SubCB(action, sub_id=0) — действия над карточкой подписки: keys / back.
- PromoActCB(action) — отдельный мастер активации промокода (open / cancel).

Ключевые клавиатуры:
- user_main_menu(has_subscription) — главное меню; порядок «Купить» / «Моя подписка» зависит от наличия активной подписки.
- back_to_menu_kb / cancel_kb — служебные одна-кнопка клавиатуры.
- plans_kb(plans) — список тарифов для покупки (одна строка = один тариф, кнопка карточки).
- inbound_select_kb(plan_id, options, promo_id=0) — single-select inbounds (Phase 3). Один InboundOption — одна кнопка '<remark> (port <port>)' с InboundCB(action='pick', plan_id, promo_id, inbound_id=option.id). Внизу '◀ Назад' (InboundCB action='back').
- confirm_kb(plan_id, promo_id=0, inbound_id=0) — финальное подтверждение покупки. 'Оплатить' пробрасывает все три id в BuyCB(action='confirm'); 'Применить промокод' доступен только при promo_id=0.
- subscription_kb(sub_id) — карточка активной подписки.
