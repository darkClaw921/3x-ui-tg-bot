# tests/test_db_migration_plan_inbounds.py

Тесты бэкфилла plan_inbounds в _apply_migrations / init_db (app/db/engine.py).

Поведение:
- Старая БД с plans без plan_inbounds → каждый план получает запись (plan.id, settings.XUI_INBOUND_ID).
- Идемпотентность: повторный init_db не перезатирает уже существующие записи (admin set_inbounds([10,20]) сохраняется).
- Селективность: бэкфилл применяется только к планам без записей в plan_inbounds; планы с admin-настройкой не трогаются.
- Graceful degrade: если settings.XUI_INBOUND_ID = 0/отсутствует — бэкфилл пропущен с warning, init_db не падает.

Использует tmp_path для file-backed DB и monkey_settings фикстуру для патча settings.XUI_INBOUND_ID.

См. также: app/db/engine.py (_apply_migrations), app/db/schema.sql.
