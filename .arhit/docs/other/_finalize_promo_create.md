# _finalize_promo_create

Общий helper в app/handlers/admin/promos.py: персистит промокод из FSM-data + переданного expires_at, чистит state и шлёт карточку. Используется из st_expires_at (ручной путь) и cb_promo_preset (пресет +N дней / бессрочно). Обрабатывает aiosqlite.IntegrityError (конфликт уникальности кода).
