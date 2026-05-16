# promo_value_presets_kb

Параметризованная клавиатура пресетов для шага value мастера создания промокода в app/keyboards/admin.py. Возвращает разные кнопки в зависимости от promo_type: percent (5/10/15/25/50%), flat_stars (25/50/100/250/500 ⭐), free_days (1/3/7/14/30 дней). Каждая кнопка-пресет шлёт PromoCB(action='preset', field='value', id=<value>). Также есть кнопка '✏ Ввести вручную' (PromoCB(action='manual', field='value')) и универсальная '✖ Отмена'. Layout: adjust(3, 2, 1, 1). Использует общий helper _promo_preset_kb.
