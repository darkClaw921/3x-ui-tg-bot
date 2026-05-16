# app/middlewares/user_ctx.py

Outer dispatcher-middleware UserContextMiddleware. Извлекает from_user из любого типа апдейта (Update.message/callback_query/inline_query/pre_checkout_query/...), вызывает users_repo.get_or_create(conn, tg_id, username, first_name) и кладёт User в data['user']. При ошибках БД логирует и проставляет data['user']=None — апдейт не теряется. Helper _extract_tg_user(event) обходит все update-поля с from_user.
