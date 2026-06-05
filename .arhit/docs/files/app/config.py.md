# app/config.py

Добавлен WALLET_TOPUP_PRESETS: list[int] (default [50,100,250,500]) — суммы Stars для кнопок пополнения на экране Кошелёк. Валидатор _parse_admin_ids переименован в _parse_csv_ints и навешен на оба поля ADMIN_IDS и WALLET_TOPUP_PRESETS (CSV '50,100' или JSON-массив -> list[int], пусто -> []).
