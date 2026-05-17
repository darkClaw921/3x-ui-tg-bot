# app/keyboards/user.py

Inline keyboards + CallbackData фабрики для user-facing флоу.

## CallbackData namespaces

- UserCB(prefix='u', area): area ∈ menu/help/my/cancel — top-level навигация.
- BuyCB(prefix='ub', action, plan_id=0, promo_id=0, inbound_id=0, sub_id=0): buy-flow. action ∈ open/extend/new/plan/apply_promo/confirm/cancel. Поля прокидываются через цепочку шагов. sub_id=0 → новая подписка; sub_id>0 → продлить именно эту (inbound наследуется от существующей, allow-list check пропускается). Packed: ub:<action>:<plan>:<promo>:<inbound>:<sub>.
- InboundCB(prefix='inb', action, plan_id=0, promo_id=0, inbound_id=0): action ∈ pick/back. Общая фабрика для buy-флоу (plan_id>0) и free_days promo-флоу (plan_id=0, promo_id>0); хендлер маршрутизирует по FSM-стейту.
- SubCB(prefix='us', action, sub_id=0): action ∈ keys/back. Для 'Моя подписка' карточек.
- PromoActCB(prefix='up', action, inbound_id=0, sub_id=0): action ∈ open/extend/new/cancel. Поле sub_id>0 несёт id подписки для extend через free_days промо.

## Функции

- user_main_menu(has_subscription): «Моя подписка» / «Купить» / «Активировать промокод» / «Помощь». Порядок первых двух меняется по флагу.
- back_to_menu_kb(): одна кнопка «◀ В меню».
- cancel_kb(): одна кнопка «✖ Отмена» (UserCB area=cancel).
- plans_kb(plans): один пункт на тариф (title · Nд · M⭐) + «В меню».
- inbound_select_kb(plan_id, options, promo_id=0): single-select inbounds, кнопка на InboundOption с текстом '<remark> (port <port>)', callback InboundCB(action='pick', plan_id, promo_id, inbound_id=option.id). Внизу «◀ Назад».
- confirm_kb(plan_id, promo_id=0, inbound_id=0, sub_id=0): «Оплатить» (BuyCB confirm + все поля) / «Применить промокод» (скрыта если promo_id≠0; пробрасывает inbound_id и sub_id) / «Отмена». sub_id>0 → invoice — продление конкретной подписки.
- **buy_action_kb(active_subs, inbound_remarks)** [NEW Phase 2]: action-экран buy-флоу при наличии active подписок. По строке на каждую sub: '🔄 Продлить #<sub_id> · <remark>' (BuyCB action='extend', sub_id=<id>), затем '🆕 Новая подписка' (BuyCB action='new'), затем '◀ Отмена' (UserCB area='cancel'). inbound_remarks — мэппинг {inbound_id: remark} из panel cache; fallback — '#<inbound_id>'.
- **promo_action_kb(active_subs, inbound_remarks)** [NEW Phase 3]: action-экран free_days промо-флоу. Зеркало buy_action_kb, но callback-фабрика PromoActCB вместо BuyCB.
- subscription_kb(sub_id): «Получить ключ ещё раз» / «◀ В меню».

## Constraints
- Все callback_data укладываются в 64-байтовый лимит Telegram (проверено тестами в test_keyboards_user.py).
- Multi-subscription support: BuyCB и PromoActCB несут sub_id для маршрутизации extend-vs-new решения в hot path.
