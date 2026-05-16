# promo_expires_presets_kb

Клавиатура пресетов для шага expires_at мастера создания промокода в app/keyboards/admin.py. Кнопки: 'бессрочно' (id=0), '+7д' (id=7), '+30д' (id=30), '+90д' (id=90), '+365д' (id=365), '✏ Ввести вручную' (PromoCB(action='manual', field='expires')), '✖ Отмена'. Пресеты — PromoCB(action='preset', field='expires', id=<days>). id=0 в хендлере преобразуется в expires_at=None, остальные — в ISO-8601 строку 'now + N days' в том же формате, что и _parse_expires_at. Layout: adjust(3, 2, 1, 1).
