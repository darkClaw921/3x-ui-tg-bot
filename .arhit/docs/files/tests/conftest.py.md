# tests/conftest.py

Общие pytest-фикстуры для tg-vpn-bot tests.

Перед любым импортом app.* устанавливает env-переменные (BOT_TOKEN, ADMIN_IDS, XUI_*, DB_PATH=':memory:'), т.к. Settings — singleton, инициализируется при импорте.

Фикстуры:
- monkey_settings: callable для patch'а атрибутов app.config.settings через monkeypatch.
- tmp_db_path: tmp_path / 'test.db' для file-backed sqlite.
- db_conn: in-memory aiosqlite.Connection с применённой schema.sql + _apply_migrations.
- file_db: file-backed sqlite по tmp_db_path + monkeypatch settings.DB_PATH; для тестов, использующих get_conn().
- make_user / make_plan / make_promo / make_subscription: factory'и для создания строк в БД через репо.
  - make_plan теперь auto-attaches default inbound (inbound_ids=[settings.XUI_INBOUND_ID]) — соответствует backfill из миграции. Параметр inbound_ids=[]/[1,2] для кастомизации.
- mock_bot: AsyncMock(aiogram.Bot) с stub'ами send_message/send_photo/send_invoice/answer_pre_checkout_query.
- mock_xui_client: AsyncMock с XuiClient surface (request_json, request, login, close).

_build_schema: применяет schema.sql + _apply_migrations к свежему соединению (используется в db_conn и file_db).
