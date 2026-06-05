# Architecture

Документ описывает структуру проекта и назначение каждого файла. Обновляется
при добавлении/удалении файлов и функций. Не содержит статусов выполнения или
истории изменений.

## Дерево каталогов (текущее состояние)

```
3x-ui-tg-bot/
├── architecture.md
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── deploy/
│   ├── tg-vpn-bot.service
│   ├── install-3x-ui.sh
│   └── install-3x-ui.md
├── docs/
│   └── e2e-checklist.md
└── app/
    ├── __init__.py
    ├── main.py
    ├── config.py
    ├── logger.py
    ├── scheduler.py
    ├── db/
    │   ├── __init__.py
    │   ├── engine.py
    │   ├── schema.sql
    │   └── repos/
    │       ├── __init__.py
    │       ├── users.py
    │       ├── plans.py
    │       ├── promos.py
    │       ├── subscriptions.py
    │       └── payments.py
    ├── services/
    │   ├── __init__.py
    │   ├── promos.py
    │   ├── billing.py
    │   ├── subscriptions.py
    │   ├── stats.py
    │   └── broadcast.py
    ├── handlers/
    │   ├── __init__.py
    │   ├── start.py
    │   ├── admin/
    │   │   ├── __init__.py
    │   │   ├── menu.py
    │   │   ├── plans.py
    │   │   ├── promos.py
    │   │   ├── users.py
    │   │   ├── stats.py
    │   │   └── broadcast.py
    │   └── user/
    │       ├── __init__.py
    │       ├── _keys.py
    │       ├── menu.py
    │       ├── my_subscription.py
    │       ├── help.py
    │       ├── buy.py
    │       └── promo.py
    ├── keyboards/
    │   ├── __init__.py
    │   ├── admin.py
    │   └── user.py
    ├── middlewares/
    │   ├── __init__.py
    │   ├── admin_only.py
    │   └── user_ctx.py
    ├── states/
    │   ├── __init__.py
    │   ├── admin.py
    │   └── user.py
    └── xui/
        ├── __init__.py
        ├── client.py
        ├── inbounds.py
        ├── clients.py
        └── links.py
scripts/
├── __init__.py
└── xui_smoke.py
```

## Корневые файлы

### [pyproject.toml](./pyproject.toml)
Метаданные пакета (`name = "tg-vpn-bot"`, `requires-python = ">=3.12"`) и
runtime-зависимости: `aiogram>=3.4`, `aiosqlite>=0.20`, `httpx>=0.27`,
`qrcode[pil]>=7.4`, `APScheduler>=3.10`, `pydantic-settings>=2.3`,
`loguru>=0.7`. Build-backend — `hatchling`, пакет —
`app`. Дополнительная группа `dev` содержит `pytest`, `pytest-asyncio`,
`respx`, `ruff`. Включает базовые настройки `ruff` (line-length=100,
target-version=py312).

### [.env.example](./.env.example)
Шаблон конфигурации с полным списком переменных окружения:
`BOT_TOKEN`, `ADMIN_IDS`, `DB_PATH`, все `XUI_*`, `LOG_LEVEL`. Пользователь
копирует в `.env` и заполняет реальными значениями.

### [.gitignore](./.gitignore)
Игнорирует виртуальные окружения (`.venv/`, `venv/`), Python-кеш
(`__pycache__/`, `*.py[cod]`), артефакты сборки (`build/`, `dist/`,
`*.egg-info/`), локальные данные (`data/`, `*.db`, журналы SQLite),
секреты (`.env`, `.env.local`), IDE/OS-метаданные, тестовые кеши.

### [README.md](./README.md)
Описание бота, стек, требования к окружению, инструкции по локальной установке
и серверному деплою через systemd, таблицы обязательных и необязательных
переменных окружения, инструкции по обновлению и бэкапу SQLite-БД, описание
пользовательского и админского флоу, ссылки на [architecture.md](./architecture.md)
и [docs/e2e-checklist.md](./docs/e2e-checklist.md).

## Каталог `deploy/`

### [deploy/tg-vpn-bot.service](./deploy/tg-vpn-bot.service)
Systemd unit для запуска бота как сервиса на Linux. Описывает:
- `[Unit]`: `Description`, `After=network.target`, `Wants=network-online.target`
  (дождаться готовности сети для Telegram long polling).
- `[Service]`: `Type=simple`, `WorkingDirectory=/opt/3x-ui-tg-bot`,
  `EnvironmentFile=/opt/3x-ui-tg-bot/.env`, `ExecStart=/opt/3x-ui-tg-bot/.venv/bin/python -m app.main`,
  `Restart=on-failure` с `RestartSec=5`, `User=tgbot`, `Group=tgbot`, логи в journald
  (`StandardOutput=journal`, `StandardError=journal`, `SyslogIdentifier=tg-vpn-bot`).
- `[Install]`: `WantedBy=multi-user.target` (автозапуск).

Устанавливается командой `sudo cp deploy/tg-vpn-bot.service /etc/systemd/system/`
с последующими `daemon-reload` и `enable --now`. Подробная инструкция —
в [README → Деплой](./README.md#деплой-systemd).

### [deploy/install-3x-ui.sh](./deploy/install-3x-ui.sh)
Идемпотентный bash-скрипт автоматической установки 3x-ui (VLESS+Reality)
и опционально Telegram-бота на чистый Ubuntu/Debian сервер. Запускается
от root: `sudo bash deploy/install-3x-ui.sh --bot-token=... --admin-id=...
--domain=... [--install-bot --bot-repo=...]`.

Структура:
- `parse_args()`, `usage()` — разбор CLI-аргументов
  (`--bot-token`, `--admin-id`, `--domain`, `--panel-port`, `--panel-user`,
  `--panel-pass`, `--panel-path`, `--vless-port`, `--reality-dest`,
  `--reality-sni`, `--sub-port`, `--sub-path`, `--install-bot`,
  `--bot-repo`, `--ssl-mode` (auto|on|off), `--le-email`,
  `--non-interactive`, `--help`).
- `info/ok/warn/err/fatal()` — цветные логи в stderr + tee в
  `/var/log/install-3x-ui.log`.
- `cleanup()` (trap EXIT) — удаление cookie-файла + подсказка по
  восстановлению в случае ошибки.
- `ask()`, `ask_secret()` — интерактивный/неинтерактивный prompt.
- `rand_port()`, `rand_hex()`, `rand_base64()`, `port_in_use()` —
  утилиты.
- `ensure_root()`, `ensure_os()` — префлайт.
- `preflight()` — apt-зависимости (curl, jq, openssl, qrencode и пр.).
- `configure_ufw()` — открытие портов 22, VLESS, PANEL, SUB
  (+ 80 в режиме `ssl-mode=on` — только на время выпуска LE-сертификата
  через certbot --standalone) в ufw (если активен).
- `install_3x_ui()` — скачивает и запускает официальный installer
  3x-ui от MHSanaei (v3+), подавая ему серию из трёх ответов:
  не кастомизировать порт → выбрать SSL=skip → bind 127.0.0.1
  (yes в nginx-режиме, no в skip-режиме).
- `wait_service_active()` — ожидание `systemctl is-active` с таймаутом.
- `configure_panel_settings()` — `x-ui setting -username/-password/-port
  /-webBasePath` + попытка `-subPort/-subPath` (если CLI поддерживает).
- `build_panel_urls()`, `panel_curl()`, `panel_login()` — обёртки REST
  API панели. `PANEL_BASE_LOCAL=http://127.0.0.1:PORT/...` — все REST-вызовы
  делаются по HTTP (TLS включается в `setup_panel_tls` уже после всех
  API-вызовов). `PANEL_BASE_PUBLIC` строится с учётом `SSL_MODE`
  (on → https://DOMAIN:PANEL_PORT/..., off → http://...). `panel_login`
  дожидается реальной готовности порта через `wait_port_listening`.
- `configure_sub_via_api()` — fallback для subPort/subPath через
  `/panel/setting/all` + `/panel/setting/update`, если CLI не справился.
- `generate_reality_keys()` — получение x25519 ключей через
  `/server/getNewX25519Cert` или `xray x25519`.
- `create_inbound()` — `POST /panel/api/inbounds/add` с VLESS+Reality
  payload (network=tcp, security=reality, sniffing http/tls/quic);
  парсит `obj.id` (с fallback на `/panel/api/inbounds/list`).
- `setup_panel_tls()` — (только при `SSL_MODE=on`) ставит `certbot`,
  выпускает Let's Encrypt сертификат через `certbot certonly --standalone
  -d DOMAIN` (с `--register-unsafely-without-email` если `LE_EMAIL` не
  задан), записывает пути `/etc/letsencrypt/live/<DOMAIN>/{fullchain,privkey}.pem`
  в SQLite (`settings.webCertFile/webKeyFile/subCertFile/subKeyFile`)
  атомарной транзакцией DELETE+INSERT, перезапускает x-ui. Создаёт
  renewal-hook `/etc/letsencrypt/renewal-hooks/deploy/restart-x-ui.sh`
  (после `certbot renew` рестартует x-ui чтобы он подхватил новый cert).
  Reverse-proxy не используется — TLS обслуживает сама панель.
- `write_env()` — генерация `.env`. При `SSL_MODE=on`:
  `XUI_BASE_URL=https://DOMAIN:PANEL_PORT/<panel_path>/`,
  `XUI_SUB_BASE_URL=https://DOMAIN:SUB_PORT/<sub_path>/`,
  `XUI_VERIFY_SSL=true`. При `off`: те же URL по http,
  `XUI_VERIFY_SSL=false`. Кладёт в `/opt/3x-ui-tg-bot/.env` при
  `--install-bot`, иначе в `/root/3x-ui-tg-bot.env`. chmod 600.
- `install_bot()` — при `--install-bot`: ставит python3.12 (через
  deadsnakes PPA, если системный <3.12), создаёт пользователя `tgbot`,
  клонирует `--bot-repo` в `/opt/3x-ui-tg-bot`, делает venv +
  `pip install -e .`, копирует `deploy/tg-vpn-bot.service` и поднимает
  через `systemctl enable --now`.
- `final_report()` — печатает URL панели, логин/пароль, ID inbound,
  Reality publicKey/shortId, путь к `.env`, команды для проверки и
  рекомендации по бэкапу.
- `main()` — оркестрация шагов.

### [deploy/install-3x-ui.md](./deploy/install-3x-ui.md)
Документация на русском к скрипту `install-3x-ui.sh`: что делает
пошагово, таблица всех CLI-аргументов с дефолтами, примеры запуска
(минимальный, полный, через curl одной командой), описание лог-файлов и
расположения `.env`/БД, объяснение идемпотентности, раздел
troubleshooting (зависший installer, неактивный сервис x-ui, ошибки
генерации x25519, занятые порты, упавший `tg-vpn-bot.service`, полное
удаление), инструкции по обновлению 3x-ui и бота, заметки по
безопасности (история shell, cookie-файл, видимость секретов в `ps`).

## Каталог `docs/`

### [docs/e2e-checklist.md](./docs/e2e-checklist.md)
Ручной end-to-end чек-лист для прогона сквозных сценариев на staging-инстансе
3x-ui и dev-аккаунте Telegram-бота (Stars test mode). Содержит 13 блоков:
подготовка окружения; админ-флоу (старт, создание тарифа `Test-30d`,
создание трёх промокодов — `percent`, `flat_stars`, `free_days`);
пользовательский флоу (старт, покупка тарифа, подключение XRay-клиентом,
проверка роста трафика); покупка со скидкой `percent` и `flat_stars`;
активация `free_days`; деактивация тарифа; сводная статистика; имитация
истечения подписки через прямой `UPDATE subscriptions SET expires_at`
и проверка expire-job в [app/scheduler.py](./app/scheduler.py); завершение
(фиксация багов в `br`).

## Концептуально: несколько активных подписок на пользователя

Бот поддерживает модель «N активных подписок на одного пользователя».
Подписка (`subscriptions` row) = один xui-client (`xui_client_uuid` +
`xui_client_email` + `xui_sub_id`) на конкретном inbound
(`xui_inbound_id`). У одного пользователя могут одновременно быть
несколько таких подписок (например, на разных inbound-ах или просто
несколько устройств), каждая со своим Subscription URL, своим
истечением и своим счётчиком трафика.

**Источники списка подписок:**
- `subs_repo.list_active_for_user(user_id)` — все active с
  `expires_at > now`, ORDER BY `expires_at DESC` (для action-экранов
  и кнопок).
- `subs_repo.list_for_user(user_id)` — все подписки (active +
  expired/revoked), для «Моя подписка»-экрана.
- `subs_repo.get_active_for_user(user_id)` — одна (последняя),
  используется только для backward-compat-проверок «есть ли вообще
  активная» (например, в `start.cmd_start` для toggle главного меню).

**Принятие решения extend vs new — на стороне UI:**
- Service-слой (`subs_service.create_or_extend`,
  `subs_service.activate_free_days`, `subs_service._provision`) не
  угадывает ветку: caller всегда передаёт `extend_sub_id` явно
  (`None` = новая, `int` = продлить именно эту).
- UI показывает экран «Что сделать?» через `buy_action_kb` (платный
  флоу) и `promo_action_kb` (free_days промо), если у пользователя
  есть хотя бы одна active подписка. Кнопки: «🔄 Продлить #N ·
  <inbound-remark>» (по одной на каждую sub) + «🆕 Новая подписка».
- В `BuyFlow` это шаг `choosing_action` (перед `choosing_plan`),
  в `PromoActivate` — одноимённый шаг (после `waiting_code` и
  валидации free_days). Если активных подписок нет, шаг
  пропускается.

**Перенос extend-target через границы processes:**
- Buy-флоу: `BuyCB.sub_id` (callback в TG keyboard) → FSM-data
  `sub_id` → `BuyCB.sub_id` в `confirm_kb` → `billing.send_invoice(
  sub_id=...)` → JSON payload ключ `"s"` → `parse_invoice_payload`
  возвращает 4-tuple → `subs_service.create_or_extend(extend_sub_id=
  sub_id or None)`.
- Promo-флоу: `PromoActCB.sub_id` (callback) → загрузка sub из БД с
  ownership-check → `subs_service.activate_free_days(extend_sub_id=
  sub.id, inbound_id=sub.xui_inbound_id)` (inbound наследуется).

**Inbound на extend:**
- При продлении inbound берётся из существующей подписки
  (`existing.xui_inbound_id`). `_provision` явно игнорирует
  переданный `inbound_id` при `extend_sub_id is not None` (логирует
  WARNING на mismatch). Это значит: подписка живёт на одном
  xui-inbound всю свою жизнь; чтобы получить подписку на новом
  inbound, надо создать новую (action-экран → «🆕 Новая»).
- В `cb_confirm` и `on_pre_checkout` платного флоу для extend-ветки
  валидация `inbound_id ∈ plan.allowed_inbounds` намеренно
  пропущена, чтобы пользователи могли продлевать подписки на
  inbound-ах, которые больше не привязаны ни к одному плану.

**Quota / totalGB на extend:**
- `update_client` при extend намеренно НЕ передаёт `totalGB` —
  накопленная квота и счётчик использованного трафика
  пользователя сохраняются. `total_gb` применяется только при
  свежем provisioning.

**UI рендера в «Моя подписка»:**
- `_build_subs_keyboard` собирает по строке на каждую видимую
  подписку (cap `_MAX_VISIBLE_SUBS = 5`): «🔑 Ключи #N» и (для
  активных) «🛒 Продлить #N». Кнопки «Продлить» отправляют
  `BuyCB(action='extend', sub_id=N)`, что попадает прямо в
  `buy.cb_pick_action_extend` (entry-point из my_subscription и
  из action-экрана делят один и тот же хендлер).

## Пакет `app/`

### [app/\_\_init\_\_.py](./app/__init__.py)
Маркер пакета. Содержимого не имеет.

### [app/main.py](./app/main.py)
Точка входа приложения (`python -m app.main`).

- `async def main() -> None` — последовательность:
  1. `setup_logging()`.
  2. `await init_db()` — применение `schema.sql` + миграций.
  3. Создание `Bot(token=settings.BOT_TOKEN,
     default=DefaultBotProperties(parse_mode=ParseMode.HTML))` и
     `Dispatcher(storage=MemoryStorage())`.
  4. `register_routers(dp)`.
  5. `setup_scheduler(bot).start()` — три cron-job-а
     (`expire_check`, `reminders`, `traffic_snapshots`).
  6. `await dp.start_polling(bot)`.
  7. В `finally`: `scheduler.shutdown(wait=False)`, `await close_xui_client()`,
     `await bot.session.close()`. Все три обёрнуты в try/except,
     чтобы остановка была best-effort.
- `if __name__ == "__main__"` блок вызывает `asyncio.run(main())` и ловит
  `KeyboardInterrupt`/`SystemExit` для graceful shutdown без traceback.

### [app/config.py](./app/config.py)
Конфигурация приложения через `pydantic-settings`.

- Класс `Settings(BaseSettings)` объявляет поля:
  `BOT_TOKEN: str`, `ADMIN_IDS: Annotated[list[int], NoDecode]`,
  `DB_PATH: str = "./data/bot.db"`, `XUI_BASE_URL`, `XUI_USERNAME`,
  `XUI_PASSWORD`, `XUI_INBOUND_ID: int`, `XUI_SERVER_HOST`,
  `XUI_SUB_BASE_URL`, `XUI_VERIFY_SSL: bool = True`, `LOG_LEVEL: str = "INFO"`.
- `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8",
  case_sensitive=True, extra="ignore")`.
- `@field_validator("ADMIN_IDS", mode="before") _parse_admin_ids` —
  принимает CSV-строку `"1,2,3"`, пустую строку, JSON-массив или список.
  Аннотация `NoDecode` отключает попытку pydantic-settings распарсить
  значение через `json.loads` до запуска валидатора.
- Экспортирует синглтон `settings = Settings()`.

### [app/logger.py](./app/logger.py)
Настройка loguru и мост со стандартным `logging`.

- Класс `InterceptHandler(logging.Handler)` — пробрасывает записи stdlib
  `logging` в loguru, сохраняя имя уровня (или числовой уровень) и
  корректный кадр-источник через раскрутку `logging.currentframe`.
- Константа `_LOG_FORMAT` — формат вывода
  (time / level / name:function:line / message).
- `def setup_logging(level: str | None = None) -> None` — удаляет дефолтный
  sink, добавляет sink на `sys.stderr`, монтирует `InterceptHandler` через
  `logging.basicConfig`, отдельно перенаправляет известные шумные логгеры
  (`aiogram`, `aiogram.event`, `httpx`, `httpcore`, `apscheduler`).
- Импорт модуля побочных эффектов не вызывает.

## Пакет `app/db/`

Слой работы с SQLite через `aiosqlite`. Никакого ORM — чистый SQL.
Все функции репозиториев `async` и принимают `aiosqlite.Connection`,
получаемый из `app.db.engine.get_conn()`.

### [app/db/\_\_init\_\_.py](./app/db/__init__.py)
Маркер пакета. Документирует публичный API слоя: `init_db`, `get_conn`,
`transaction` из `engine.py`, плюс репозитории в `repos/`.

### [app/db/schema.sql](./app/db/schema.sql)
Идемпотентная DDL-схема (все DDL — `CREATE … IF NOT EXISTS`). Применяется
`engine.init_db()` через `executescript`.

Таблицы:
- `users` (id PK, tg_id UNIQUE, username, first_name, is_admin, created_at).
- `plans` (id PK, title, days, price_stars, traffic_gb, is_active, created_at) — тарифы;
  `CHECK days > 0`, `CHECK price_stars >= 0`, `CHECK traffic_gb >= 0`.
  `traffic_gb` — лимит трафика тарифа в ГБ (0 = без лимита), пробрасывается в
  3x-ui как `totalGB` при `add_client`. Колонка добавлена идемпотентной миграцией
  `ALTER TABLE plans ADD COLUMN traffic_gb INTEGER NOT NULL DEFAULT 0` в
  `_apply_migrations`.
- `plan_inbounds` (plan_id FK plans.id ON DELETE CASCADE, inbound_id,
  PRIMARY KEY (plan_id, inbound_id)) — many-to-many между тарифами и
  inbound id из 3x-ui панели. `inbound_id` хранится без FK (это id из
  3x-ui, не локальная запись). `ON DELETE CASCADE` гарантирует
  консистентность при удалении тарифа. Один тариф может обслуживаться
  несколькими inbound'ами (мульти-регион/мульти-протокол).
- `promos` (id PK, code UNIQUE, type CHECK IN ('percent','flat_stars','free_days'),
  value, max_uses, used_count, expires_at NULL, created_at,
  created_by FK users.id ON DELETE SET NULL).
- `subscriptions` (id PK, user_id FK users.id ON DELETE CASCADE,
  xui_inbound_id, xui_client_uuid, xui_client_email, xui_sub_id (для
  public sub URL), expires_at, created_at,
  plan_id FK plans.id ON DELETE SET NULL,
  status CHECK IN ('active','expired','revoked')).
- `promo_redemptions` (id PK, promo_id FK ON DELETE CASCADE, user_id FK ON DELETE CASCADE,
  subscription_id FK ON DELETE SET NULL, redeemed_at).
- `payments` (id PK, user_id FK ON DELETE CASCADE, subscription_id FK ON DELETE SET NULL,
  telegram_charge_id UNIQUE, stars_amount, plan_id FK ON DELETE SET NULL,
  promo_id FK ON DELETE SET NULL, status CHECK IN ('paid','refunded'), created_at).
- `traffic_snapshots` (id PK, subscription_id FK ON DELETE CASCADE, up, down, taken_at).
- `subscription_notifications` (id PK, subscription_id FK ON DELETE CASCADE,
  kind CHECK IN ('3d','1d','0d','expired'), sent_at,
  UNIQUE(subscription_id, kind)) — ledger дедупликации для scheduler-job-ов
  напоминаний и финального уведомления об истечении.

Индексы: `users(tg_id)`, `subscriptions(user_id)`, `subscriptions(user_id,status)`,
`subscriptions(expires_at)`, `promos(code)`, `promo_redemptions(promo_id)`,
`promo_redemptions(user_id)`, `payments(user_id)`, `payments(telegram_charge_id)`,
`traffic_snapshots(subscription_id, taken_at)`,
`subscription_notifications(subscription_id)`, `plan_inbounds(plan_id)`.

### [app/db/engine.py](./app/db/engine.py)
Async-движок поверх `aiosqlite`.

- `async def init_db() -> None` — создаёт директорию `DB_PATH.parent`,
  открывает соединение, применяет `schema.sql` через `executescript`,
  затем вызывает `_apply_migrations(conn)`.
- `async def _apply_migrations(conn)` — два набора миграций плюс backfill:
  1. Идемпотентные `ALTER TABLE` (try/except на "duplicate column"/
     "already exists"). Текущий перечень: добавление
     `subscriptions.xui_sub_id TEXT NOT NULL DEFAULT ''` и
     `plans.traffic_gb INTEGER NOT NULL DEFAULT 0`.
  2. `CREATE TABLE/INDEX IF NOT EXISTS` для таблиц, появившихся после
     первоначальной схемы. Применяются и на свежих БД (no-op, т.к.
     SQL идемпотентен), и при апгрейде существующих. Текущий перечень:
     `subscription_notifications` + индекс `idx_subscription_notifications_sub`,
     `plan_inbounds` + индекс `idx_plan_inbounds_plan`.
  3. Backfill `plan_inbounds` для legacy-планов без записей:
     `INSERT OR IGNORE INTO plan_inbounds (plan_id, inbound_id)
     SELECT id, ? FROM plans WHERE id NOT IN (SELECT plan_id FROM plan_inbounds)`
     с параметром `settings.XUI_INBOUND_ID`. Условие `WHERE id NOT IN (...)`
     обеспечивает идемпотентность на уровне отдельного плана —
     повторный `init_db()` не перезатирает админский выбор inbounds.
     Если `XUI_INBOUND_ID` не задан — backfill пропускается с warning.
- `_configure_connection(conn)` — выставляет `conn.row_factory = aiosqlite.Row`,
  выполняет `PRAGMA foreign_keys = ON` и `PRAGMA journal_mode = WAL` для
  каждого соединения (pragmas в SQLite — per-connection).
- `get_conn()` — `asynccontextmanager`, открывает соединение, конфигурирует
  его и закрывает на выходе.
- `transaction(conn=None)` — `asynccontextmanager` оборачивающий
  `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK` блок. Принимает существующий
  `conn` или открывает новое соединение. Откатывает транзакцию при
  любом исключении в теле.
- Константа `_SCHEMA_PATH = Path(__file__).parent / "schema.sql"`.

## Пакет `app/db/repos/`

### [app/db/repos/\_\_init\_\_.py](./app/db/repos/__init__.py)
Маркер пакета репозиториев. Документирует, что каждая функция принимает
`aiosqlite.Connection` (DI) и не открывает соединения сама.

### [app/db/repos/users.py](./app/db/repos/users.py)
Репозиторий пользователей.

- Dataclass `User(id, tg_id, username, first_name, is_admin, created_at)`.
- `User.from_row(row)` — построение из `aiosqlite.Row`.
- `async def get_by_tg_id(conn, tg_id) -> User | None`.
- `async def get_by_id(conn, user_id) -> User | None`.
- `async def get_by_username(conn, username) -> User | None` —
  case-insensitive (`COLLATE NOCASE`); удаляет ведущий `@`, пустой
  запрос → `None`. Используется админским поиском по @handle.
- `async def create(conn, tg_id, username, first_name, is_admin=False) -> User`.
- `async def get_or_create(conn, tg_id, username, first_name) -> User` —
  идемпотентен; `is_admin` синхронизируется с `settings.ADMIN_IDS`.
- `async def list_all_tg_ids(conn) -> list[int]` — `tg_id` всех
  пользователей, старейшие первыми (`ORDER BY id`); используется
  админской рассылкой (`app.handlers.admin.broadcast`).
- `async def set_admin(conn, user_id, value: bool)`.

### [app/db/repos/plans.py](./app/db/repos/plans.py)
Репозиторий тарифов.

- Dataclass `Plan(id, title, days, price_stars, traffic_gb, is_active, created_at)`.
  Поле `traffic_gb: int` — лимит трафика тарифа в ГБ (0 = без лимита); читается
  через `Plan.from_row`.
- Константа `_UPDATABLE_COLUMNS = {"title","days","price_stars","traffic_gb","is_active"}` —
  whitelist колонок для `update`.
- `async def create(conn, title, days, price_stars, traffic_gb=0) -> Plan` —
  `traffic_gb` опционален (по умолчанию 0 = без лимита).
- `async def get(conn, plan_id) -> Plan | None`.
- `async def list_active(conn) -> list[Plan]` — `is_active=1`, сортировка
  по `price_stars ASC`.
- `async def list_all(conn) -> list[Plan]`.
- `async def update(conn, plan_id, **fields) -> Plan` — только колонки
  из whitelist (включая `traffic_gb`); `ValueError` на остальные;
  `LookupError` если нет такого id.
- `async def deactivate(conn, plan_id)` — мягкое отключение (`is_active=0`).
- `async def get_inbounds(conn, plan_id) -> list[int]` — `SELECT inbound_id
  FROM plan_inbounds WHERE plan_id=? ORDER BY inbound_id`. Возвращает `[]`
  для несуществующих или пустых планов.
- `async def set_inbounds(conn, plan_id, inbound_ids: Iterable[int]) -> None` —
  атомарная замена набора inbound'ов тарифа: `DELETE FROM plan_inbounds
  WHERE plan_id=?` + `executemany INSERT`, обёрнуто в одну транзакцию
  (`BEGIN`/`COMMIT`, `ROLLBACK` при исключении). Дедуп входа через
  `set()`. Пустой итерируемый → `ValueError('plan must have at least
  one inbound')` (тариф без inbound невозможно купить).

### [app/db/repos/promos.py](./app/db/repos/promos.py)
Репозиторий промокодов и `promo_redemptions`.

- Литерал `PromoType = Literal["percent","flat_stars","free_days"]`.
- Dataclass `Promo(id, code, type, value, max_uses, used_count, expires_at,
  created_at, created_by)`.
- Dataclass `Redemption(id, promo_id, user_id, subscription_id, redeemed_at)`.
- Helper `_utcnow_iso()` → ISO-8601 UTC seconds-resolution.
- `async def create(conn, code, type, value, max_uses, expires_at, created_by) -> Promo`.
- `async def get(conn, promo_id) -> Promo | None`.
- `async def get_by_code(conn, code) -> Promo | None` —
  case-insensitive (`COLLATE NOCASE`).
- `async def list_active(conn) -> list[Promo]` — не истёк И есть ёмкость.
- `async def deactivate(conn, promo_id)` — `expires_at = now`.
- `async def try_redeem(conn, promo_id, user_id, subscription_id) -> bool` —
  атомарный redeem внутри `transaction(conn)`: SELECT с валидацией,
  UPDATE с capacity-guarded WHERE (`max_uses=0 OR used_count<max_uses`),
  INSERT в `promo_redemptions`. Возвращает `False` если промо невалиден
  (включая гонку).
- `async def list_redemptions(conn, promo_id) -> list[Redemption]`.

### [app/db/repos/subscriptions.py](./app/db/repos/subscriptions.py)
Репозиторий подписок + `traffic_snapshots`.

- Литерал `SubscriptionStatus = Literal["active","expired","revoked"]`.
- Helpers `_to_iso(value)` (datetime/str → ISO-8601 UTC) и `_utcnow_iso()`.
- Dataclass `Subscription(id, user_id, xui_inbound_id, xui_client_uuid,
  xui_client_email, xui_sub_id, expires_at, created_at, plan_id, status)`.
- Dataclass `TrafficSnapshot(id, subscription_id, up, down, taken_at)`.
- `async def create(conn, user_id, xui_inbound_id, xui_client_uuid,
  xui_client_email, expires_at, plan_id, xui_sub_id="") -> Subscription`
  (status='active'; `xui_sub_id` — `subId` из 3x-ui для public
  subscription URL).
- `async def get(conn, sub_id) -> Subscription | None`.
- `async def get_active_for_user(conn, user_id) -> Subscription | None` —
  последняя с `status='active' AND expires_at>now`.
- `async def list_for_user(conn, user_id) -> list[Subscription]`.
- `async def list_active_for_user(conn, user_id) -> list[Subscription]` —
  все активные подписки юзера (`status='active' AND expires_at>now`),
  ORDER BY `expires_at DESC, id DESC` (свежая по экспирации сверху).
  Используется handlers/UI для рендера выбора «продлить #N vs новая»
  и для рендера списка подписок в «Моя подписка». В отличие от
  `get_active_for_user`, который возвращает максимум одну запись,
  эта функция возвращает массив и поддерживает сценарий
  «несколько активных подписок на пользователя» (одна = один
  xui-client на конкретном inbound).
- `async def extend(conn, sub_id, new_expires_at)` — меняет только `expires_at`.
- `async def set_status(conn, sub_id, status)` — меняет только статус.
- `async def list_expired_active(conn, now=None) -> list[Subscription]` —
  для expire-job-а: active И `expires_at<=now`.
- `async def list_active(conn) -> list[Subscription]`.
- `async def list_expiring_in(conn, days) -> list[Subscription]` —
  active в окне `(now, now+days]`.
- `async def add_traffic_snapshot(conn, sub_id, up, down) -> TrafficSnapshot`.
- `async def last_traffic_snapshot(conn, sub_id) -> TrafficSnapshot | None`.
- Литерал `NotificationKind = Literal["3d","1d","0d","expired"]`.
- `async def try_mark_notification_sent(conn, sub_id, kind) -> bool` —
  атомарный `INSERT OR IGNORE` в `subscription_notifications`. Возвращает
  `True`, если строка была вставлена (значит можно слать сообщение), и
  `False`, если запись `(sub_id, kind)` уже существовала. Используется
  scheduler-job-ами для дедупликации напоминаний (UNIQUE-constraint
  гарантирует, что каждое kind отправляется ровно один раз).

### [app/db/repos/payments.py](./app/db/repos/payments.py)
Репозиторий Stars-платежей.

- Литерал `PaymentStatus = Literal["paid","refunded"]`.
- Dataclass `Payment(id, user_id, subscription_id, telegram_charge_id,
  stars_amount, plan_id, promo_id, status, created_at)`.
- Helper `_to_iso(value)` — datetime/str → ISO-8601 UTC.
- `async def create(conn, user_id, subscription_id, telegram_charge_id,
  stars_amount, plan_id, promo_id, status='paid') -> Payment` — UNIQUE
  на `telegram_charge_id` приводит к `IntegrityError` на дубль; caller
  должен ловить и обращаться к `get_by_charge_id`.
- `async def get(conn, payment_id) -> Payment | None`.
- `async def get_by_charge_id(conn, telegram_charge_id) -> Payment | None`.
- `async def list_for_user(conn, user_id) -> list[Payment]` —
  `ORDER BY created_at DESC`.
- `async def total_stars_period(conn, start, end) -> int` — сумма
  `stars_amount` только для `status='paid'` в окне `[start,end]`.
- `async def set_status(conn, payment_id, status)`.

## Пакет `app/handlers/`

### [app/handlers/\_\_init\_\_.py](./app/handlers/__init__.py)
Агрегатор роутеров и middleware верхнего уровня.

- `def register_routers(dp: Dispatcher) -> None`:
  1. Регистрирует `UserContextMiddleware` на `dp.update.outer_middleware` —
     каждый апдейт получает `data['user']` до маршрутизации.
  2. Подключает `start.router` (первым — `/start` должен срабатывать всегда).
  3. Подключает `admin_router` (с собственной `AdminOnlyMiddleware` на
     router-level).
  4. Подключает `user_router` (catch-all для юзерских колбеков и
     сообщений; FSM-стейты `BuyFlow`/`PromoActivate` живут в нём).

### [app/handlers/start.py](./app/handlers/start.py)
Роутер команды `/start`.

- `router = Router(name="start")`.
- `async def cmd_start(message: Message, user: User | None = None)` —
  хэндлер `CommandStart()`. Если `user.is_admin` — отвечает админ-меню
  (`admin_main_menu()`); иначе показывает `user_main_menu(has_subscription)`
  с приоритетом «Моя подписка» если `subs_repo.get_active_for_user`
  вернул запись. `user` приходит из `data`, проброшенного
  `UserContextMiddleware`.

### [app/handlers/admin/\_\_init\_\_.py](./app/handlers/admin/__init__.py)
Агрегатор админ-роутера.

- `_build_admin_router()` строит `Router(name="admin")`, навешивает
  `AdminOnlyMiddleware` на `admin_router.message` и
  `admin_router.callback_query`, включает суб-роутеры
  `menu.router`, `plans.router`, `promos.router`, `users.router`,
  `stats.router`.
- Экспортирует `admin_router`.

### [app/handlers/admin/menu.py](./app/handlers/admin/menu.py)
Хэндлеры `/admin` и навигации в админ-меню.

- `router = Router(name="admin_menu")`.
- `async def cmd_admin(message)` — `Command("admin")`, отвечает
  `_GREETING` + `admin_main_menu()`.
- `async def open_main(callback)` — `AdminCB(area=main, action in {open,back})`,
  редактирует сообщение обратно в главное меню.
- `async def cancel_fsm(callback, state)` — `AdminCB(action=cancel)`,
  `state.clear()` + возврат в меню. Единая Cancel-точка для всех wizard'ов.
- Константа `_GREETING`.

### [app/handlers/admin/plans.py](./app/handlers/admin/plans.py)
Хэндлеры CRUD тарифов с FSM-флоу.

- `router = Router(name="admin_plans")`.
- Helpers:
  - `_format_plan(plan, inbound_remarks=None)` — HTML-карточка
    (показывает title/days/price/traffic_gb/is_active). Если передан
    `inbound_remarks: dict[int, str]` — добавляется строка
    «Подключения: <remark1>, <remark2>»; для удалённых из 3x-ui
    (пустой remark) — «id=NN (удалён)».
  - `_resolve_inbound_remarks(inbound_ids)` — резолвит remark'и через
    `app.services.inbounds.list_user_inbounds`; при `XuiError` graceful
    degrade (пустые строки для всех id).
  - `_show_card(message, plan_id, edit=True)` — рендер карточки:
    `plans_repo.get` + `plans_repo.get_inbounds` + `_resolve_inbound_remarks`.
  - `_show_list(message, edit=True)` — сортировка active→inactive.
- Callbacks: `cb_list` (`PlanCB.action=list`, очищает state),
  `cb_card` (`action=card`), `cb_edit_menu` (`action=edit_menu`),
  `cb_deactivate` (`action=deactivate`).
- Wizard `PlanCreate` (5 шагов): `cb_create` → `st_title` → `st_days`
  → `st_price` → `st_traffic_gb` → `_enter_inbounds_step` →
  `waiting_inbounds`. На численных шагах показывается пресет-
  клавиатура (`plan_days_presets_kb` / `plan_price_presets_kb` /
  `plan_gb_presets_kb`), но ручной текстовый ввод тоже работает.
  Валидация: title непустой, days>0, price_stars≥0, traffic_gb≥0.
  - `_enter_inbounds_step(message, state)` — после ввода `traffic_gb`
    загружает `list_user_inbounds`, кэширует options в FSM data
    (`inbound_options`, сериализованные dict'ы), инициализирует
    `selected_inbounds=[]`, показывает `plan_inbounds_select_kb`.
    При `XuiError` или пустом списке inbound'ов — сообщение об ошибке,
    state не двигается.
  - `_options_from_data(data)` — реконструирует `list[InboundOption]`
    из FSM data для перерисовки клавиатуры без повторного запроса
    в 3x-ui.
  - `cb_toggle_inbound` (`action=toggle_inbound`, `id=inbound_id`) —
    XOR id в `selected_inbounds`, `edit_reply_markup` с обновлённой
    клавиатурой. Общий для create и edit (различения здесь нет).
  - `cb_inbounds_done` (`action=inbounds_done`) — финализация. Пустой
    `selected` → `callback.answer('Выберите хотя бы одно подключение',
    show_alert=True)`. Иначе: если в state есть `editing_plan_id` →
    edit-режим (`plans_repo.set_inbounds` + `_show_card`); иначе →
    `_finalize_plan_create`.
  - `_finalize_plan_create(message, state, *, selected_inbounds)` —
    `plans_repo.create(...)` + `plans_repo.set_inbounds(plan.id, selected)`
    + рендер карточки с remark'ами.
- Общие preset/manual callback-и (`PlanCB.action ∈ {preset, manual}`,
  `field ∈ {days, price, gb}`): `cb_plan_preset` пишет выбранное
  значение в FSM-data, переключает state и шлёт клавиатуру следующего
  шага. На шаге `gb` записывает `traffic_gb` и вызывает
  `_enter_inbounds_step` (передаёт управление в multi-select inbound'ов).
  `cb_plan_manual` переключает шаг на ручной текстовый ввод (оставляет
  тот же `waiting_*` state и показывает подсказку). Мапа `_PRESET_FLOW`
  связывает `field` пресета с FSM-data ключом, следующим состоянием
  и фабрикой клавиатуры (для `gb` next_state=None).
- Wizard `PlanEdit`:
  - `cb_edit_inbounds` (`PlanCB.action=edit, field=inbounds`) —
    отдельная ветка для multi-select редактирования подключений
    существующего тарифа. Регистрируется ПЕРЕД `cb_edit` (фильтр
    специфичнее). Загружает текущие inbound'ы (`get_inbounds`) +
    `list_user_inbounds`, кладёт в state `editing_plan_id`,
    `selected_inbounds=list(current)`, `inbound_options`. Использует
    то же состояние `PlanCreate.waiting_inbounds` и общие
    `cb_toggle_inbound`/`cb_inbounds_done` (различение по
    `editing_plan_id`). При `XuiError` или пустом списке inbound'ов —
    alert через `callback.answer(..., show_alert=True)`.
  - `cb_edit` (`PlanCB.field` ∈ title/days/price_stars/traffic_gb) →
    `st_edit_value`. `plans_repo.update`, `LookupError` на отсутствующий
    plan_id. Поле `inbounds` НЕ обрабатывается здесь — у него своя ветка.
- Константа `_FIELD_LABELS` — подсказки при редактировании текстовых
  полей (title/days/price_stars/traffic_gb). Поле `inbounds` в неё
  НЕ входит.

### [app/handlers/admin/promos.py](./app/handlers/admin/promos.py)
Хэндлеры CRUD промокодов с FSM-флоу.

- `router = Router(name="admin_promos")`.
- Helpers: `_TYPE_LABELS` — RU-метки для типов; `_format_promo(promo)` —
  HTML-карточка со статусом (активен/исчерпан/истёк); `_list_all_promos(conn)`
  — inline-SQL (репо не имеет `list_all`); `_promo_is_active(promo)`;
  `_show_card`, `_show_list`; `_parse_expires_at(raw)` — принимает
  `-`/`skip`/`нет`/`no` → `None`, иначе `YYYY-MM-DD` → ISO-8601 UTC
  23:59:59, `False` на parse-error.
- Callbacks: `cb_list`/`cb_card`/`cb_deactivate`/`cb_redemptions`.
  `cb_redemptions` показывает историю с tg_id + датой + sub_id.
- Wizard `PromoCreate`: `cb_create` → `st_code` (уникальность через
  `get_by_code`, без пробелов) → `cb_type` (`PromoCB.action=type`,
  `field` ∈ {`percent`,`flat_stars`,`free_days`}) → `st_value`
  (percent 1..100, flat_stars/free_days >0) → `st_max_uses` (≥0,
  0 = unlimited) → `st_expires_at` (parse + `promos_repo.create` с
  `created_by=user.id`). На `aiosqlite.IntegrityError` — fallback с
  сообщением об ошибке.

  На каждом из шагов value / max_uses / expires_at показывается пресет-
  клавиатура (`promo_value_presets_kb(promo_type)` /
  `promo_max_uses_presets_kb` / `promo_expires_presets_kb`), но ручной
  текстовый ввод сохранён. Финализация шага expires вынесена в
  `_finalize_promo_create` — общая точка для preset- и manual-путей.

- Общие preset/manual callback-и (`PromoCB.action ∈ {preset, manual}`,
  `field ∈ {value, max_uses, expires}`): `cb_promo_preset` пишет
  выбранное значение в FSM-data и переходит к следующему шагу (для
  `expires` конвертирует `+N дней` через `_expires_days_to_iso(days)`,
  где `0 → None` = бессрочно, и сразу финализирует промокод);
  `cb_promo_manual` переключает шаг на ручной текстовый ввод. Мапа
  `_PROMO_STEP_FLOW` связывает `field` пресета с FSM-data ключом,
  следующим состоянием и фабрикой клавиатуры.

### [app/handlers/admin/users.py](./app/handlers/admin/users.py)
Админский экран «Пользователи»: поиск + карточка пользователя.

- `router = Router(name="admin_users")`.
- Константы: `_MAX_PAYMENTS = 10`.
- Helpers:
  - `_safe(value) -> str` — HTML-escape (`&`, `<`, `>`) для имён/usernames.
  - `_fetch_traffic_line(sub) -> str` — `xui.clients.get_client_traffics`,
    `XuiError` → «панель недоступна», пустой ответ → «клиент не найден
    в панели», для не-active подписок возвращает `""`.
  - `_sub_status_glyph(sub)` — ✅/🚫/❌ по эффективному статусу.
  - `_format_payment(p)` — однострочный summary платежа
    (stars + charge_id + plan + promo + дата + статус).
  - `_build_card(target) -> (text, active_sub_id, is_admin)` — собирает
    HTML-карточку: header (имя/tg_id/username/is_admin/created_at) +
    подписки (active с трафиком, inactive — компактный список до 5) +
    последние 10 платежей. Обрезает на 4000 символов.
  - `_render_card_message(message, target, edit=True)` — рендер.
  - `_resolve_user_query(query) -> User | None` — цифры → `get_by_tg_id`,
    иначе → `get_by_username` (case-insensitive).
- Хендлеры:
  - `cb_open_users` (`AdminCB area=users action=open`) — вход из админ-
    меню, ставит FSM `AdminSearchUser.waiting_query`, просит ввести
    tg_id или @username.
  - `cb_search` (`UserCB action=search`) — повторный вход в поиск.
  - `st_query` (`AdminSearchUser.waiting_query`) — резолвит и рендерит
    карточку, либо «не найден».
  - `cb_card` (`UserCB action=card`) — открытие карточки по `users.id`.
  - `cb_revoke` (`UserCB action=revoke, id=sub_id, user_id=users.id`)
    — `services.subscriptions.revoke(xui, sub)`; защита
    `sub.user_id == target.id`; перерисовка карточки.
  - `cb_toggle_admin` (`UserCB action=toggle_admin, id=users.id`) —
    flip `is_admin` через `users_repo.set_admin` (учитывается, что
    `UserContextMiddleware` синхронизирует с `ADMIN_IDS`).

### [app/handlers/admin/stats.py](./app/handlers/admin/stats.py)
Админский экран «Статистика». Stateless — период несётся в callback.

- `router = Router(name="admin_stats")`.
- Константы:
  - `_PERIODS` — `{key: (label, timedelta)}` для 7d / 30d / all
    (all = `timedelta(days=36500)`).
  - `_DEFAULT_PERIOD = "30d"`.
  - `_EXPIRING_WINDOW_DAYS = 7`.
  - `_PAYMENTS_WINDOW = timedelta(days=30)` — фиксированное окно для
    счётчика платежей (стабильная точка сравнения вне зависимости от
    выбранного headline-периода).
  - `_MAX_EXPIRING_ROWS = 10`, `_TOP_PROMOS_LIMIT = 5`.
- Helpers:
  - `_period_meta(key) -> (label, timedelta)` — fallback на default.
  - `_format_expiring(subs, tg_ids)` — список «истекающих» с tg_id,
    sub#id и expires_at; обрезка на 10 + хвостовая строка.
  - `_build_text(period_key)` — в одном `get_conn` собирает:
    `revenue_stars(lookback)`, `active_subscriptions_count`,
    `expiring_in(7)`, `top_promos(5)`, `users_count`,
    `payments_count_period(30d)`, резолв `tg_id` для expiring.
    Обрезает на 4000 символов.
  - `_render(callback, period_key)` — `edit_text` с
    `stats_kb(active_period=period_key)`.
- Хендлеры:
  - `cb_open_stats` (`AdminCB area=stats action=open`) — render с
    `_DEFAULT_PERIOD`.
  - `cb_period` (`StatsCB action=period`) — переключение headline-
    периода.
  - `cb_refresh` (`StatsCB action=refresh`) — пересчёт того же периода
    (period передаётся в `callback_data.field`).

### [app/handlers/admin/broadcast.py](./app/handlers/admin/broadcast.py)
Админская рассылка поста всем пользователям. FSM `BroadcastCreate`
(`waiting_post` → `confirming`).

- `router = Router(name="admin_broadcast")`.
- `_PROMPT` — текст приглашения отправить пост.
- Хендлеры:
  - `cb_open` (`AdminCB area=broadcast action=open`) — вход из главного
    меню: `state.set_state(BroadcastCreate.waiting_post)` + `edit_text`
    приглашения с `cancel_kb`.
  - `st_post` (state `waiting_post`, любое сообщение) — сохраняет в FSM
    `post_chat_id`/`post_message_id` (само сообщение не разбирается —
    позже копируется как есть), считает аудиторию через
    `users_repo.list_all_tg_ids`, переходит в `confirming` и отвечает
    экраном подтверждения `broadcast_confirm_kb`.
  - `cb_send` (state `confirming`, `AdminCB area=broadcast action=send`) —
    мгновенно отвечает на callback, меняет сообщение на «⏳ Рассылка
    запущена…», вызывает `broadcast_message` и редактирует сообщение в
    итоговую сводку (получатели/доставлено/заблокировали/ошибки) с
    `back_to_main_kb`. При отсутствии `post_*` в FSM — alert + сброс.
- `_plural(n)` — дательное окончание «пользовател-» (ю/ям) для счётчика.
- Отмена на любом шаге — общий `cancel_fsm` из `menu.py` (кнопка
  «✖ Отмена» переиспользует `AdminCB(area=main, action=cancel)`).

## Пакет `app/keyboards/`

### [app/keyboards/\_\_init\_\_.py](./app/keyboards/__init__.py)
Маркер пакета inline-keyboards. Хранит admin- и user-клавиатуры в
отдельных подмодулях `admin.py` / `user.py`.

### [app/keyboards/admin.py](./app/keyboards/admin.py)
Inline-клавиатуры админ-флоу через `InlineKeyboardBuilder`.

**CallbackData-фабрики** (prefix без `:` — это разделитель aiogram):
- `AdminCB(prefix="adm", area, action)` — навигация
  (`area` ∈ main/plans/promos/users/stats/**broadcast**,
  `action` ∈ open/back/cancel/**send**). `action=send` под
  `area=broadcast` подтверждает рассылку.
- `PlanCB(prefix="admp", action, id=0, field="")` — list/create/card/
  edit_menu/edit/deactivate/**preset**/**manual**/**toggle_inbound**/
  **inbounds_done**;
  `field` ∈ title/days/price_stars/traffic_gb/**inbounds** (edit) или
  days/price/gb (preset/manual). Для `preset` поле `id` несёт выбранное
  целочисленное значение шага мастера; для `toggle_inbound` — `inbound_id`.
- `PromoCB(prefix="admpr", action, id=0, field="")` — list/create/card/
  deactivate/redemptions/type/**preset**/**manual**;
  `field` ∈ percent/flat_stars/free_days (type) или
  value/max_uses/expires (preset/manual). Для `preset` `id` несёт
  выбранное значение (для `expires` это число дней от «сейчас»,
  0 = «бессрочно»).
- `UserCB(prefix="admu", action, id=0, user_id=0)` — поиск/карточка/мутации
  в админском «Пользователи»; `action` ∈ search/card/revoke/toggle_admin.
  Для `revoke` — `id=sub_id`, `user_id=users.id`.
- `StatsCB(prefix="adms", action, field="")` — экран статистики;
  `action` ∈ open/period/refresh; `field` несёт период (`7d`/`30d`/`all`).

**Функции:**
- `admin_main_menu()` — 5 кнопок (Тарифы / Промокоды / Пользователи /
  Статистика / Рассылка).
- `back_to_main_kb()` — одна кнопка «В меню».
- `cancel_kb()` — одна кнопка «✖ Отмена» для FSM-wizard'ов.
- `broadcast_confirm_kb()` — экран подтверждения рассылки: «✅ Разослать»
  (`AdminCB area=broadcast action=send`) + «✖ Отмена»
  (`AdminCB area=main action=cancel`).
- `plans_list_kb(plans)` — список тарифов + «Создать» + «В меню».
  Inactive с префиксом 🔒.
- `plan_card_kb(plan_id, is_active=True)` — Редактировать / Деактивировать
  (если активен) / Назад.
- `plan_edit_fields_kb(plan_id)` — выбор поля
  (Название/Срок/Цена/**Лимит трафика (ГБ)**/**🔌 Подключения**) + Назад.
  Кнопка «Подключения» отправляет
  `PlanCB(action="edit", id=plan_id, field="inbounds")` — хендлер
  открывает multi-select экран вместо текстового ввода.
- `plan_inbounds_select_kb(options, selected)` — multi-select inbounds
  (используется и в `PlanCreate.waiting_inbounds`, и в редактировании).
  Каждый `InboundOption` рендерится строкой `☑/☐ <remark> (port <port>)`
  (`☑` если `option.id ∈ selected`); тап шлёт
  `PlanCB(action="toggle_inbound", id=inbound_id)` для переключения
  множества в FSM data. Внизу `✅ Готово` (`PlanCB(action="inbounds_done")`)
  и `✖ Отмена` (`AdminCB(area="main", action="cancel")`).
- Пресет-клавиатуры мастера тарифа (используют `PlanCB(action="preset",
  field=<step>, id=<value>)` для значений и `PlanCB(action="manual",
  field=<step>)` для перехода к ручному вводу; общий помощник
  `_plan_preset_kb`):
  - `plan_days_presets_kb()` — пресеты для `PlanCreate.waiting_days`
    (7/14/30/90/180/365).
  - `plan_price_presets_kb()` — пресеты для `PlanCreate.waiting_price`
    (0/50/100/200/500/1000 ⭐).
  - `plan_gb_presets_kb()` — пресеты для `PlanCreate.waiting_traffic_gb`
    (0/10/50/100/250/500 ГБ; `0` = без лимита).
- `promos_list_kb(promos)` — список промокодов + «Создать» + «В меню».
  Исчерпанные с префиксом 🔒.
- `promo_type_kb()` — percent / flat_stars / free_days + Отмена.
- Пресет-клавиатуры мастера промокода (используют `PromoCB(action="preset",
  field=<step>, id=<value>)` для значений и `PromoCB(action="manual",
  field=<step>)` для перехода к ручному вводу; общий помощник
  `_promo_preset_kb`):
  - `promo_value_presets_kb(promo_type)` — для `PromoCreate.waiting_value`,
    набор пресетов зависит от типа: percent (5/10/15/25/50%),
    flat_stars (25/50/100/250/500 ⭐), free_days (1/3/7/14/30 дней).
    Неизвестный тип → manual-only клавиатура.
  - `promo_max_uses_presets_kb()` — для `PromoCreate.waiting_max_uses`
    (0/1/5/10/50/100; `0` = без лимита).
  - `promo_expires_presets_kb()` — для `PromoCreate.waiting_expires_at`
    (бессрочно/+7д/+30д/+90д/+365д); `id` несёт число дней от now,
    `0` = `expires_at=None`.
- `promo_card_kb(promo_id, is_active=True)` — Redemptions / Деактивировать
  / Назад.
- `user_card_kb(user_id, *, active_sub_id=None, is_admin=False)` — кнопки
  карточки пользователя: «Отозвать активную подписку» (если
  `active_sub_id`), «Сделать/Снять админа», «Найти другого», «В меню».
- `stats_kb(active_period="30d")` — переключатель 7д/30д/Всё время
  (текущий помечен «· text ·»), «🔄 Обновить» (period в payload), «В меню».

callback_data всегда укладывается в Telegram-лимит 64 байта.

## Пакет `app/middlewares/`

### [app/middlewares/\_\_init\_\_.py](./app/middlewares/__init__.py)
Re-export `UserContextMiddleware` и `AdminOnlyMiddleware`.

### [app/middlewares/user_ctx.py](./app/middlewares/user_ctx.py)
Outer dispatcher-middleware `UserContextMiddleware(BaseMiddleware)`.

- `_extract_tg_user(event)` — извлекает `from_user` из любого типа апдейта
  (Update.message / edited_message / channel_post / edited_channel_post /
  callback_query / inline_query / chosen_inline_result / shipping_query /
  pre_checkout_query / poll_answer / my_chat_member / chat_member /
  chat_join_request). Возвращает `None` если нет.
- `__call__` — открывает соединение через `get_conn`, вызывает
  `users_repo.get_or_create(conn, tg_id, username, first_name)` и
  пишет результат в `data['user']`. На ошибках БД логирует и ставит
  `data['user'] = None` — апдейт продолжает движение.

Регистрируется как `dp.update.outer_middleware(UserContextMiddleware())`.

### [app/middlewares/admin_only.py](./app/middlewares/admin_only.py)
Router-middleware `AdminOnlyMiddleware(BaseMiddleware)`.

- `__call__` — на `Message`/`CallbackQuery`: если `_is_admin` — пропускает;
  иначе отвечает «Доступ запрещён» (на CallbackQuery с `show_alert=True`) и
  возвращает `None` — handler не вызывается.
- `_is_admin(event, data)` — приоритет `data['user'].is_admin` (уже
  синхронизирован с `ADMIN_IDS` через `UserContextMiddleware`), иначе
  fallback на `event.from_user.id ∈ settings.ADMIN_IDS`.
- Константа `_ACCESS_DENIED`.

Подключается на `admin_router.message.middleware(...)` и
`admin_router.callback_query.middleware(...)`.

## Пакет `app/states/`

### [app/states/\_\_init\_\_.py](./app/states/__init__.py)
Re-export `PlanCreate`, `PlanEdit`, `PromoCreate` из `app.states.admin`
и `BuyFlow`, `PromoActivate` из `app.states.user`.

### [app/states/admin.py](./app/states/admin.py)
FSM-стейты админ-флоу (aiogram `StatesGroup`).

- `PlanCreate(waiting_title, waiting_days, waiting_price, waiting_traffic_gb,
  waiting_inbounds)` — wizard создания тарифа. После ввода цены идёт
  `waiting_traffic_gb` (non-negative int; 0 = без лимита), затем
  `waiting_inbounds` — multi-select inbounds (пустое множество ≡
  «все доступные»); завершается через `PlanCB(action="inbounds_done")`.
- `PlanEdit(waiting_field, waiting_value)` — wizard редактирования одного
  поля; `plan_id` и `field` хранятся в `FSMContext` data.
  При `field='inbounds'` waiting_value не используется — вместо этого
  открывается тот же multi-select экран (`plan_inbounds_select_kb`).
- `PromoCreate(waiting_code, waiting_type, waiting_value, waiting_max_uses,
  waiting_expires_at)` — wizard создания промокода.
- `AdminSearchUser(waiting_query)` — единичный стейт админского поиска
  юзера (tg_id-цифры или `@username`); handler резолвит запрос и
  сразу очищает state.
- `BroadcastCreate(waiting_post, confirming)` — wizard рассылки поста:
  `waiting_post` (админ присылает сообщение; его `chat_id`/`message_id`
  кладутся в FSM data) → `confirming` (подтверждение копирует пост всем
  через `app.services.broadcast.broadcast_message`).

## Пакет `app/xui/`

Async REST-клиент панели 3x-ui плюс билдеры vless-ссылок и QR.
Внешние зависимости: `httpx`, `qrcode[pil]`.

### [app/xui/\_\_init\_\_.py](./app/xui/__init__.py)
Маркер пакета. Re-exports `XuiClient`, `XuiError`, `get_xui_client`,
`close_xui_client` из `client.py`. Документирует подмодули.

### [app/xui/client.py](./app/xui/client.py)
Базовый HTTP-клиент 3x-ui.

- Класс `XuiError(RuntimeError)` — единая доменная ошибка (HTTP, JSON,
  envelope `success=false`).
- Константа `_DEFAULT_TIMEOUT = httpx.Timeout(connect=10, read=30, write=30,
  pool=10)`.
- Класс `XuiClient`:
  - `__init__(base_url=None, username=None, password=None, verify_ssl=None,
    timeout=_DEFAULT_TIMEOUT)` — поля по умолчанию из `settings.XUI_*`;
    создаёт `httpx.AsyncClient(base_url, timeout, verify, follow_redirects=True)`,
    `_login_lock = asyncio.Lock()`, `_logged_in = False`.
  - `async def login()` — сначала `_bootstrap_session()` (CSRF), затем
    `POST /login` с form-data `{username,password}` и заголовком
    `X-CSRF-Token`; сериализуется через `_login_lock`; cookie в httpx jar.
  - `async def _bootstrap_session()` — `GET /` корня панели: захватывает
    session-cookie и CSRF-токен из `<meta name="csrf-token">`
    (regex `_CSRF_META_RE`) в `self._csrf_token`. Новая мажорная версия
    3x-ui (React-rewrite) отвечает `403` на POST без токена; старые панели
    без meta-тега → токен `None`, cookie-only flow (обратная совместимость).
  - `_csrf_headers(extra=None)` — мержит `X-CSRF-Token` (если есть) в
    заголовки.
  - `async def request(method, path, **kwargs) -> httpx.Response` —
    lazy-login + single-retry при истечении сессии; добавляет CSRF-заголовок
    к каждому запросу (на retry — свежий токен после relogin).
  - `async def request_json(method, path, **kwargs) -> Any` — распаковывает
    `obj` envelope, кидает `XuiError` на неудачи.
  - `async def close()`, `__aenter__`, `__aexit__`.
  - `@staticmethod _needs_relogin(resp)` — `401`/`403` (протухший CSRF) или
    `success=false` с `msg` содержащим `login`/`session`/`unauthor`.
  - `@staticmethod _parse(resp)` — валидация и unwrap `{success,msg,obj}`-envelope.
- Константа `_CSRF_META_RE` — regex поиска CSRF-токена в HTML корня панели.
- Singleton: `async def get_xui_client() -> XuiClient` (lazy, asyncio.Lock),
  `async def close_xui_client() -> None`.

### [app/xui/inbounds.py](./app/xui/inbounds.py)
Операции с inbound'ами.

- Константа `_JSON_STRING_FIELDS = ("settings","streamSettings","sniffing","allocate")`.
- `_parse_inbound(raw) -> dict` — shallow-copy + JSON-decode subfields
  (`settings`/`streamSettings`/`sniffing`/`allocate`); малформный JSON
  оставляет строкой.
- `async def list_inbounds(client) -> list[dict]` — `GET /panel/api/inbounds/list`,
  применяет `_parse_inbound` к каждому элементу.
- `async def get_inbound(client, inbound_id) -> dict` —
  `GET /panel/api/inbounds/get/:id`; `XuiError` если obj не object;
  `clients` доступны через `obj['settings']['clients']`.

### [app/xui/clients.py](./app/xui/clients.py)
Операции над клиентами через новый email-keyed API
`/panel/api/clients/*` (React-rewrite версия 3x-ui). Клиенты адресуются по
**email**, не по UUID; envelope `{success,msg,obj}` без изменений.

- Helper `make_client_uuid() -> str` — `str(uuid4())`.
- Helper `make_client_email(tg_id: int, username: str | None = None) -> str` —
  генерирует уникальный label клиента для панели. Если задан `username`,
  он нормализуется (lowercase; все символы вне `[A-Za-z0-9_]` заменяются на
  `_`; trim ведущих/хвостовых `_`; cap 32 символа) и формат принимает вид
  `<safe_username>_tg_<tg_id>_<6hex>`. Если username пуст или нормализация
  дала пустую строку — fallback на `tg_<tg_id>_<6hex>`. Suffix
  `secrets.token_hex(3)` (6 hex) обеспечивает уникальность при
  пере-подписке после `del_client`.
- Helper `_make_sub_id() -> str` — `secrets.token_hex(8)` (16 hex).
- Helper `_q(value) -> str` — URL-encode сегмента пути/запроса
  (`quote(safe="")`, зеркало `encodeURIComponent`).
- Helper `_coerce_tg_id(tg_id) -> int` — приведение к числовому `tgId`
  (нечисловое → 0).
- `async def add_client(client, inbound_id, client_uuid, email, expiry_ts_ms,
  total_gb=0, sub_id=None, flow="", enable=True, limit_ip=0, tg_id="",
  reset=0) -> dict` — `POST /panel/api/clients/add`; тело
  `{"client": {email, uuid, subId, flow, totalGB, limitIp, tgId, enable,
  reset, expiryTime, comment}, "inboundIds": [inbound_id]}`. `obj` = `null`
  на успехе → нормализуется в fallback-dict. `expiry_ts_ms` в миллисекундах.
- Константы `_CLIENT_FIELDS` (поля для round-trip при update, **без** числового
  `id`) и `_UPDATABLE_CLIENT_FIELDS` (whitelist override-полей).
- `async def get_client(client, email) -> dict` —
  `GET /panel/api/clients/get/:email`; возвращает `obj["client"]` или `{}`
  (на "record not found").
- `async def update_client(client, email, **fields) -> dict` — **read-merge-write**:
  читает текущего клиента через `get_client`, накладывает `fields`, постит
  весь объект в `POST /panel/api/clients/update/:email` (полная замена;
  `email` обязателен, числовой `id` выбрасывается). Неизвестные ключи →
  `ValueError`; отсутствующий клиент → `XuiError`. Сохраняет нетронутые поля
  (`totalGB`/`subId`/`uuid`) — критично, чтобы revoke/extend не сбрасывали
  квоту. `_coerce_numeric_fields` приводит типы.
- `async def del_client(client, email, *, keep_traffic=False) -> None` —
  `POST /panel/api/clients/del/:email` (`?keepTraffic=1` при `keep_traffic`);
  soft-fail на `not exist`/`not found`/`no such` (идемпотентно).
- `async def get_client_traffics(client, email) -> dict` — живой трафик
  едет в пагинированном списке: `GET /panel/api/clients/list/paged?search=:email`,
  возвращает `items[].traffic` ({up,down,total,expiryTime,enable}) совпавшего
  по email элемента (лениво принимает единственную строку). `{}` если не найден.

### [app/xui/links.py](./app/xui/links.py)
Билдеры ссылок и QR.

- `build_subscription_url(sub_id) -> str` — джойнит
  `settings.XUI_SUB_BASE_URL` с `sub_id`, нормализуя слеши.
- `_find_client(inbound, client_uuid) -> dict` — поиск клиента в
  `inbound.settings.clients` по uuid.
- `_stream_params(stream) -> dict[str,str]` — извлекает query-параметры
  vless URI из `streamSettings`:
  - всегда: `type` (network), `security`.
  - `tcp` → `headerType`/`path`/`host` (из header.request).
  - `ws`  → `path`/`host`.
  - `grpc` → `serviceName`/`mode`.
  - `http|h2` → `path`/`host`.
  - `kcp` → `headerType`/`seed`.
  - `quic` → `quicSecurity`/`key`/`headerType`.
  - `tls` → `sni`/`alpn`/`fp`.
  - `reality` → `pbk`/`fp`/`sni`/`sid`/`spx`.
- `build_vless_link(inbound, client_uuid, email) -> str` — собирает
  `vless://uuid@HOST:port?<query>#<email-quoted>`; HOST из
  `settings.XUI_SERVER_HOST`, port из `inbound.port`; `flow` — из
  client object (`settings.clients[i].flow`); fragment URL-encoded.
- `make_qr_png(text) -> bytes` — `qrcode.make(text)` + сохранение
  в `BytesIO` как PNG; возвращает байты (magic `89 50 4E 47`),
  готовые для aiogram `send_photo`.

### [app/scheduler.py](./app/scheduler.py)
Фоновые задачи бота на `APScheduler` (`AsyncIOScheduler` + `CronTrigger`).

- Литерал `ReminderKind = Literal["3d","1d","0d"]`.
- Константа-словарь `_REMINDER_TEXTS: dict[ReminderKind, str]` — тексты
  предупреждений «истекает через 3 дня / завтра / сегодня».
- Константа `_EXPIRED_TEXT` — финальное сообщение «подписка истекла».
- Helper `_parse_iso(value) -> datetime` — парсит хранящиеся в БД
  ISO-строки (`YYYY-MM-DD HH:MM:SS` или с `+00:00`) в aware-datetime UTC.
- Helper `_days_left(expires_at, now) -> int` — целое число суток до
  дедлайна (отрицательное при просрочке; floor через `timedelta.days`).
- Helper `_kind_for_days_left(days_left) -> ReminderKind | None` —
  маппинг: `[3,4)` → `3d`, `[1,2)` → `1d`, `0` → `0d`, иначе `None`.
- Helper `_safe_send(bot, tg_id, text)` — `bot.send_message` с глушением
  `TelegramAPIError` (юзер мог заблокировать бота).

- `async def expire_check_job(bot)` — раз в час: для каждой подписки из
  `subs_repo.list_expired_active(now)` вызывает
  `xui.update_client(enable=False)`, ставит `set_status(sub.id, 'expired')`,
  через `try_mark_notification_sent('expired')` гарантирует однократную
  отправку финального уведомления юзеру (`_EXPIRED_TEXT`). Все ошибки
  (xui / БД / Telegram) логируются и не валят цикл.
- `async def reminders_job(bot)` — раз в сутки: `list_expiring_in(days=3)`,
  для каждой подписки вычисляет `_days_left`, маппит в `kind`, через
  `try_mark_notification_sent(sub_id, kind)` дедуплицирует и шлёт
  соответствующий `_REMINDER_TEXTS[kind]`.
- `async def traffic_snapshot_job(bot)` — раз в 6 часов: для каждой
  `subs_repo.list_active(conn)` вызывает `xui.get_client_traffics(email)`,
  затем `subs_repo.add_traffic_snapshot(sub.id, up, down)`. Пустой ответ
  (клиент в панели не найден) пропускается. `bot` принимается ради единого
  callable-signature, не используется.
- Helper `_wrap(job, bot, name)` — closure-обёртка, которая ловит
  любые исключения job-а и логирует через loguru (чтобы один упавший
  job не остановил остальные).
- `def setup_scheduler(bot) -> AsyncIOScheduler` — создаёт scheduler
  с `timezone='UTC'` и регистрирует три job-а:
  - `expire_check`: `CronTrigger(minute=0)` каждый час; `coalesce=True`,
    `misfire_grace_time=30*60`, `max_instances=1`.
  - `reminders`: `CronTrigger(hour=10, minute=0)` раз в сутки;
    `coalesce=True`, `misfire_grace_time=6*60*60`, `max_instances=1`.
  - `traffic_snapshots`: `CronTrigger(hour='0,6,12,18', minute=5)`;
    `coalesce=True`, `misfire_grace_time=60*60`, `max_instances=1`.
  Не запускает scheduler — старт делает caller (`app/main.py`).

## Каталог `scripts/`

### [scripts/\_\_init\_\_.py](./scripts/__init__.py)
Маркер пакета standalone-скриптов (smoke-тесты, ops-хелперы).
Не часть runtime-приложения, но в том же venv.

### [scripts/xui_smoke.py](./scripts/xui_smoke.py)
Standalone smoke-тест 3x-ui REST-клиента.

- `_short(obj, limit=400) -> str` — компактный JSON для логов.
- `async def run(keep: bool) -> int` — sequence: `setup_logging('INFO')` →
  `XuiClient()` → `login` → `list_inbounds` → `get_inbound(XUI_INBOUND_ID)` →
  `add_client` (test uuid+email, 10 мин expiry) → `get_client_traffics` →
  `del_client` (если не `--keep`). Каждый шаг ловит `XuiError` и
  возвращает собственный exit-code (2-6). В `finally` всегда
  `client.close()`.
- `def main() -> int` — argparse (`--keep`), `asyncio.run(run(...))`.
- Запуск: `python -m scripts.xui_smoke` или `python scripts/xui_smoke.py`.

## Пакет `app/services/`

Бизнес-логика, которая оркестрирует репозитории и `XuiClient`. Сервисы
не знают про `aiogram` (кроме `billing.send_invoice`, который пишет
непосредственно в Telegram) — это позволяет тестировать их в изоляции.

### [app/services/\_\_init\_\_.py](./app/services/__init__.py)
Маркер пакета. Документирует подмодули `promos`, `billing`, `subscriptions`.

### [app/services/promos.py](./app/services/promos.py)
Бизнес-логика промокодов.

- Dataclass `PromoValidation(is_valid, error, promo)` — результат
  валидации (error — RU-сообщение, безопасно отдавать юзеру).
- Dataclass `DiscountResult(final_price, extra_days)` — выход
  `compute_discount`.
- `_utcnow_iso() -> str`, `_already_redeemed_by(conn, promo_id, user_id) -> bool`
  (политика one-per-user через `promo_redemptions`).
- `async def validate(conn, code, user_id, plan) -> PromoValidation` —
  trim+непустой; `get_by_code` (case-insensitive); `expires_at>now`;
  `used_count<max_uses` (или `max_uses=0`); пользователь ещё не
  активировал. Если `plan=None` — допускает любой тип (caller проверит).
- `def compute_discount(plan, promo) -> DiscountResult` — pure:
  `None` → `(price, 0)`; `percent` → `ceil(price*(100-value)/100)`;
  `flat_stars` → `max(0, price-value)`; `free_days` → `(price, value)`.
- `async def apply(conn, promo_id, user_id, subscription_id) -> bool` —
  тонкая обёртка над `promos_repo.try_redeem`.

### [app/services/billing.py](./app/services/billing.py)
Расчёт цены и подготовка Stars-invoice.

- Константы `_STARS_MIN = 1` (TG требует amount>=1), `_PAYLOAD_BYTE_LIMIT = 128`.
- Dataclass `InvoicePrice(stars, raw_discount, extra_days)`.
- `def calc_price(plan, promo) -> InvoicePrice` — обёртка над
  `promos.compute_discount` + `max(_STARS_MIN, final_price)`.
- `def build_invoice_payload(plan_id, promo_id, inbound_id, *, sub_id: int = 0) -> str` —
  компактный JSON `{"p":..., "r": ... | null, "i": ..., "s": ...}` с
  короткими ключами (<128 байт даже для крупных id); raise `ValueError`
  если payload не вмещается. Ключ `"s"` (sub_id-to-extend) **опускается
  целиком** при `sub_id == 0` (свежая покупка), чтобы не раздувать
  payload в hot-path-е «новая подписка»; legacy-payloads без `"s"`
  парсятся как `sub_id=0`.
- `def parse_invoice_payload(payload) -> tuple[int, int | None, int, int]` —
  обратная функция, возвращает 4-tuple
  `(plan_id, promo_id, inbound_id, sub_id)`. Принимает как новые ключи
  (`p`/`r`/`i`/`s`), так и legacy (`plan_id`/`promo_id` без `i`/`s`);
  при отсутствии `i` — fallback на `settings.XUI_INBOUND_ID` с
  WARNING-логом; при отсутствии `s` — `sub_id=0`. `ValueError` на
  малформность; `promo_id=0` нормализуется в `None`. `sub_id=0`
  означает «новая подписка» для handler-а; `sub_id>0` означает
  «продлить именно эту подписку».
- Helpers `_invoice_title(plan)` (формат `VPN · <title>`),
  `_invoice_description(plan, price, promo, *, sub_id=0)` — упоминает
  бонусные дни и тип скидки; при `sub_id > 0` заголовок описания
  меняется на «Продление подписки #N на <days> дн.» (юзер видит в TG
  invoice-окне явно, что это extend).
- `async def send_invoice(bot, chat_id, plan, promo, *, inbound_id, sub_id: int = 0) -> Message` —
  `bot.send_invoice(currency="XTR", provider_token="",
  prices=[LabeledPrice(label=plan.title, amount=stars)],
  payload=build_invoice_payload(..., inbound_id=..., sub_id=sub_id))`.
  `inbound_id` обязательный kwarg; `sub_id` опциональный (0 =
  новая, >0 = extend конкретной подписки). Оба значения
  прокидываются в payload, чтобы пост-оплатный provisioning знал
  целевой inbound и (опционально) подписку-получатель.

### [app/services/inbounds.py](./app/services/inbounds.py)
Кэшированный список доступных 3x-ui inbound-ов для user/admin флоу.

- Константа `_CACHE_TTL_SEC = 30.0` (баланс между свежестью админских
  правок и нагрузкой на панель).
- Dataclass `InboundOption(id:int, remark:str, port:int, enabled:bool)`
  (`frozen`, `slots`) — проекция inbound-а с полями, нужными
  клавиатурам и хендлерам.
- Модульный TTL-кэш: переменные `_cache: list[InboundOption] | None`,
  `_ts: float` (time.monotonic), `_lock: asyncio.Lock` для защиты от
  thundering-herd на холодном кэше.
- `async def list_user_inbounds(xui) -> list[InboundOption]` — при
  кэш-хите возвращает без сетевого вызова. При промахе под `_lock`
  делает double-check freshness, вызывает
  `app.xui.inbounds.list_inbounds`, фильтрует `enable=True`, кладёт в
  `_cache`. Малформированные inbound-ы (без `id`/`enable`) логируются и
  пропускаются. При исключении от 3x-ui кэш НЕ обновляется (исключение
  пробрасывается).
- `def clear_cache()` — сброс кэша для тестов и админ-действий,
  меняющих состояние inbound-ов на панели.

### [app/services/subscriptions.py](./app/services/subscriptions.py)
Единая точка работы с подписками: xui-first, db-after.

- Helpers `_expiry_ms(dt) -> int` (UTC datetime → ms since epoch для
  3x-ui `expiryTime`); `_parse_iso(value) -> datetime` (обратное
  преобразование строки из `expires_at`); `_bonus_days_from_promo(promo)`
  (0 для всех типов кроме `free_days`); `_make_sub_id()` (делегирует в
  `app.xui.clients`).
- `async def create_or_extend(conn, xui, user, plan, promo, *, inbound_id, extend_sub_id: int | None = None) -> Subscription` —
  `inbound_id` обязательный kwarg, `extend_sub_id` — explicit-режим
  выбора ветки (см. `_provision`). Считает
  `delta = plan.days + bonus_days(promo)`, делегирует в `_provision`
  с `total_gb=int(plan.traffic_gb)`, переданным `inbound_id` и
  `extend_sub_id`. При `extend_sub_id=None` — всегда создаёт **новую**
  подписку (даже если у пользователя уже есть активные); при
  `extend_sub_id=int` — продлевает конкретную с проверкой ownership и
  `status='active'`.
- `async def activate_free_days(conn, xui, user, promo, *, inbound_id, extend_sub_id: int | None = None) -> Subscription` —
  `inbound_id` обязательный kwarg, `extend_sub_id` — то же поведение,
  что в `create_or_extend`. Для standalone-флоу free_days-промокода.
  `ValueError` если `promo.type != "free_days"`. `delta = promo.value`,
  `plan_id=None`, `total_gb=0` (квота не задаётся).
- `async def _provision(*, conn, xui, user, delta_days, plan_id, total_gb=0, inbound_id, extend_sub_id: int | None) -> Subscription` —
  **explicit branch selection** по `extend_sub_id`:
  - `extend_sub_id is None` → **всегда** свежее provisioning: новый
    uuid + email + sub_id, `add_client(inbound_id=<переданный>, ...,
    total_gb=total_gb)` (xui-first), затем
    `subs_repo.create(xui_inbound_id=<переданный>, xui_sub_id=...)`.
    Наличие других активных подписок у того же юзера не влияет — это
    ответственность caller-а (UI показывает экран «Продлить / Новая»).
  - `extend_sub_id is int` → `subs_repo.get(conn, extend_sub_id)`,
    проверка `existing.user_id == user.id` и `existing.status ==
    'active'`. При невыполнении любого из условий — `ValueError`
    (caller трактует как «подписка недоступна»). На extend
    `update_client(expiryTime=..., enable=True)` (важно: `totalGB`
    намеренно НЕ передаётся, чтобы не сбрасывать накопленную квоту
    при продлении) + `subs_repo.extend`. `inbound_id` при extend
    ИГНОРИРУЕТСЯ — используется `existing.xui_inbound_id`; mismatch
    логируется WARNING-ом с `subscription_id`, существующим и
    запрошенным inbound_id (чтобы не «прыгать» между inbound-ами
    в рамках одной подписки).
  Guard: если строка active, но `expires_at < now`, новая экспирация
  отсчитывается от `now`, а не от истёкшей точки.
  `total_gb` применяется ТОЛЬКО при свежем provisioning.
- `async def revoke(xui, sub) -> None` — `update_client(enable=False)`
  (best-effort, ловит исключения и логирует) + `subs_repo.set_status(sub.id, "revoked")`.

**Бизнес-логика multi-subscription:** пользователь может владеть N
активными подписками одновременно (каждая = свой xui-client на
конкретном inbound, свой UUID, свой sub URL). Выбор «продлить
конкретную #N vs создать новую» делается явно через
`extend_sub_id`. Старая логика «auto-extend single active»
полностью убрана из service-слоя — service просто исполняет
явное решение caller-а.

### [app/services/stats.py](./app/services/stats.py)
Агрегаты для админского экрана «Статистика». Все функции `async`,
принимают `aiosqlite.Connection` (DI). Тяжёлые вычисления сделаны на
стороне SQL.

- Helpers `_utcnow() -> datetime`, `_iso(value) -> str`.
- `async def revenue_stars(conn, period: timedelta) -> int` — сумма
  Stars-дохода (`status='paid'`) за окно `[now-period, now]`,
  делегирует в `payments_repo.total_stars_period`.
- `async def total_stars_period(conn, date_from, date_to) -> int` —
  pass-through к репо для явных границ периода.
- `async def active_subscriptions_count(conn) -> int` — `COUNT(*)` по
  `subscriptions` с `status='active' AND expires_at > now`.
- `async def expiring_in(conn, days) -> list[Subscription]` — обёртка
  над `subs_repo.list_expiring_in`.
- `async def expiring_in_days(conn, days)` — алиас `expiring_in`,
  имена совпадают со словарём плана.
- `async def top_promos(conn, limit=5) -> list[Promo]` — `SELECT *
  FROM promos ORDER BY used_count DESC, id DESC LIMIT ?`. Включает
  деактивированные/истёкшие.
- `async def users_count(conn) -> int` — `COUNT(*)` по `users`.
- `async def users_count_total(conn)` — алиас `users_count`.
- `async def payments_count_period(conn, date_from, date_to) -> int` —
  `COUNT(*)` по `payments` со `status='paid'` в `[date_from, date_to]`.

### [app/services/broadcast.py](./app/services/broadcast.py)
Веерная рассылка одного поста всей аудитории (админская «Рассылка»).

- `@dataclass(frozen=True) BroadcastResult(total, sent, blocked, failed)`
  — счётчики результата; инвариант `sent + blocked + failed == total`.
- `async def broadcast_message(bot, *, from_chat_id, message_id, tg_ids,
  throttle=0.05) -> BroadcastResult` — копирует сообщение
  `(from_chat_id, message_id)` каждому получателю через
  `bot.copy_message` (доставка verbatim, без «Forwarded from», любой тип
  контента). Устойчивость: `TelegramForbiddenError` → бакет `blocked`
  (юзер заблокировал/удалил чат), любая другая ошибка → `failed`, цикл
  никогда не падает. `TelegramRetryAfter` (flood control) обрабатывается
  сном на `exc.retry_after` и одной повторной попыткой для этого
  получателя. Между отправками — `asyncio.sleep(throttle)` как защита от
  лимита ~30 msg/s (в тестах `throttle=0`).

## Пакет `app/handlers/user/`

Пользовательский флоу: меню, помощь, покупка, активация промокода.
Без gate-middleware — доступен всем.

### [app/handlers/user/\_\_init\_\_.py](./app/handlers/user/__init__.py)
Агрегатор `user_router`. Подключает в порядке
`menu → my_subscription → buy → promo → help`.

### [app/handlers/user/menu.py](./app/handlers/user/menu.py)
Главное меню пользователя.

- `router = Router(name="user_menu")`.
- `_has_active_subscription(user_db_id) -> bool` — обёртка над
  `subs_repo.get_active_for_user`.
- `_send_main_menu(message, user, edit=bool)` — единая точка рендера
  (`edit_text` или `answer`).
- `cmd_menu` (`Command("menu")`) — показать меню в новом сообщении.
- `cb_menu` (`UserCB area=menu`) — edit обратно в главное меню (универсальная
  «Назад»).
- `cb_cancel` (`UserCB area=cancel`) — `state.clear()` + возврат в меню.

### [app/handlers/user/my_subscription.py](./app/handlers/user/my_subscription.py)
Экран «Моя подписка» — список **всех** подписок пользователя со
статусом, днями до истечения, live-трафиком из 3x-ui, и набором
per-sub action-кнопок. Поддерживает повторную выдачу
vless/QR/Subscription URL.

- `router = Router(name="user_my_subscription")`.
- Константа `_MAX_VISIBLE_SUBS = 5` — Telegram-friendly cap на число
  отображаемых карточек.
- Внутренние helpers:
  - `_format_bytes(value) -> str` — human-readable байты (`1.0 KB`,
    `5.0 GB`) с бинарным шагом 1024. Используется для отображения
    счётчиков `up`/`down`.
  - `_parse_iso(value)` / `_days_delta(expires_at)` — парс ISO-8601
    в UTC-aware `datetime`, разница в днях с округлением вниз (поэтому
    «истекает через 0 дн.» → «сегодня», «истекла 6 часов назад» →
    «истекла 1 дн. назад»).
  - `_is_active(sub)` — `status='active'` И `expires_at > now()`.
  - `_format_days_line` / `_format_status_line` — строки карточки.
  - `_fetch_traffics(sub) -> (up, down, ok)` — обёртка над
    `xui.clients.get_client_traffics(email)`; ловит `XuiError` и любые
    другие исключения, возвращая `ok=False` чтобы экран никогда не
    падал из-за недоступной панели. Также возвращает `ok=False` если
    панель ответила `obj=null` (клиент удалён вручную).
  - `_format_sub_card(sub, traffic)` — HTML-карточка из 5 строк
    (заголовок, статус, дата, дни, трафик); при `ok=False` — текст
    «Трафик: не удалось получить (панель недоступна)».
  - `_sort_subs(subs) -> list[Subscription]` — сортировка для вывода:
    активные подписки сверху (по `expires_at` DESC, тай-брейк `id`
    DESC), затем неактивные (`expired` / `revoked` / `active` с
    `expires_at` в прошлом) — по `created_at` DESC. Порядок
    зафиксирован тестами.
  - `_build_subs_keyboard(visible) -> InlineKeyboardBuilder` —
    собирает inline-клавиатуру: сверху одна строка
    «🆕 Купить новую подписку» (`BuyCB(action='new')`); затем по
    одной строке на каждую видимую подписку с парой кнопок
    «🔑 Ключи #N» (`SubCB(action='keys', sub_id=N)`) и (только для
    активных) «🛒 Продлить #N» (`BuyCB(action='extend', sub_id=N)`);
    внизу «◀ В меню» (`UserCB(area='menu')`). Кнопка «Продлить»
    скрывается для неактивных, так как
    `buy.cb_pick_action_extend` отклоняет non-active подписки.
  - `_btn(text, cb)` — мелкий хелпер для построения
    `InlineKeyboardButton` из `CallbackData`-фабрики (`cb.pack()`).
  - `_pluralize_subs(n) -> str` — русские формы для слова «подписка»
    (1 / 2-4 / 5+) — используется в footer-строке «… и ещё N
    подписк{а|и|ок}».
  - `_no_subscription_kb()` — кнопки «Купить подписку»
    (`BuyCB(action='open')`) + «В меню».
- Хендлеры:
  - `cb_open_my` (`UserCB area=my`) — загружает все подписки через
    `subs_repo.list_for_user`; при отсутствии — «no subscription»
    экран с `_no_subscription_kb`. Иначе сортирует через `_sort_subs`,
    берёт первые `_MAX_VISIBLE_SUBS` и рендерит карточки через
    `_format_sub_card`, разделяя их линией `━━━━━━━━━━━━━━━`. При
    наличии скрытых подписок добавляется footer «… и ещё N
    подписк{а|и|ок}». Клавиатура — `_build_subs_keyboard(visible)`.
  - `cb_resend_keys` (`SubCB action=keys`) — повторно отдаёт ключи
    через `_keys.deliver_keys`. Гарантии: проверка `sub.user_id ==
    user.id` (один и тот же текст «Подписка не найдена» для not-found
    и not-yours — без утечки информации); header адаптируется к
    статусу (для истёкших — «для копирования»). Любую `XuiError`
    ловит и отвечает «панель временно недоступна».

### [app/handlers/user/help.py](./app/handlers/user/help.py)
Инструкция по подключению.

- `router = Router(name="user_help")`.
- Константа `_HELP_TEXT` — три рекомендуемых клиента (v2rayNG для Android,
  Streisand для iOS, Hiddify для desktop) и три способа импорта
  (vless URI, Subscription URL, QR).
- `cb_help` (`UserCB area=help`) — `edit_text(_HELP_TEXT, back_to_menu_kb)`.

### [app/handlers/user/_keys.py](./app/handlers/user/_keys.py)
Helper для выдачи ключей юзеру. Используется и в `buy.py`, и в `promo.py`.

- `async def deliver_keys(bot, xui, chat_id, sub, *, header) -> None` —
  отправляет три сообщения: (1) summary с expires_at и vless URI в
  `<code>`; (2) QR PNG через `bot.send_photo` (`BufferedInputFile` из
  `make_qr_png`); (3) Subscription URL + клавиатура с URL-кнопкой
  `Subscription URL` (vless:// не идёт в URL-кнопке — Telegram такие
  схемы не принимает) + `subscription_kb(sub.id)`. При `XuiError` на
  `get_inbound` логирует и продолжает без vless URI; QR строится по
  sub_url.

### [app/handlers/user/buy.py](./app/handlers/user/buy.py)
Полный платёжный флоу за Stars с выбором inbound.

- `router = Router(name="user_buy")`.
- Helpers
  - `_format_confirm(plan, promo, inbound_remark=None, has_active_sub=False)` —
    HTML-карточка с итоговой ценой; выводит строку «Подключение: …»
    при наличии `inbound_remark`; добавляет ⚠️-предупреждение «продление
    останется на текущем подключении» при `has_active_sub=True`.
  - `_has_active_sub(conn, user_id)` — `bool` поверх
    `subs_repo.get_active_for_user`.
  - `_remark_for(options, inbound_id)` — резолвит remark из FSM-options
    (list[InboundOption] или list[dict] после JSON round-trip).
  - `_options_to_jsonable(options)` / `_jsonable_to_options(items)` —
    сериализация `InboundOption` в/из MemoryStorage JSON.
  - `_fetch_plan(conn, plan_id)` / `_fetch_promo(conn, promo_id)` —
    репо-обёртки.
  - `_plan_is_buyable(plan)` / `_promo_is_usable(promo)` — read-only
    проверки для pre_checkout (без one-per-user, т.к. её гарантирует
    `try_redeem`).
- UI-колбеки (state-driven):
  - `cb_open` (`BuyCB action=open`) — entry-point из главного меню.
    Загружает `subs_repo.list_active_for_user(user.id)`. При наличии
    активных подписок переходит в `BuyFlow.choosing_action`, сохраняет
    в FSM `active_sub_ids` и `inbound_remarks` (мэппинг
    `{inbound_id: remark}` из `list_user_inbounds`), рендерит
    `buy_action_kb(active, remarks)`. При отсутствии активных —
    стандартный путь: `BuyFlow.choosing_plan` + `plans_kb(list_active())`.
    Если нет тарифов — соответствующее сообщение.
  - `cb_pick_action_extend` (state-filter `BuyFlow.choosing_action` +
    `BuyCB action=extend`) — юзер выбрал «🔄 Продлить #N». Валидирует
    `sub_id>0` и ownership (`subs_repo.get(sub_id)` с `user_id` совпадает,
    `status='active'` — анти-подделка callback); сохраняет
    `sub_id` в FSM, делегирует в `_send_plan_list` (переход в
    `BuyFlow.choosing_plan`). Также служит entry-point для прямой
    кнопки «🛒 Продлить #N» с `my_subscription`.
  - `cb_pick_action_new` (state-filter `BuyFlow.choosing_action` +
    `BuyCB action=new`) — юзер выбрал «🆕 Новая подписка». Очищает
    `sub_id=0` в FSM, делегирует в `_send_plan_list`. Также служит
    entry-point для прямой кнопки «🆕 Купить новую подписку» с
    `my_subscription`.
  - `_send_plan_list(callback, state)` — общий helper: грузит
    `plans_repo.list_active()`, выставляет `BuyFlow.choosing_plan`,
    рендерит `plans_kb`.
  - `cb_pick_plan` (`action=plan`) — загружает
    `plans_repo.get_inbounds(plan_id)`. **Extend-ветка:** если в FSM
    `sub_id > 0`, шаг `choosing_inbound` **пропускается** независимо от
    количества inbound-ов плана — inbound наследуется от существующей
    подписки (`subs_repo.get(sub_id).xui_inbound_id`); FSM получает
    `inbound_id=<existing>`, состояние → `BuyFlow.confirming`,
    `confirm_kb(plan_id, promo_id, inbound_id, sub_id=sub_id)`,
    `_format_confirm` использует `inbound_remark` из FSM-снапшота.
    **New-ветка** (`sub_id == 0`): если `len == 1` → резолвит remark
    через `list_user_inbounds`, FSM(`inbound_id`), `BuyFlow.confirming`;
    если `len > 1` → `list_user_inbounds` + фильтр по allow-list,
    FSM(`inbound_options`), `BuyFlow.choosing_inbound`, рендер
    `inbound_select_kb`; пустой список / XuiError — answer alert.
    Сохраняет уже привязанный `promo_id`, если он валиден.
  - `cb_pick_inbound` (`InboundCB action=pick` в
    `BuyFlow.choosing_inbound`) — валидирует `inbound_id ∈
    get_inbounds(plan_id)`; на успехе сохраняет в FSM, переходит в
    `confirming`, рендерит `confirm_kb(plan_id, promo_id, inbound_id)`.
  - `cb_pick_inbound_back` (`InboundCB action=back` в
    `BuyFlow.choosing_inbound`) — возврат к списку тарифов
    (`BuyFlow.choosing_plan`).
  - `cb_apply_promo` (`action=apply_promo`) — сохраняет `plan_id` и
    `inbound_id` (из callback / FSM), `BuyFlow.entering_promo` +
    подсказка ввести код.
  - `msg_promo_code` (handler в `BuyFlow.entering_promo`) — валидирует
    через `promos_service.validate(plan=plan)`; на ошибке остаётся в
    стейте; на успехе сохраняет `promo_id`, резолвит remark inbound и
    `has_active_sub`, возвращает в `confirming`.
  - `cb_confirm` (`action=confirm`) — резолвит `inbound_id` и
    `sub_id` из callback_data (fallback на FSM), валидирует `plan`
    активен, `promo` usable. **Extend-ветка** (`sub_id > 0`):
    повторно проверяет ownership и `status='active'` подписки (защита
    от подделки callback) и **пропускает** проверку `inbound_id ∈
    get_inbounds(plan_id)` — extend всегда переиспользует существующий
    inbound, даже если он больше не разрешён планом; иначе
    `billing.send_invoice(..., inbound_id=..., sub_id=sub_id)` и
    `state.clear()`. **New-ветка** (`sub_id == 0`): валидирует
    `inbound_id ∈ get_inbounds(plan_id)`; при mismatch возвращает в
    `choosing_inbound` со свежим `inbound_select_kb`; иначе
    `billing.send_invoice(..., inbound_id=..., sub_id=0)` и
    `state.clear()`.
- Stateless-обработчики платежа:
  - `on_pre_checkout` (`pre_checkout_query`) — `parse_invoice_payload`
    возвращает 4-tuple `(plan_id, promo_id, inbound_id, sub_id)`;
    read-only проверки plan/promo; при `sub_id == 0` дополнительно
    `inbound_id ∈ get_inbounds(plan_id)`; при `sub_id > 0` проверяется
    ownership + active-status подписки (`inbound_id` не валидируется,
    т.к. extend всегда наследует существующий); answer `ok=True/False`.
  - `on_successful_payment` (`F.successful_payment`) — идемпотентен по
    `payments_repo.get_by_charge_id`; парсит 4-tuple payload; логирует
    WARNING для legacy-payload без `i` (fallback на
    `settings.XUI_INBOUND_ID`); refetch plan/promo;
    `subs_service.create_or_extend(..., inbound_id=..., extend_sub_id=<sub_id or None>)`
    (xui-first; на `XuiError` фиксирует платёж без подписки и
    уведомляет юзера; на `ValueError` от `_provision` — подписка
    больше не подходит для extend — пишет в логи и уведомляет);
    `payments_repo.create` (`IntegrityError` на duplicate
    игнорируется; `subscription_id` ссылается на (новую или
    extended) подписку); `promos.apply` (best-effort);
    `deliver_keys` с заголовком, отражающим extend vs new.

### [app/handlers/user/promo.py](./app/handlers/user/promo.py)
Standalone-активация промокода (без оплаты, для `free_days`) с
опциональным action-экраном «продлить vs новая» и выбором inbound.

- `router = Router(name="user_promo")`.
- Хелперы: `_options_to_jsonable` / `_jsonable_to_options` —
  сериализация `InboundOption` для FSM storage (зеркало хелперов в
  `buy.py`).
- `_activate_promo_for_sub(callback, state, bot, user, promo_id,
  extend_sub_id: int | None, inbound_id)` — общий tail для extend-ветки
  action-экрана (и любых будущих путей, которым нужно активировать
  free_days промо против конкретного `extend_sub_id` без шага выбора
  inbound). Re-валидирует промо, вызывает
  `subs_service.activate_free_days(extend_sub_id=...)`, best-effort
  `promos_service.apply`, `deliver_keys` с заголовком
  «применён к подписке #N» (extend) или «активирован» (new), очищает FSM.
- `cb_open` (`PromoActCB action=open`) — `state.set_state(PromoActivate.waiting_code)`
  + `cancel_kb`.
- `msg_code` (handler в `PromoActivate.waiting_code`) —
  `promos_service.validate(plan=None)`; если `promo.type != "free_days"`
  → подсказка использовать buy flow и `state.clear()`; на ошибке
  остаётся в стейте; для `free_days` вызывает
  `list_user_inbounds(xui)` (на `XuiError` или пустом списке — извинение
  и `state.clear()`). Затем грузит `subs_repo.list_active_for_user(user.id)`:
  если есть активные подписки → стейт `PromoActivate.choosing_action`,
  сохраняет `promo_id` + `inbound_options` (jsonable), рендерит
  `promo_action_kb(active, remarks)`; если активных нет — текущая ветка
  `choosing_inbound` + `inbound_select_kb`.
- `cb_pick_action_extend_promo` (state-filter `PromoActivate.choosing_action`
  + `PromoActCB action=extend`) — юзер выбрал «🔄 Продлить #N».
  Проверка `sub_id>0`, наличия `promo_id` в FSM, загрузка sub через
  `subs_repo.get` с проверкой ownership (`user_id` совпадает) +
  `status='active'` (анти-подделка callback), затем
  `_activate_promo_for_sub(extend_sub_id=sub.id,
  inbound_id=sub.xui_inbound_id)` — inbound наследуется от существующей
  подписки, allow-list НЕ проверяется (sub может жить на inbound, который
  больше не привязан ни к одному тарифу).
- `cb_pick_action_new_promo` (state-filter `PromoActivate.choosing_action`
  + `PromoActCB action=new`) — юзер выбрал «🆕 Новая подписка».
  Переиспользует `inbound_options` из FSM (положенный `msg_code` перед
  показом action-экрана); если по какой-то причине пусто — фоллбек
  `list_user_inbounds` с защитными ветками `XuiError`/empty. Переходит
  в `PromoActivate.choosing_inbound`, рендерит `inbound_select_kb(0,
  options, promo_id=promo_id)`. Дальше работает существующий
  `cb_pick_inbound_for_promo` с `extend_sub_id=None`.
- `cb_pick_inbound_for_promo` (state-filter `PromoActivate.choosing_inbound`
  + `InboundCB action=pick`) — повторно валидирует промо через
  `promos_service.validate` (анти-гонка), сверяет `inbound_id` со
  снэпшотом `inbound_options` в FSM (защита от подделки callback),
  вызывает `subs_service.activate_free_days(conn, xui, user, promo,
  inbound_id=inbound_id, extend_sub_id=None)` (xui-first; при `XuiError`
  промо НЕ редимится); затем `promos_service.apply` (best-effort),
  `deliver_keys`, `state.clear()`.
- `cb_back_inbound_for_promo` (state-filter `PromoActivate.choosing_inbound`
  + `InboundCB action=back`) — возврат в `PromoActivate.waiting_code`,
  сброс FSM-полей `promo_id` и `inbound_options`.
- Разделение с buy-флоу: фабрика `InboundCB` общая, но хендлеры
  фильтруются по своему FSM-стейту (`BuyFlow.choosing_inbound` vs
  `PromoActivate.choosing_inbound`), так что не конфликтуют. Также
  `PromoActCB extend`/`new` фильтруются по
  `PromoActivate.choosing_action`, что не конфликтует с `BuyCB
  extend`/`new` под `BuyFlow.choosing_action`.

## Пакет `app/keyboards/` — пользовательские клавиатуры

### [app/keyboards/user.py](./app/keyboards/user.py)
Inline-клавиатуры юзерского флоу.

**CallbackData-фабрики:**
- `UserCB(prefix="u", area)` — area ∈ menu/help/my/cancel.
- `BuyCB(prefix="ub", action, plan_id=0, promo_id=0, inbound_id=0, sub_id=0)` —
  action ∈ open/plan/apply_promo/confirm/cancel/extend/new. Поле
  `inbound_id` пробрасывается через шаги после выбора inbound (`0` =
  шаг был автоматически пропущен из-за единственного inbound в
  allow-list). Поле `sub_id` (>0) несёт id подписки, которую надо
  продлить (extend-ветка action-экрана и кнопка «🛒 Продлить #N» с
  `my_subscription`); `0` = новая подписка / n/a. Packed payload:
  `ub:<action>:<plan_id>:<promo_id>:<inbound_id>:<sub_id>`.
- `InboundCB(prefix="inb", action, plan_id=0, promo_id=0, inbound_id=0)` —
  action ∈ pick/back. Используется и в buy-флоу (`plan_id>0`), и в
  free-days promo-флоу (`plan_id=0`, `promo_id>0`); хендлер маршрутизирует
  по тому, какой id ненулевой.
- `SubCB(prefix="us", action, sub_id=0)` — action ∈ keys/back.
- `PromoActCB(prefix="up", action, inbound_id=0, sub_id=0)` —
  action ∈ open/extend/new/cancel. Поле `sub_id>0` несёт id подписки,
  которую нужно продлить через free_days промо (выбор на
  `promo_action_kb`); `0` = новая подписка / n/a. Packed payload:
  `up:<action>:<inbound_id>:<sub_id>` (например `up:open:0:0`,
  `up:extend:0:42`).

**Функции:**
- `user_main_menu(has_subscription) -> InlineKeyboardMarkup` —
  «Моя подписка» / «Купить» / «Активировать промокод» / «Помощь».
  Порядок первых двух меняется по флагу.
- `back_to_menu_kb()` — одна кнопка «◀ В меню».
- `cancel_kb()` — одна кнопка «✖ Отмена» (cancel-таргет — `UserCB(area=cancel)`).
- `plans_kb(plans)` — один пункт на тариф (`title · Nд · M⭐`) + «В меню».
- `inbound_select_kb(plan_id, options, promo_id=0)` — single-select
  inbounds: одна кнопка на `InboundOption` с текстом
  `<remark> (port <port>)`, callback
  `InboundCB(action="pick", plan_id, promo_id, inbound_id=option.id)`.
  Внизу «◀ Назад» (`InboundCB(action="back", plan_id, promo_id)`).
- `confirm_kb(plan_id, promo_id=0, inbound_id=0, sub_id=0)` — «Оплатить»
  (`BuyCB(action="confirm", plan_id, promo_id, inbound_id, sub_id)`) /
  «Применить промокод» (скрыта если `promo_id≠0`; пробрасывает
  `inbound_id` и `sub_id`) / «Отмена». `sub_id>0` означает, что
  invoice — это продление конкретной подписки (extend-ветка):
  значение прокидывается в `billing.send_invoice(sub_id=...)`, далее
  в payload, далее в `subs_service.create_or_extend(extend_sub_id=...)`.
- `buy_action_kb(active_subs, inbound_remarks) -> InlineKeyboardMarkup` —
  action-экран buy-флоу, когда у пользователя есть одна или несколько
  активных подписок. По строке на каждую active sub: «🔄 Продлить
  #<sub_id> · <remark>» (`BuyCB(action="extend", sub_id=<id>)`),
  затем «🆕 Новая подписка» (`BuyCB(action="new")`) и «◀ Отмена»
  (`UserCB(area="cancel")`). `inbound_remarks` — `{inbound_id: remark}`
  мэппинг из кэшированного panel-листа; fallback при отсутствии —
  `#<inbound_id>`. Зеркало `promo_action_kb`, но фабрика — `BuyCB`.
- `promo_action_kb(active_subs, inbound_remarks)` — action-экран для
  free_days промокода, когда у пользователя есть активные подписки.
  По строке на каждую active sub: «🔄 Продлить #<sub_id> · <remark>»
  (`PromoActCB(action="extend", sub_id=<id>)`), затем «🆕 Новая подписка»
  (`PromoActCB(action="new")`) и «◀ Отмена» (`UserCB(area="cancel")`).
  `inbound_remarks` — `{inbound_id: remark}` мэппинг из кэшированного
  panel-листа; при отсутствии fallback — `#<inbound_id>`. Зеркало
  `buy_action_kb`, но callback-фабрика — `PromoActCB`.
- `subscription_kb(sub_id)` — «Получить ключ ещё раз» / «◀ В меню».

callback_data укладывается в 64-байтовый лимит TG.

## Пакет `app/states/` — пользовательские стейты

### [app/states/user.py](./app/states/user.py)
FSM-стейты юзерского флоу.

- `BuyFlow(choosing_action, choosing_plan, choosing_inbound, entering_promo, confirming)` —
  покупка. Первый шаг `choosing_action` показывается только при наличии
  активных подписок (`list_active_for_user`) — там юзер выбирает
  «🔄 Продлить #N · <remark>» или «🆕 Новая подписка» через `buy_action_kb`.
  При отсутствии активных подписок флоу стартует сразу с `choosing_plan`.
  При выборе «extend #N» — следующий шаг сразу `choosing_plan`
  (но при confirm пропускается `choosing_inbound`, так как inbound
  наследуется от существующей подписки), `sub_id` (extend-target)
  пробрасывается через FSM и далее в `BuyCB`/`confirm_kb`/`send_invoice`.
  При выборе «new» (или отсутствии активных) — стандартный путь:
  `choosing_plan` → `choosing_inbound` (хендлер пропускает шаг
  автоматически при единственном inbound в allow-list) → `confirming`.
  Состояние очищается после `send_invoice`; pre_checkout и
  successful_payment приходят stateless, используя `invoice_payload`
  как state-carrier (несёт `plan_id`, `promo_id`, `inbound_id` и
  опциональный `sub_id`).
- `PromoActivate(waiting_code, choosing_action, choosing_inbound)` —
  standalone-активация free_days. После валидации кода (тип `free_days`)
  возможны две ветки: (1) если у пользователя есть активные подписки —
  переход в `choosing_action` с `promo_action_kb` (выбор «Продлить #N»
  или «Новая подписка»); extend-ветка минует `choosing_inbound` и сразу
  вызывает `activate_free_days(extend_sub_id=N)` с inbound, унаследованным
  от существующей sub; new-ветка переходит в `choosing_inbound`. (2) если
  активных подписок нет — сразу `choosing_inbound`: пользователь выбирает
  inbound из 3x-ui, и только тогда вызывается
  `subs_service.activate_free_days(inbound_id=..., extend_sub_id=None)`.
  Discount-промокоды (`percent`/`flat_stars`) на этом шаге отклоняются
  с подсказкой использовать buy flow.

## Связи между модулями

- `app.main` импортирует `settings` (`app.config`), `setup_logging`
  (`app.logger`), `init_db` (`app.db.engine`), `register_routers`
  (`app.handlers`).
- `app.logger` импортирует `settings` (`app.config`) для чтения
  `LOG_LEVEL` по умолчанию.
- `app.db.engine` импортирует `settings` (`app.config`) для `DB_PATH`.
- `app.db.repos.users` импортирует `settings` (`app.config`) для
  чтения `ADMIN_IDS` в `get_or_create`.
- `app.db.repos.promos` импортирует `transaction` (`app.db.engine`)
  для атомарного `try_redeem`.
- Все остальные `app.db.repos.*` зависят только от `aiosqlite` и
  стандартной библиотеки.
- `app.handlers.__init__` импортирует `app.handlers.start`,
  `app.handlers.admin.admin_router`, `app.middlewares.user_ctx.UserContextMiddleware`
  и подключает их к `Dispatcher` (UserContextMiddleware — как
  outer-middleware на `dp.update`).
- `app.handlers.start` импортирует `User` (`app.db.repos.users`) для
  type-hint и `admin_main_menu` (`app.keyboards.admin`) для ветвления
  на админа.
- `app.handlers.admin.__init__` импортирует пять sub-роутеров
  (`menu`, `plans`, `promos`, `users`, `stats`) и `AdminOnlyMiddleware`
  (`app.middlewares.admin_only`).
- `app.handlers.admin.users` импортирует `get_conn` (`app.db.engine`),
  репозитории `payments`/`subscriptions`/`users` и их dataclass-ы,
  helpers `_format_bytes`/`_is_active` из
  `app.handlers.user.my_subscription` (переиспользование),
  `AdminCB`/`UserCB`/`cancel_kb`/`user_card_kb` из `app.keyboards.admin`,
  `services.subscriptions.revoke` (через `app.services.subscriptions`),
  стейт `AdminSearchUser` из `app.states.admin`, `XuiError`/
  `get_xui_client` из `app.xui` и `get_client_traffics` из
  `app.xui.clients`.
- `app.handlers.admin.stats` импортирует `get_conn`, репозиторий
  `users` (для резолва tg_id в списке expiring), dataclass
  `Subscription`, `AdminCB`/`StatsCB`/`stats_kb` из
  `app.keyboards.admin` и сервис `app.services.stats`.
- `app.services.stats` импортирует репозитории `payments`,
  `subscriptions` и dataclass-ы `Promo`/`Subscription`.
- `app.handlers.admin.menu` импортирует `AdminCB`, `admin_main_menu`
  из `app.keyboards.admin`.
- `app.handlers.admin.plans` импортирует `get_conn` (`app.db.engine`),
  `plans` (`app.db.repos`), `Plan`, клавиатуры `PlanCB`, `cancel_kb`,
  `plan_card_kb`, `plan_edit_fields_kb`, `plans_list_kb` и FSM-стейты
  `PlanCreate`/`PlanEdit`.
- `app.handlers.admin.promos` импортирует `get_conn`, репозитории
  `promos` и `users`, dataclass-ы `Promo`/`PromoType`/`User`, клавиатуры
  `PromoCB`, `cancel_kb`, `promo_card_kb`, `promo_type_kb`,
  `promos_list_kb` и стейт `PromoCreate`.
- `app.middlewares.user_ctx` зависит от `get_conn` (`app.db.engine`)
  и `users_repo` (`app.db.repos.users`); проверяет тип `Update` из
  `aiogram.types` для обхода всех полей `from_user`.
- `app.middlewares.admin_only` зависит от `settings` (`app.config`) и
  `User` (`app.db.repos.users`).
- `app.keyboards.admin` зависит только от aiogram (`CallbackData`,
  `InlineKeyboardBuilder`, `InlineKeyboardMarkup`) и dataclass-ов
  `Plan`/`Promo` для типизации входных коллекций.
- `app.states.admin` зависит только от `aiogram.fsm.state`
  (`State`, `StatesGroup`).
- `app.xui.client` импортирует `settings` (`app.config`) для
  `XUI_BASE_URL/USERNAME/PASSWORD/VERIFY_SSL` и `httpx`, `loguru`.
- `app.xui.inbounds` и `app.xui.clients` импортируют `XuiClient` и
  `XuiError` из `app.xui.client`.
- `app.xui.links` импортирует `settings` (`app.config`) для
  `XUI_SERVER_HOST` и `XUI_SUB_BASE_URL`; использует `qrcode` и
  `urllib.parse`.
- `scripts.xui_smoke` импортирует `settings`/`setup_logging` и
  публичный API `app.xui` (`XuiClient`, `add_client`/`del_client`/…,
  `list_inbounds`/`get_inbound`).
- `app.services.promos` импортирует `promos_repo` (`app.db.repos.promos`),
  `Plan`/`Promo` для типов.
- `app.services.billing` импортирует `compute_discount`/`DiscountResult`
  (`app.services.promos`), `Plan`/`Promo` для типов и `aiogram.types`
  (`LabeledPrice`, `Message`).
- `app.services.subscriptions` импортирует `settings` (`app.config`),
  `subs_repo` (`app.db.repos.subscriptions`), `XuiClient`/`XuiError`
  (`app.xui`), и `add_client`/`update_client`/`make_client_email`/
  `make_client_uuid`/`_make_sub_id` (`app.xui.clients`).
- `app.handlers.__init__` теперь также подключает `user_router`
  (`app.handlers.user.__init__`) — самым последним, после admin_router.
- `app.handlers.start` дополнительно импортирует `user_main_menu`
  (`app.keyboards.user`), `get_conn` (`app.db.engine`) и `subs_repo`
  для определения `has_subscription`.
- `app.handlers.user.__init__` импортирует `menu`/`buy`/`promo`/`help` и
  собирает их в `user_router`.
- `app.handlers.user.menu` импортирует `get_conn`, `subs_repo`,
  `User` для type-hint и `UserCB`/`user_main_menu` из `app.keyboards.user`.
- `app.handlers.user.help` импортирует `UserCB`/`back_to_menu_kb` из
  `app.keyboards.user`.
- `app.handlers.user._keys` импортирует `Subscription`, `XuiClient`/`XuiError`,
  `get_inbound`, `build_subscription_url`/`build_vless_link`/`make_qr_png`,
  `subscription_kb`. Использует `BufferedInputFile` из `aiogram.types`.
- `app.handlers.user.buy` импортирует `get_conn`, репозитории `payments`,
  `plans`, `promos`, dataclass-ы `Plan`/`Promo`/`User`, `deliver_keys`
  из `app.handlers.user._keys`, клавиатуры `BuyCB`/`confirm_kb`/`plans_kb`,
  все три сервиса (`billing`, `promos`, `subscriptions`), `BuyFlow`,
  `XuiError`/`get_xui_client`.
- `app.handlers.user.promo` импортирует `get_conn`, `User`,
  `deliver_keys`, `PromoActCB`/`cancel_kb`, `promos_service`/`subs_service`,
  `PromoActivate`, `XuiError`/`get_xui_client`.
- `app.keyboards.user` зависит только от `aiogram` (`CallbackData`,
  `InlineKeyboardBuilder`, `InlineKeyboardMarkup`) и dataclass-а `Plan`.
- `app.states.user` зависит только от `aiogram.fsm.state`.

---

## tests/

Pytest-suite, обеспечивающий >=90% покрытия (фактически 95.95%) и проверку
всех краевых случаев. Запускается командой `pytest` из корня проекта.
Конфигурация — в `pyproject.toml` (`[tool.pytest.ini_options]`):
`asyncio_mode = "auto"`, `--cov=app`, `--cov-fail-under=90`.

Файлы (все находятся в [`tests/`](tests/)):

- [`tests/__init__.py`](tests/__init__.py) — маркер пакета.
- [`tests/conftest.py`](tests/conftest.py) — общие фикстуры:
  - `db_conn` — in-memory aiosqlite + schema/migrations
  - `file_db` — файловая БД + monkeypatch `settings.DB_PATH`
  - `monkey_settings` — патч атрибутов `app.config.settings`
  - фабрики: `make_user`, `make_plan` (auto-attaches default inbound
    из `settings.XUI_INBOUND_ID`; параметр `inbound_ids=[...]` для
    кастомизации), `make_promo`, `make_subscription`
  - `mock_bot`, `mock_xui_client` — AsyncMock для aiogram.Bot и XuiClient
- [`tests/test_config.py`](tests/test_config.py) — Settings, CSV-парсинг
  ADMIN_IDS, дефолты, валидация.
- [`tests/test_db_engine.py`](tests/test_db_engine.py) — init_db, миграции,
  `transaction()` rollback/commit, foreign_keys=ON.
- [`tests/test_db_users.py`](tests/test_db_users.py) — get_by_tg_id,
  get_by_username (NOCASE, со/без @), get_or_create, set_admin.
- [`tests/test_db_plans.py`](tests/test_db_plans.py) — CRUD планов,
  whitelist `update`, `deactivate`.
- [`tests/test_db_promos.py`](tests/test_db_promos.py) — CRUD промо,
  `get_by_code` NOCASE, `try_redeem` race на capacity=1, expired/full
  фильтрация.
- [`tests/test_db_subscriptions.py`](tests/test_db_subscriptions.py) —
  CRUD подписок, `list_expired_active`, `list_expiring_in`, traffic
  snapshots, `try_mark_notification_sent` dedup.
- [`tests/test_db_payments.py`](tests/test_db_payments.py) — UNIQUE
  charge_id, `total_stars_period` исключает refunded, `set_status`.
- [`tests/test_xui_client.py`](tests/test_xui_client.py) — login успех/ошибка,
  retry на 401 / `success=false:msg=login`, asyncio.Lock на параллельные
  запросы, singleton фабрика.
- [`tests/test_xui_inbounds.py`](tests/test_xui_inbounds.py) —
  list/get_inbound с парсингом JSON-string полей.
- [`tests/test_xui_clients.py`](tests/test_xui_clients.py) — add/update/del,
  soft-fail на «not exist», whitelist полей `update_client`, coercion.
- [`tests/test_xui_links.py`](tests/test_xui_links.py) — `make_qr_png`
  (PNG magic), `build_subscription_url`, `build_vless_link` для tcp+reality
  / ws+tls / grpc / http / kcp / quic, graceful fallback.
- [`tests/test_services_billing.py`](tests/test_services_billing.py) —
  `calc_price` (no-promo / percent / flat_stars / free_days), Stars-min,
  ceil-rounding, `build_invoice_payload`/`parse_invoice_payload` с
  3-tuple `(plan_id, promo_id, inbound_id)`, legacy payload без `i`
  → fallback на `settings.XUI_INBOUND_ID`, byte-limit guard,
  `send_invoice` с kwarg `inbound_id` (embedded в payload как `i`).
- [`tests/test_services_promos.py`](tests/test_services_promos.py) —
  `validate` (все ветки), `apply` race на capacity=1.
- [`tests/test_services_subscriptions.py`](tests/test_services_subscriptions.py) —
  `create_or_extend` create/extend ordering, xui-first vs DB-after,
  `activate_free_days`, `revoke`.
- [`tests/test_services_stats.py`](tests/test_services_stats.py) — revenue,
  active count, expiring_in_days, top_promos, payments_count_period.
- [`tests/test_services_broadcast.py`](tests/test_services_broadcast.py) —
  `broadcast_message`: полная доставка, бакеты blocked/failed,
  flood-control retry (успех/повторный провал), пустая аудитория.
- [`tests/test_scheduler.py`](tests/test_scheduler.py) — `_kind_for_days_left`,
  expire/reminders/traffic jobs, dedup через `subscription_notifications`,
  XuiError soft-fail.
- [`tests/test_middlewares.py`](tests/test_middlewares.py) —
  `AdminOnlyMiddleware`, `UserContextMiddleware`, извлечение `from_user`.
- [`tests/test_logger.py`](tests/test_logger.py) — `setup_logging`,
  `InterceptHandler` (stdlib → loguru).
- [`tests/test_handlers_start.py`](tests/test_handlers_start.py) — `/start`
  для админа/юзера с/без подписки.
- [`tests/test_handlers_user_menu.py`](tests/test_handlers_user_menu.py) —
  `/menu`, cancel, help, admin menu.
- [`tests/test_handlers_user_buy.py`](tests/test_handlers_user_buy.py) —
  полный buy flow с выбором inbound: skip-логика для одного inbound,
  multi-inbound селектор, валидация принадлежности inbound тарифу в
  `cb_confirm`/`on_pre_checkout`, recovery с возвратом к селектору,
  legacy payload (без `i`) → fallback на `settings.XUI_INBOUND_ID`,
  идемпотентность по `charge_id`, xui failure → запись payment с
  `subscription_id=None`, redemption промо, warning в `_format_confirm`
  при активной подписке.
- [`tests/test_handlers_user_my_subscription.py`](tests/test_handlers_user_my_subscription.py)
  — карточка с/без подписки, fallback при XuiError, ownership-check.
- [`tests/test_handlers_user_promo.py`](tests/test_handlers_user_promo.py) —
  двухшаговый flow free_days (msg_code → choosing_inbound →
  cb_pick_inbound_for_promo): валидация кода, отказ для percent/flat_stars,
  double-activation guard, выбор inbound из FSM-options, race с
  invalidated promo (deactivate между шагами), xui failure не редимит
  промо, back-callback в waiting_code.
- [`tests/test_handlers_admin_plans.py`](tests/test_handlers_admin_plans.py) —
  FSM создания/редактирования с шагом `waiting_inbounds`, multi-select
  (`toggle_inbound` XOR), `inbounds_done` (empty alert, create/edit
  режимы), `cb_edit_inbounds` (preload current set, xui unavailable,
  empty panel), `_format_plan` рендер (с/без remarks, «(удалён)», «не
  настроены»), валидация полей, деактивация.
- [`tests/test_handlers_admin_promos.py`](tests/test_handlers_admin_promos.py)
  — FSM создания (все 3 типа), expires_at parsing, max_uses=0 unlimited.
- [`tests/test_handlers_admin_users.py`](tests/test_handlers_admin_users.py)
  — поиск по tg_id / @username, карточка с подписками и платежами,
  revoke, toggle_admin.
- [`tests/test_handlers_admin_stats.py`](tests/test_handlers_admin_stats.py)
  — переключение периодов 7d/30d/all, refresh, truncation.
- [`tests/test_handlers_admin_broadcast.py`](tests/test_handlers_admin_broadcast.py)
  — `cb_open` (вход в waiting_post), `st_post` (сохранение ref + счётчик
  аудитории), `cb_send` (рассылка + сводка), отсутствие поста в FSM,
  `_plural`.
- [`tests/test_keys_helper.py`](tests/test_keys_helper.py) — `deliver_keys`
  happy / XuiError fallback / без sub URL.
- [`tests/test_handlers_init.py`](tests/test_handlers_init.py) —
  `register_routers` подключает все маршруты к Dispatcher.
- [`tests/test_db_repos_plans_inbounds.py`](tests/test_db_repos_plans_inbounds.py)
  — `plans_repo.set_inbounds`/`get_inbounds` + таблица `plan_inbounds`:
  ValueError на пустом списке, sort по возрастанию, replace-семантика,
  dedup дубликатов, `[]` для несуществующего plan_id, `ON DELETE CASCADE`
  при hard-delete плана.
- [`tests/test_services_inbounds.py`](tests/test_services_inbounds.py) —
  `list_user_inbounds`: фильтрация `enable=False`, TTL-кэш 30s (через
  `monkeypatch` на `time.monotonic`), `clear_cache()`, propagation
  исключений xui без обновления кэша, skip malformed entries.
- [`tests/test_db_migration_plan_inbounds.py`](tests/test_db_migration_plan_inbounds.py)
  — backfill `plan_inbounds` в `init_db`: legacy плановые строки получают
  `settings.XUI_INBOUND_ID`, идемпотентность (admin set_inbounds
  сохраняется при повторном `init_db`), селективность (только планы без
  записей), graceful no-op при `XUI_INBOUND_ID=0`.
