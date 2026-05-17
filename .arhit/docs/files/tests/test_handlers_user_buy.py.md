# tests/test_handlers_user_buy.py

Тесты для app.handlers.user.buy — полный buy-flow с выбором inbound.

Покрытие хендлеров:
- cb_open: с/без планов.
- cb_pick_plan: skip-логика для 1 inbound (auto-confirm), multi-inbound селектор, no-inbounds misconfig (alert), xui unavailable, сохранение promo_id из FSM.
- cb_pick_inbound: валидный выбор, inbound не в плане (alert), back-callback.
- cb_apply_promo: переход в waiting_promo_code с сохранением inbound_id.
- msg_promo_code: valid/invalid/no-user/deactivated-plan.
- cb_confirm: send_invoice + payload c inbound_id, recovery при inbound не в плане (route обратно на selector), invalid plan, no chat_id.
- on_pre_checkout: ok, bad payload, deactivated plan, invalid promo, inbound не в плане, legacy payload (fallback), missing plan.
- on_successful_payment: happy path, legacy payload fallback, idempotency (duplicate charge), bad payload, no user, xui failure (records payment с subscription_id=None), promo redemption, plan deleted.
- _format_confirm: warning при наличии активной подписки (с/без).

Использует мок plans_repo.get_inbounds, мок list_user_inbounds (services.inbounds), AsyncMock get_xui_client.
Autouse фикстура _clear_inbounds_cache сбрасывает TTL-кэш между тестами.

См. также: app/handlers/user/buy.py.
