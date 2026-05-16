# cb_promo_preset

Общий callback-хендлер пресет-кнопок мастера создания промокода в app/handlers/admin/promos.py. Фильтр: PromoCB.filter(F.action == 'preset'). На основе callback_data.field (value/max_uses/expires) и таблицы _PRESET_FLOW записывает callback_data.id в FSM data под нужным ключом, затем переводит state и отправляет следующую пресет-клавиатуру. Для терминального шага expires вызывает _expires_days_to_iso (0 → None, иначе now+N days в формате _parse_expires_at) и _finalize_promo_create. Принимает user: User | None из UserContextMiddleware для проброса created_by.
