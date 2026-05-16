# app/db/repos/plans.py

Репозиторий тарифов (таблица plans). Soft-delete через deactivate (is_active=0) — payments и subscriptions ссылаются на plans, hard-delete сломал бы историю.

Dataclass Plan(id, title, days, price_stars, traffic_gb, is_active, created_at) — frozen, slots. Поле traffic_gb: int — лимит трафика тарифа в ГБ (0 = без лимита, соответствует xui totalGB). Plan.from_row(row) строит из aiosqlite.Row.

Константа _UPDATABLE_COLUMNS = {'title', 'days', 'price_stars', 'traffic_gb', 'is_active'} — whitelist колонок, разрешённых в update (защита от SQL-injection через имена колонок).

Функции:
- create(conn, title, days, price_stars, traffic_gb=0) -> Plan — вставляет активный тариф; traffic_gb опционален (по умолчанию 0 = без лимита).
- get(conn, plan_id) -> Plan | None.
- list_active(conn) -> list[Plan] — is_active=1, сортировка price_stars ASC, id ASC.
- list_all(conn) -> list[Plan] — все тарифы, сортировка по id.
- update(conn, plan_id, **fields) -> Plan — патч одной или нескольких колонок из _UPDATABLE_COLUMNS (включая traffic_gb). ValueError на неизвестные колонки; LookupError если plan_id не существует. Booleans коэрсятся в 0/1 для is_active.
- deactivate(conn, plan_id) — мягкое отключение (is_active=0).

Схема plans содержит CHECK (traffic_gb >= 0); колонка добавлена идемпотентной миграцией ALTER TABLE plans ADD COLUMN traffic_gb INTEGER NOT NULL DEFAULT 0 в app/db/engine.py::_apply_migrations.
