# tests/test_handlers_admin_routing.py

Routing-coverage тест для admin_router. Гарантирует что КАЖДАЯ кнопка КАЖДОЙ admin-клавиатуры (app.keyboards.admin) имеет зарегистрированный handler. Регрессия после бага «AdminCB(area='plans'/'promos', action='open') не имел handler — кнопки молча игнорировались».

Использует HandlerObject.check() для синтетического прогона CallbackQuery через router без вызова handler'ов. Покрытые клавиатуры (параметризованно): admin_main_menu, back_to_main_kb, cancel_kb, plans_list_kb (empty + одна запись), plan_card_kb (active/inactive), plan_edit_fields_kb, plan_days/price/gb_presets_kb (под соответствующими PlanCreate.waiting_* states), plan_inbounds_select_kb (none_selected + partial_selected), promos_list_kb, promo_type_kb (под PromoCreate.waiting_type), promo_value_presets_kb для всех трёх типов (percent/flat_stars/free_days под waiting_value), promo_max_uses/expires_presets_kb, promo_card_kb, user_card_kb (без подписки/с админом), stats_kb (7d/30d/all).

Pinned regressions: test_admin_main_menu_specifically_routes_plans_and_promos (явный guard под старый баг), test_plan_inbound_multiselect_buttons_are_routed (Phase 4: toggle_inbound, inbounds_done, edit с field=inbounds).

Helpers _walk (рекурсивный обход router.sub_routers), _all_buttons (только callback-кнопки), _has_matching_handler (state-aware), _sample_plan, _sample_promo, _sample_inbound_options.
