# app/handlers/admin/__init__.py

Агрегатор admin-router. _build_admin_router() создаёт Router(name='admin'), вешает AdminOnlyMiddleware на admin_router.message и admin_router.callback_query, включает sub-роутеры menu/plans/promos. Экспортирует admin_router как переменную модуля. Подключается в app.handlers.__init__ через dp.include_router.
