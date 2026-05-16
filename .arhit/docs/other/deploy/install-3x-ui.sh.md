# deploy/install-3x-ui.sh

Идемпотентный bash-скрипт автоматической установки 3x-ui (VLESS+Reality) и опционально Telegram-бота на чистый Ubuntu/Debian сервер.

Запуск: sudo bash deploy/install-3x-ui.sh --bot-token=... --admin-id=... --domain=... [--install-bot --bot-repo=...]

CLI-аргументы:
- --bot-token=<str> — BOT_TOKEN Telegram (обязателен)
- --admin-id=<csv> — Telegram user ID админов через запятую (обязателен)
- --domain=<fqdn> — публичный FQDN сервера (обязателен)
- --panel-port=<int> — порт админ-панели (default: rand 20000-65535)
- --panel-user=<str> — логин панели (default: admin)
- --panel-pass=<str> — пароль панели (default: openssl rand -base64 18)
- --panel-path=<str> — webBasePath панели (default: /<12 hex>/)
- --vless-port=<int> — порт VLESS Reality inbound (default: 443)
- --reality-dest=<host:port> — маскировочный сайт (default: www.microsoft.com:443)
- --reality-sni=<str> — SNI (default: host из reality-dest)
- --sub-port=<int> — порт подписок (default: 2096)
- --sub-path=<str> — path подписок (default: /sub/)
- --install-bot — также поднять бота как systemd-сервис
- --bot-repo=<url> — git URL репозитория бота (нужен с --install-bot)
- --non-interactive — не задавать вопросов
- --help — справка

Ключевые функции:
- parse_args/usage — разбор CLI
- info/ok/warn/err/fatal — цветные логи в stderr + tee в /var/log/install-3x-ui.log
- cleanup (trap EXIT) — удаление временного cookie-файла + подсказка восстановления
- ask/ask_secret — интерактивный/неинтерактивный prompt
- rand_port/rand_hex/rand_base64/port_in_use — утилиты
- ensure_root/ensure_os — префлайт (root + Debian/Ubuntu)
- preflight — apt install curl wget tar jq openssl qrencode ca-certificates iproute2
- configure_ufw — открывает 22/panel/vless/sub порты если ufw active
- install_3x_ui — скачивает install.sh от MHSanaei/3x-ui, отвечает 'n' на customize-prompt
- wait_service_active — ожидание systemctl is-active с таймаутом
- configure_panel_settings — x-ui setting -username/-password/-port/-webBasePath + попытка -subPort/-subPath
- build_panel_urls/panel_curl/panel_login — REST API панели (curl -k -b/-c cookie + jq)
- configure_sub_via_api — fallback subPort/subPath через /panel/setting/update
- generate_reality_keys — x25519 ключи через /server/getNewX25519Cert или xray x25519
- create_inbound — POST /panel/api/inbounds/add с VLESS+Reality payload, парсит obj.id
- write_env — генерирует .env с BOT_TOKEN/ADMIN_IDS/XUI_*/LOG_LEVEL, chmod 600
- install_bot — python3.12 (deadsnakes если нужно), useradd tgbot, git clone, venv, pip install -e, systemd unit
- final_report — печатает URL панели, логин/пароль, ID inbound, Reality publicKey, путь к .env

Зависимости: bash 4+, curl, jq, openssl, systemd, apt-get, ss (iproute2).

Связанные файлы:
- deploy/tg-vpn-bot.service — копируется в /etc/systemd/system при --install-bot
- deploy/install-3x-ui.md — детальная документация со скрипту
- .env.example — шаблон, на основе которого формируется итоговый .env
