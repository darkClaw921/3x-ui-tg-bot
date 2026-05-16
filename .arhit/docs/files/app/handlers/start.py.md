# app/handlers/start.py

/start. Использует user из data (из UserContextMiddleware). Если is_admin=True → admin_main_menu(). Иначе показывает user_main_menu с has_subscription из subs_repo.get_active_for_user.
