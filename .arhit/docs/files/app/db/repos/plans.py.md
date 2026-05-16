# app/db/repos/plans.py

Репозиторий таблицы plans (тарифы).

Dataclass Plan(slots, frozen): id, title, days, price_stars, is_active (bool), created_at.
Метод Plan.from_row(aiosqlite.Row).
Константа _UPDATABLE_COLUMNS = {'title','days','price_stars','is_active'}.

Async-функции:
- create(conn, title, days, price_stars) -> Plan — создаёт активный тариф (is_active=1).
- get(conn, plan_id) -> Plan | None.
- list_active(conn) -> list[Plan] — где is_active=1, сортировка ORDER BY price_stars ASC, id ASC.
- list_all(conn) -> list[Plan] — все, sorted by id.
- update(conn, plan_id, **fields) -> Plan — только колонки из whitelist; ValueError на unknown columns; LookupError если запись не найдена. Преобразует bool→0/1 для is_active.
- deactivate(conn, plan_id) — soft-delete (is_active=0). Запись остаётся для FK-целостности из payments/subscriptions.
