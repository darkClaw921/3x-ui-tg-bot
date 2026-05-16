# app/handlers/user/__init__.py

Агрегатор пользовательского user_router (aiogram Router). Подключает в порядке: menu -> my_subscription -> buy -> promo -> help. Без gate-middleware — доступен всем юзерам. menu идёт первым чтобы /menu и main-menu callbacks обрабатывались до более специфичных flow; my_subscription обрабатывает UserCB(area='my') и SubCB(action='keys') для повторной выдачи ключей; buy несёт самый тяжёлый набор FSM-хендлеров + pre_checkout/successful_payment; promo и help — отдельные одиночные колбеки.
