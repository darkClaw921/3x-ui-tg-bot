# app/db/repos/plans.py

Репозиторий таблицы plans (тарифы) + связанной таблицы plan_inbounds.

Структуры данных:
- Plan dataclass(slots, frozen): id, title, days, price_stars, traffic_gb, is_active (bool), created_at. Plan.from_row(row) — конструктор из aiosqlite.Row.
- _UPDATABLE_COLUMNS = frozenset({title, days, price_stars, traffic_gb, is_active}) — whitelist колонок для update().

Функции (все async, принимают aiosqlite.Connection):
- create(conn, title, days, price_stars, traffic_gb=0) -> Plan — INSERT нового активного тарифа, commit, возвращает Plan.
- get(conn, plan_id) -> Plan | None — SELECT по PK.
- list_active(conn) -> list[Plan] — SELECT WHERE is_active=1 ORDER BY price_stars ASC, id ASC.
- list_all(conn) -> list[Plan] — SELECT ORDER BY id ASC.
- update(conn, plan_id, **fields) -> Plan — patch выбранных колонок (только из _UPDATABLE_COLUMNS). is_active приводится к 0/1. Raises ValueError на unknown columns, LookupError если plan не найден.
- deactivate(conn, plan_id) -> None — soft-delete (is_active=0); строка сохраняется для FK из payments/subscriptions.
- get_inbounds(conn, plan_id) -> list[int] — SELECT inbound_id FROM plan_inbounds WHERE plan_id=? ORDER BY inbound_id. Возвращает [] для несуществующих или пустых планов.
- set_inbounds(conn, plan_id, inbound_ids: Iterable[int]) -> None — атомарная замена набора inbounds для тарифа. Wraps DELETE FROM plan_inbounds WHERE plan_id=? + executemany INSERT в одну транзакцию (BEGIN/COMMIT, ROLLBACK на исключении). Дедуп входа через set(). Пустой итерируемый -> raise ValueError('plan must have at least one inbound') (тариф без inbound невозможно купить).

Используется хендлерами app/handlers/admin/plans.py (CRUD тарифов и multi-select inbound'ов), app/handlers/user/buy.py (получение списка inbound'ов тарифа при покупке), app/services/subscriptions.py (валидация inbound принадлежит плану).
