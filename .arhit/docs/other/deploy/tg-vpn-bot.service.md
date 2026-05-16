# deploy/tg-vpn-bot.service

Systemd unit для деплоя бота на Ubuntu/Debian сервер.

[Unit]
- Description: человекочитаемое имя сервиса
- After=network.target: запуск после сети
- Wants=network-online.target: дождаться готовности сети (для long-polling Telegram)

[Service]
- Type=simple: основной процесс — это ExecStart
- WorkingDirectory=/opt/3x-ui-tg-bot: рабочая директория (где лежит проект)
- EnvironmentFile=/opt/3x-ui-tg-bot/.env: загрузка переменных окружения из .env (BOT_TOKEN, XUI_*, ADMIN_IDS и т.д.)
- ExecStart=/opt/3x-ui-tg-bot/.venv/bin/python -m app.main: запуск бота из venv
- Restart=on-failure: автоперезапуск при ошибке
- RestartSec=5: пауза 5с между рестартами
- User=tgbot, Group=tgbot: непривилегированный системный пользователь
- StandardOutput/Error=journal: логи в systemd-journal (читаем через journalctl -u tg-vpn-bot)
- SyslogIdentifier=tg-vpn-bot: идентификатор в syslog

[Install]
- WantedBy=multi-user.target: автозапуск на обычном multi-user runlevel

Использование:
  sudo cp deploy/tg-vpn-bot.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now tg-vpn-bot
  journalctl -u tg-vpn-bot -f
