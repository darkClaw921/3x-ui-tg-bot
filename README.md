# 3x-ui-tg-bot

Telegram-бот для управления панелью 3x-ui:

- продажа VPN-подписок за Telegram Stars,
- выдача `vless://` ссылок, QR-кодов и Subscription URL,
- активация промокодов (`percent`, `flat_stars`, `free_days`),
- админ-меню: CRUD тарифов и промокодов, статистика, карточки пользователей.

Бот интегрируется с уже развёрнутой панелью 3x-ui через её REST API. Локальное
состояние (пользователи, тарифы, промокоды, подписки, платежи) хранится в SQLite.

## Стек

- Python 3.12, [aiogram 3.x](https://docs.aiogram.dev/) — long polling.
- `aiosqlite` — БД.
- `httpx` — REST к 3x-ui.
- `qrcode[pil]` — QR.
- `APScheduler` — фоновые задачи (expire-check, traffic-snapshots).
- `pydantic-settings` — конфиг из `.env`.
- `loguru` — логи (через stdlib `logging` интерсептор).

## Требования

- **Python 3.12+** (см. `requires-python` в [pyproject.toml](./pyproject.toml)).
- **systemd** (для серверного деплоя) — Ubuntu 22.04/24.04, Debian 12+ и т.п.
- Развёрнутая **панель 3x-ui** с доступом к REST API (`/panel/api/inbounds/...`)
  и созданным inbound'ом, в котором бот будет управлять клиентами.
- Telegram-бот, созданный через [@BotFather](https://t.me/BotFather),
  с включёнными Stars-платежами.

## Быстрая установка одной командой

Если у вас чистый Ubuntu/Debian сервер и нужно одновременно поставить
панель 3x-ui (с VLESS+Reality inbound) и Telegram-бота — используйте
скрипт [`deploy/install-3x-ui.sh`](./deploy/install-3x-ui.sh).

```bash
sudo bash <(curl -sSL https://raw.githubusercontent.com/<you>/3x-ui-tg-bot/main/deploy/install-3x-ui.sh) \
    --bot-token=1234567:ABCDEF \
    --admin-id=123456789 \
    --domain=vpn.example.com \
    --install-bot \
    --bot-repo=https://github.com/<you>/3x-ui-tg-bot.git
```

Скрипт самостоятельно:

- поставит 3x-ui из официального репозитория (отвечая на интерактивные
  вопросы установщика),
- задаст логин/пароль/порт/`webBasePath`,
- сгенерирует x25519-ключи Reality и создаст inbound,
- при `--ssl-mode=nginx` (включается автоматически если `--domain` — это
  FQDN): поставит nginx + certbot, выпустит Let's Encrypt сертификат,
  поднимет reverse-proxy `https://<domain>/<panel-path>/` →
  `127.0.0.1:<panel-port>`, забиндит панель только на 127.0.0.1
  и пропишет deploy-hook для авто-перезагрузки nginx при renew,
- если VLESS-порт совпал с nginx-портом (по умолчанию 443) —
  автоматически унесёт nginx на 8443 (управляется `--nginx-port`),
- запишет готовый `.env` для бота с корректными `XUI_BASE_URL`,
  `XUI_SUB_BASE_URL`, `XUI_VERIFY_SSL`,
- по флагу `--install-bot` склонирует репозиторий, создаст venv и поднимет
  бота как systemd-сервис.

Полезные дополнительные флаги:

- `--ssl-mode=auto|nginx|skip` — `auto` (по умолчанию): FQDN →
  `nginx`+LE, IP → `skip`. `skip` оставляет панель HTTP-only на публичном
  порту (`XUI_VERIFY_SSL=false`).
- `--le-email=<addr>` — email для Let's Encrypt. Если не задан, сертификат
  выпускается с `--register-unsafely-without-email`.
- `--nginx-port=<int>` — порт HTTPS у nginx (по умолчанию 443; авто 8443
  если VLESS на 443).

Подробное описание всех аргументов, troubleshooting и обновление —
в [`deploy/install-3x-ui.md`](./deploy/install-3x-ui.md).

## Локальный запуск

```bash
git clone <repo-url> 3x-ui-tg-bot
cd 3x-ui-tg-bot

python3.12 -m venv .venv
source .venv/bin/activate     # macOS / Linux
pip install -e .

cp .env.example .env
# заполните переменные в .env (минимум BOT_TOKEN, XUI_*)

python -m app.main
```

После запуска отправьте боту `/start` — он должен ответить приветствием.

## Конфигурация

Все переменные читаются из `.env` (`pydantic-settings`). Шаблон — `.env.example`.

### Обязательные

| Переменная          | Назначение                                                              |
|---------------------|-------------------------------------------------------------------------|
| `BOT_TOKEN`         | Токен бота от [@BotFather](https://t.me/BotFather).                     |
| `ADMIN_IDS`         | CSV Telegram-ID администраторов: `123,456`. Доступ к админ-меню.        |
| `XUI_BASE_URL`      | База URL панели 3x-ui, например `https://panel.example.com:2053`.       |
| `XUI_USERNAME`      | Логин панели (используется для `/login`).                               |
| `XUI_PASSWORD`      | Пароль панели.                                                          |
| `XUI_INBOUND_ID`    | ID inbound'а, в котором бот создаёт/обновляет клиентов.                 |
| `XUI_SERVER_HOST`   | Публичный хост в `vless://`-ссылках (то, что видит конечный клиент).    |
| `XUI_SUB_BASE_URL`  | База URL Subscription-страниц 3x-ui, например `https://.../sub`.        |

### Необязательные

| Переменная        | По умолчанию      | Назначение                                              |
|-------------------|-------------------|---------------------------------------------------------|
| `DB_PATH`         | `./data/bot.db`   | Путь к файлу SQLite.                                    |
| `XUI_VERIFY_SSL`  | `true`            | Проверять TLS-сертификат панели. `false` — для self-signed. |
| `LOG_LEVEL`       | `INFO`            | Уровень логирования (`DEBUG`/`INFO`/`WARNING`/`ERROR`). |

## Деплой (systemd)

Файл сервиса лежит в [`deploy/tg-vpn-bot.service`](./deploy/tg-vpn-bot.service).

### Шаги

```bash
# 1. Создать системного пользователя для бота (домашняя директория — место проекта).
sudo useradd -r -m -d /opt/3x-ui-tg-bot -s /bin/bash tgbot

# 2. Склонировать репозиторий в /opt/3x-ui-tg-bot (от имени tgbot).
sudo -u tgbot git clone <repo-url> /opt/3x-ui-tg-bot
cd /opt/3x-ui-tg-bot

# 3. Создать виртуальное окружение и поставить зависимости.
sudo -u tgbot python3.12 -m venv /opt/3x-ui-tg-bot/.venv
sudo -u tgbot /opt/3x-ui-tg-bot/.venv/bin/pip install -e .

# 4. Подготовить .env.
sudo -u tgbot cp /opt/3x-ui-tg-bot/.env.example /opt/3x-ui-tg-bot/.env
sudo -u tgbot ${EDITOR:-nano} /opt/3x-ui-tg-bot/.env
# Заполнить минимум BOT_TOKEN, ADMIN_IDS, XUI_*.
sudo chmod 600 /opt/3x-ui-tg-bot/.env
sudo chown tgbot:tgbot /opt/3x-ui-tg-bot/.env

# 5. Установить systemd unit.
sudo cp /opt/3x-ui-tg-bot/deploy/tg-vpn-bot.service /etc/systemd/system/
sudo systemctl daemon-reload

# 6. Запустить и включить автозагрузку.
sudo systemctl enable --now tg-vpn-bot

# 7. Проверить статус и логи.
sudo systemctl status tg-vpn-bot
sudo journalctl -u tg-vpn-bot -f
```

### Обновление

```bash
cd /opt/3x-ui-tg-bot
sudo -u tgbot git pull
sudo -u tgbot /opt/3x-ui-tg-bot/.venv/bin/pip install -e .
sudo systemctl restart tg-vpn-bot
```

### Бэкап

База SQLite живёт по пути из `DB_PATH` (по умолчанию `./data/bot.db`, при деплое
— `/opt/3x-ui-tg-bot/data/bot.db`). Делайте регулярный бэкап:

```bash
# Безопасный snapshot через SQLite Online Backup API
sudo -u tgbot sqlite3 /opt/3x-ui-tg-bot/data/bot.db \
    ".backup '/var/backups/tg-vpn-bot-$(date +%F).db'"

# Cron (ежедневно в 03:00, хранить 30 дней)
sudo crontab -e
# 0 3 * * * sqlite3 /opt/3x-ui-tg-bot/data/bot.db ".backup '/var/backups/tg-vpn-bot-$(date +\%F).db'" && find /var/backups -name 'tg-vpn-bot-*.db' -mtime +30 -delete
```

Также имеет смысл бэкапить `.env` (вне публичных репозиториев).

## Использование

### Пользователь

1. Отправить `/start` боту → откроется главное меню.
2. **«Купить подписку»** → выбрать тариф → ввести промокод (опционально) →
   подтвердить → оплатить через Telegram Stars.
3. После успешной оплаты бот пришлёт:
   - `vless://...` ссылку,
   - QR-код для импорта в XRay-клиент,
   - Subscription URL (можно подключить как «подписку» в клиенте).
4. **«Моя подписка»** → текущий статус (тариф, остаток дней, трафик),
   повторная выдача ключа, продление.
5. **«Активировать промокод»** → ввод кода (для `free_days` — даёт бесплатные
   дни подписки; `percent`/`flat_stars` применяются на этапе покупки тарифа).

### Администратор

Доступ — только для Telegram-ID из `ADMIN_IDS`.

1. `/start` → видно меню «Админ».
2. **Тарифы** → создать (название, цена в Stars, длительность в днях, лимит
   трафика), редактировать, активировать/деактивировать.
3. **Промокоды** → создать тип (`percent` / `flat_stars` / `free_days`),
   задать значение, лимит использований, срок действия.
4. **Пользователи** → найти юзера, увидеть подписку и потреблённый трафик.
5. **Статистика** → сводка по платежам и промокодам.

## Структура проекта

См. [architecture.md](./architecture.md) — там описан каждый файл и его назначение.

## E2E чек-лист

Перед промо-релизом или после крупных изменений прогоняется ручной end-to-end
сценарий на staging-инстансе 3x-ui и dev-аккаунте Telegram-бота. Шаги собраны
в [docs/e2e-checklist.md](./docs/e2e-checklist.md).
