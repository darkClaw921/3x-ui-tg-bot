# tests/test_db_repos_plans_inbounds.py

Тесты для функций plans_repo.set_inbounds / plans_repo.get_inbounds и таблицы plan_inbounds (many-to-many между plans и 3x-ui inbound id).

Покрывает:
- set_inbounds([]) → ValueError (тариф должен иметь хотя бы один inbound).
- set_inbounds + get_inbounds: возвращает id отсортированные по возрастанию.
- Повторный set_inbounds полностью заменяет предыдущий набор (атомарно).
- Дубликаты id в input set_inbounds дедуплицируются.
- get_inbounds для несуществующего plan_id возвращает [].
- ON DELETE CASCADE: hard-delete плана удаляет все его строки в plan_inbounds.

Фикстуры: db_conn (in-memory aiosqlite с применёнными миграциями), make_plan (создаёт plan).

См. также: app/db/repos/plans.py (тестируемые функции), app/db/schema.sql (DDL plan_inbounds).
