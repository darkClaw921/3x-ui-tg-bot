# app/handlers/__init__.py

register_routers(dp): подключает outer middleware UserContextMiddleware на dp.update + роутеры в порядке start → admin_router → user_router. start первым, чтобы /start всегда срабатывал; admin_router второй (внутри AdminOnlyMiddleware блокирует не-админов); user_router последний (catch-all для юзерских callback и messages).
