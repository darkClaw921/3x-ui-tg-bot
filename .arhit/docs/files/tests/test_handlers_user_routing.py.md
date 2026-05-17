# tests/test_handlers_user_routing.py

Routing-coverage тест для user_router (зеркало test_handlers_admin_routing.py). Проверяет что КАЖДАЯ callback-кнопка КАЖДОЙ пользовательской клавиатуры (app.keyboards.user) имеет хотя бы один зарегистрированный handler. Использует HandlerObject.check() для прогона всей цепочки фильтров (CallbackData parsers + state filters + magic filters) против синтезированного CallbackQuery. Handlers НЕ вызываются — нет ни Telegram API, ни DB, ни 3x-ui. 

Параметризованный test_every_user_button_is_routed покрывает: user_main_menu(has_subscription=True/False), back_to_menu_kb, cancel_kb, plans_kb(empty/one), inbound_select_kb (под BuyFlow.choosing_inbound и под PromoActivate.choosing_inbound), confirm_kb (с/без promo), subscription_kb.

Pinned regressions: test_user_main_menu_entry_points_are_routed (4 entry-кнопки главного меню), test_inbound_select_routes_in_both_flows (pick/back под обоими state), test_confirm_kb_threads_inbound_id_through_routing (inbound_id в payload не ломает routing). 

State-bound клавиатуры тестируются под нужным state (raw_state параметром). Helpers _walk/_all_buttons/_has_matching_handler — намеренная копия из admin-routing-теста (две suites должны быть независимы).
