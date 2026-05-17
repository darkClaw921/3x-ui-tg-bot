# app/states/user.py

FSM-группы пользовательского флоу.

BuyFlow — мастер покупки подписки через Telegram Stars:
- choosing_plan: пользователь выбирает тариф из inline-списка (callback BuyCB action=plan, plan_id).
- choosing_inbound: пользователь выбирает inbound/сервер из allow-list тарифа (callback InboundCB action=pick). Шаг автоматически пропускается хендлером, если в allow-list ровно один inbound — тогда сразу confirming.
- entering_promo: текстовый ввод промокода (применяется к выбранному тарифу).
- confirming: финальное подтверждение, выпускается Stars-инвойс. После send_invoice состояние очищается; pre_checkout / successful_payment приходят как stateless обновления Telegram с payload, содержащим plan_id/promo_id/inbound_id.

PromoActivate — мастер активации отдельного промокода (обычно free_days):
- waiting_code: текстовый ввод кода.
- choosing_inbound: выбор inbound для free-days подписки. Пропускается при единственном inbound; иначе после выбора создаётся подписка и состояние очищается.

Промежуточный шаг choosing_inbound добавлен в Phase 3 (выбор сервера перед оплатой / выдачей free-days).
