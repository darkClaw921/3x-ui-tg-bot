# app/config.py

Конфигурация приложения через pydantic-settings. Класс Settings(BaseSettings) объявляет BOT_TOKEN, ADMIN_IDS (Annotated[list[int], NoDecode] для отключения JSON-декодирования), DB_PATH (default './data/bot.db'), XUI_BASE_URL/USERNAME/PASSWORD/INBOUND_ID/SERVER_HOST/SUB_BASE_URL, LOG_LEVEL (default 'INFO'). Читает из .env через SettingsConfigDict(env_file='.env'). field_validator '_parse_admin_ids' (mode='before') парсит CSV-строку '1,2,3' → [1,2,3], принимает пустую строку, JSON-массив, готовый list. Экспортирует синглтон settings = Settings().
