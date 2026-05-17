# tests/test_handlers_user_promo.py

Тесты для app.handlers.user.promo — двушаговый флоу активации free-days промокода с выбором inbound.

Поток: msg_code (введите код) → choosing_inbound (выберите сервер) → cb_pick_inbound_for_promo (активация) → deliver_keys.

Покрытие:
- cb_open: вход в PromoActivate.waiting_code.
- msg_code: no-user, invalid code (stays in waiting_code), discount-тип (percent/flat_stars) → state.clear с подсказкой использовать buy-flow, free_days happy path → переход в choosing_inbound с inbound_options в FSM, xui failure → clear + apology, no inbounds → clear + apology, double activation (already redeemed).
- cb_pick_inbound_for_promo: activates (try_redeem + add_client + deliver_keys), no-user alert, missing promo_id in FSM (session expired), inbound_id вне options (rejected), promo invalidated race (deactivated между шагами), xui failure (promo NOT redeemed).
- cb_back_inbound_for_promo: возврат в waiting_code, очистка promo_id/inbound_options.

Использует мок get_xui_client, list_user_inbounds, deliver_keys.

См. также: app/handlers/user/promo.py.
