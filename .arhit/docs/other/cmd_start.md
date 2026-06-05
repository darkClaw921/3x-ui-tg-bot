# cmd_start

app/handlers/start.py — обработчик /start. Парсит deep-link аргумент (command: CommandObject) через _parse_deep_link ДО приветствия: ref_<tg_id> и gift_<code> (реальная логика рефералов/подарков — Ф3, сейчас классификация+лог как точка расширения). Без аргумента работает как раньше. Админы → admin_main_menu, остальные → user_main_menu (приоритет 'Моя подписка'/'Купить' по наличию активной подписки).
