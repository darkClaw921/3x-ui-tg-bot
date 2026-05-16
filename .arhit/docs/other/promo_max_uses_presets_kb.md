# promo_max_uses_presets_kb

Клавиатура пресетов для шага max_uses мастера создания промокода в app/keyboards/admin.py. Кнопки: 0 (∞)/1/5/10/50/100, '✏ Ввести вручную' (PromoCB(action='manual', field='max_uses')), '✖ Отмена'. Пресеты — PromoCB(action='preset', field='max_uses', id=<value>). Значение 0 означает 'без лимита' (соответствует семантике колонки max_uses в БД). Layout: adjust(3, 3, 1, 1).
