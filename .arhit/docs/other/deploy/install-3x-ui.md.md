# deploy/install-3x-ui.md

Документация на русском к скрипту deploy/install-3x-ui.sh.

Разделы:
- Что делает скрипт — пошаговое описание (10 шагов: префлайт, ufw, установка 3x-ui, x-ui setting, REST login, x25519 keys, create inbound, write .env, install bot, final report).
- Аргументы — таблица всех CLI-флагов с обязательностью и значениями по умолчанию.
- Примеры запуска — минимальный, полный (панель+бот), запуск через curl bash <(...).
- Файлы и лог — расположение лог-файла, cookie, .env, БД 3x-ui и бота.
- Идемпотентность — поведение при повторном запуске (skip 3x-ui install, prompt .env overwrite, git pull вместо clone, каждый запуск создаёт новый inbound).
- Troubleshooting — зависший installer, неактивный сервис x-ui, ошибки x25519, занятые порты, упавший tg-vpn-bot.service, полное удаление.
- Обновление — x-ui update; cd /opt/3x-ui-tg-bot && git pull && pip install -e . && systemctl restart tg-vpn-bot.
- Безопасность — set +o history, временный cookie-файл, chmod 600 на .env, видимость секретов в ps.

Связанные файлы:
- deploy/install-3x-ui.sh — сам скрипт
- README.md — раздел 'Быстрая установка одной командой' ссылается на эту документацию
