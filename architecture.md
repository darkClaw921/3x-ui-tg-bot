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
├── assets/
│   └── hero.svg
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
    ├── bot_meta.py
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
    │       ├── payments.py
    │       ├── wallet.py
    │       ├── referrals.py
    │       ├── gift_codes.py
    │       ├── tickets.py
    │       ├── audit.py
    │       └── health.py
    ├── services/
    │   ├── __init__.py
    │   ├── promos.py
    │   ├── billing.py
    │   ├── subscriptions.py
    │   ├── stats.py
    │   ├── exports.py
    │   ├── broadcast.py
    │   ├── wallet.py
    │   ├── referrals.py
    │   ├── gifts.py
    │   ├── tickets.py
    │   ├── audit.py
    │   ├── inbounds.py
    │   └── health.py
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
    │   │   ├── broadcast.py
    │   │   ├── tickets.py
    │   │   └── audit.py
    │   └── user/
    │       ├── __init__.py
    │       ├── _keys.py
    │       ├── menu.py
    │       ├── my_subscription.py
    │       ├── help.py
    │       ├── buy.py
    │       ├── promo.py
    │       ├── trial.py
    │       ├── referral.py
    │       ├── gift.py
    │       ├── wallet.py
    │       ├── support.py
    │       └── language.py
    ├── i18n/
    │   ├── __init__.py
    │   ├── catalog.py
    │   ├── plural.py
    │   └── locales/
    │       ├── __init__.py
    │       ├── ru.py
    │       ├── en.py
    │       ├── uk.py
    │       ├── fa.py
    │       └── zh.py
    ├── keyboards/
    │   ├── __init__.py
    │   ├── admin.py
    │   └── user.py
    ├── middlewares/
    │   ├── __init__.py
    │   ├── admin_only.py
    │   ├── blocked.py
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
и [docs/e2e-checklist.md](./docs/e2e-checklist.md). В шапке (hero) встроен
баннер [assets/hero.svg](./assets/hero.svg); длинные разделы (деплой, бэкап,
сценарии использования) свёрнуты в `<details>`-блоки.

## Каталог `assets/`

### [assets/hero.svg](./assets/hero.svg)
Векторный hero-баннер для шапки README (`viewBox 0 0 1200 500`). Отрисовывает
суть проекта: горизонтальный поток из четырёх узлов-карточек
**Пользователь → Telegram-бот → 3x-ui Panel → VPN-доступ**, соединённых
анимированными пунктирными коннекторами с движущимися «пакетами», падающие
сверху на бота Telegram Stars и возвратный путь выдачи ключа
(`vless:// · QR-код · Subscription URL`). Внизу — капсулы tech-стека
(Python 3.12, aiogram 3.x, SQLite, VLESS+Reality, Telegram Stars).
Самодостаточен: все градиенты, фильтры свечения (`feGaussianBlur`), точечная
сетка-паттерн и SMIL-анимации (`animate`, `animateTransform`, `animateMotion`)
определены внутри `<defs>`; внешних шрифтов и ресурсов не требует, тёмный фон
вшит, поэтому одинаково смотрится в светлой и тёмной теме GitHub.
Анимации: бегущий блик по заголовку (анимированный `gradientTransform`),
мерцание/парение Telegram Stars, движущиеся «пакеты» по коннекторам и
возвратному пути, пульсирующее кольцо вокруг бота, мигающие LED-индикаторы на
стойке 3x-ui, исходящая «волна» от щита VPN, дыхание фоновых orb-пятен и лёгкое
парение иконок узлов.

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
  `--bot-repo`, `--ssl-mode` (auto|on|off), `--le-email`, `--client-email`,
  `--skip-blocklist-check`, `--force-blocked-ip`,
  `--non-interactive`, `--help`).
- `info/ok/warn/err/fatal()` — цветные логи в stderr + tee в
  `/var/log/install-3x-ui.log`.
- `cleanup()` (trap EXIT) — удаление cookie-файла + подсказка по
  восстановлению в случае ошибки.
- `ask()`, `ask_secret()` — интерактивный/неинтерактивный prompt.
- `rand_port()`, `rand_hex()`, `rand_base64()`, `port_in_use()` —
  утилиты.
- `ensure_root()`, `ensure_os()` — префлайт.
- `detect_public_ip()`, `check_ip_blocklist()` — шаг 0, самый первый в
  `main()` (до любых apt-install/настроек). Определяет публичный IP сервера
  (api.ipify.org / ifconfig.me / icanhazip.com, первый успешный ответ),
  скачивает реестр блокировок РКН с `antifilter.download/list/ipsum.lst`
  и проверяет точный IP и его `/24`-подсеть на вхождение. Если найден —
  `fatal()` (установка не имеет смысла: провайдеры РФ блокируют весь
  трафик к такому IP на сетевом уровне независимо от протокола), если не
  указан `--force-blocked-ip`. Сетевые сбои (нет curl, недоступен
  antifilter.download, не удалось определить IP) — не фатальны, просто
  `warn()` и пропуск проверки. Полностью отключается `--skip-blocklist-check`.
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
- `create_default_client()` — сразу после `create_inbound()`. Генерирует
  UUID клиента (`/proc/sys/kernel/random/uuid`, fallback на
  `python3 -c 'import uuid...'`), добавляет его через
  `POST /panel/api/inbounds/addClient` с email `--client-email`
  (по умолчанию `admin`) и `flow=xtls-rprx-vision`, и сразу собирает
  готовую ссылку `vless://UUID@DOMAIN:VLESS_PORT?...&pbk=...&sid=...`
  в `CONNECTION_LINK` — она печатается в `final_report()`.
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
  Reality publicKey/shortId, готовую ссылку подключения (`CONNECTION_LINK`),
  путь к `.env`, команды для проверки и рекомендации по бэкапу.
- `main()` — оркестрация шагов: `ensure_root` → `ensure_os` →
  `init_log_file` → `check_ip_blocklist` (до опроса параметров — нет смысла
  спрашивать bot-token/admin-id, если IP уже заблокирован) → `finalize_params`
  → `preflight` → `configure_ufw` → `install_3x_ui` →
  `configure_panel_settings` → `panel_login` → `configure_sub_via_api` →
  `generate_reality_keys` → `create_inbound` → `create_default_client` →
  `setup_panel_tls` → `write_env` → `install_bot` → `final_report`.

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
  5. `setup_scheduler(bot).start()` — пять cron-job-ов
     (`expire_check`, `reminders`, `traffic_snapshots`, `auto_renew`,
     `health_check`).
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
  `WALLET_TOPUP_PRESETS: Annotated[list[int], NoDecode]` (default
  `[50, 100, 250, 500]` — суммы Stars для кнопок пополнения на экране Кошелёк),
  `DB_PATH: str = "./data/bot.db"`, `XUI_BASE_URL`, `XUI_USERNAME`,
  `XUI_PASSWORD`, `XUI_INBOUND_ID: int`, `XUI_SERVER_HOST`,
  `XUI_SUB_BASE_URL`, `XUI_VERIFY_SSL: bool = True`,
  `TRIAL_DAYS: int = 0` (длина пробного периода в днях; 0 = trial выкл),
  `TRIAL_TRAFFIC_GB: int = 0` (лимит трафика trial в ГБ; 0 = безлимит),
  `REFERRAL_BONUS_STARS: int = 0` (Stars-бонус приглашающему; 0 = выкл),
  `AUTO_RENEW_ENABLED: bool = True` (мастер-флаг автопродления: нативные Star
  Subscriptions + wallet-fallback),
  `TRAFFIC_ALERT_PERCENT: int = 80` (порог трафик-алерта в % квоты тарифа,
  0..100; 0 = выкл),
  `STAR_SUBSCRIPTION_PLAN_DAYS: int = 30` (длина тарифа в днях, дающая право на
  нативную Star-подписку — совпадает с `billing.SUBSCRIPTION_PERIOD_SECONDS`),
  `SUPPORT_CHAT_ID: int = 0` (опциональный чат для ретрансляции тикетов
  поддержки; 0 = только DM админам из `ADMIN_IDS`),
  `DEFAULT_LANGUAGE: str = "ru"` (резервный UI-язык новых юзеров),
  `LOG_LEVEL: str = "INFO"`.
- `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8",
  case_sensitive=True, extra="ignore")`.
- `@field_validator("ADMIN_IDS", "WALLET_TOPUP_PRESETS", mode="before")
  _parse_csv_ints` — общий валидатор для обоих CSV-полей: принимает CSV-строку
  `"1,2,3"`, пустую строку, JSON-массив или список → `list[int]`. Аннотация
  `NoDecode` отключает попытку pydantic-settings распарсить значение через
  `json.loads` до запуска валидатора.
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
- `users` (id PK, tg_id UNIQUE, username, first_name, is_admin,
  `lang TEXT NOT NULL DEFAULT 'ru'`, `is_blocked INTEGER NOT NULL DEFAULT 0`,
  created_at). Колонка `lang` хранит выбранный язык интерфейса (один из
  `app.i18n.SUPPORTED_LANGS`); добавлена идемпотентной миграцией `ALTER TABLE
  users ADD COLUMN lang TEXT NOT NULL DEFAULT 'ru'`. Колонка `is_blocked`
  помечает забаненного админом юзера (1); проверяется `BlockedUserMiddleware`
  до любого хендлера; добавлена миграцией `ALTER TABLE users ADD COLUMN
  is_blocked INTEGER NOT NULL DEFAULT 0` в `_apply_migrations`.
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
  status CHECK IN ('active','expired','revoked'),
  `is_trial INTEGER NOT NULL DEFAULT 0`,
  `auto_renew INTEGER NOT NULL DEFAULT 0`, `tg_sub_charge_id TEXT NULL`).
  Колонка `is_trial` помечает пробную подписку (1) vs обычную/платную (0);
  добавлена идемпотентной миграцией `ALTER TABLE subscriptions ADD COLUMN
  is_trial INTEGER NOT NULL DEFAULT 0`. Правило «один trial на юзера»
  обеспечивается partial-unique индексом `idx_subscriptions_one_trial
  UNIQUE(user_id) WHERE is_trial=1`. Колонки `auto_renew` / `tg_sub_charge_id`
  (миграции `ALTER TABLE ADD COLUMN`) обслуживают автопродление: `auto_renew=1`
  включает автопродление, `tg_sub_charge_id` хранит `telegram_payment_charge_id`
  нативной Telegram Star-подписки (нужен для `bot.edit_user_star_subscription`)
  и отличает нативную подписку (non-NULL) от wallet-fallback (NULL).
- `promo_redemptions` (id PK, promo_id FK ON DELETE CASCADE, user_id FK ON DELETE CASCADE,
  subscription_id FK ON DELETE SET NULL, redeemed_at).
- `payments` (id PK, user_id FK ON DELETE CASCADE, subscription_id FK ON DELETE SET NULL,
  telegram_charge_id UNIQUE, stars_amount, plan_id FK ON DELETE SET NULL,
  promo_id FK ON DELETE SET NULL, status CHECK IN ('paid','refunded'), created_at).
- `traffic_snapshots` (id PK, subscription_id FK ON DELETE CASCADE, up, down, taken_at).
- `subscription_notifications` (id PK, subscription_id FK ON DELETE CASCADE,
  kind TEXT (free-text), sent_at, UNIQUE(subscription_id, kind)) — ledger
  дедупликации для scheduler-job-ов напоминаний, финального уведомления об
  истечении и трафик-алерта (`'traffic80'`). Допустимые значения kind
  валидируются в коде (`subscriptions.NOTIFICATION_KINDS`:
  `'3d'/'1d'/'0d'/'expired'/'traffic80'`), а не CHECK-constraint'ом — legacy
  CHECK снимается терпимой data-preserving миграцией
  `engine._relax_subscription_notifications_kind` (без destructive rebuild), что
  позволяет добавлять новые kind без пересборки таблицы на существующих БД.
- `wallet_transactions` (id PK, user_id FK users.id ON DELETE CASCADE,
  type CHECK IN ('topup','spend','refund','referral_bonus','admin_grant','payment'),
  amount (знаковый int — кредиты +, списания −), ref TEXT NULL, created_at) —
  append-only ledger баланса в Stars. Баланс не хранится столбцом, всегда
  пересчитывается как `COALESCE(SUM(amount),0)`. Идемпотентность — partial-unique
  индекс `idx_wallet_ref UNIQUE(ref) WHERE ref IS NOT NULL` (глобальная защита от
  replay/double-credit/double-spend по детерминированному `ref`).
- `referrals` (id PK, referrer_id FK users.id ON DELETE CASCADE,
  referred_id FK users.id ON DELETE CASCADE UNIQUE,
  status CHECK IN ('pending','rewarded') DEFAULT 'pending', created_at,
  rewarded_at NULL) — реферальный ledger: одна строка на приглашённого
  (`referred_id` UNIQUE). Бонус приглашающему выплачивается ровно один раз —
  атомарный `UPDATE WHERE status='pending'` (`referrals.try_mark_rewarded`).
- `gift_codes` (id PK, code UNIQUE, plan_id FK plans.id ON DELETE SET NULL,
  inbound_id, buyer_id FK users.id ON DELETE CASCADE,
  payment_id FK payments.id ON DELETE SET NULL,
  status CHECK IN ('active','redeemed','refunded') DEFAULT 'active',
  redeemed_by FK users.id ON DELETE SET NULL,
  subscription_id FK subscriptions.id ON DELETE SET NULL, created_at,
  redeemed_at NULL) — подарочные коды: покупатель оплачивает, получатель
  активирует. Жизненный цикл `active→redeemed/refunded`; атомарный claim под
  `BEGIN IMMEDIATE` (`gift_codes.try_claim`/`try_redeem`).
- `tickets` (id PK, user_id FK users.id ON DELETE CASCADE,
  status CHECK IN ('open','answered','closed') DEFAULT 'open', created_at,
  updated_at) — тикет поддержки (двусторонний чат через бота). Статус идёт
  `open` (юзер написал, ждёт админа) → `answered` (админ ответил, ждёт юзера)
  → `closed` (терминальный). `updated_at` бампится на каждое сообщение/смену
  статуса для сортировки списка открытых по активности.
- `ticket_messages` (id PK, ticket_id FK tickets.id ON DELETE CASCADE,
  sender CHECK IN ('user','admin'), text, tg_message_id NULL, created_at) —
  append-only транскрипт тикета.
- `audit_log` (id PK, admin_id FK users.id ON DELETE SET NULL, action,
  target_type NULL, target_id NULL, details TEXT NULL (JSON), created_at) —
  append-only лог привилегированных админ-действий (plan/promo CRUD, user
  revoke/toggle_admin/grant_sub/block, broadcast, ticket reply/close,
  `stats.export`). `action` — короткий dotted-глагол (`'plan.create'`,
  `'user.block'`).
- `health_status` (id PK, component TEXT UNIQUE DEFAULT 'xui', status CHECK IN
  ('up','down'), last_error TEXT NULL, changed_at) — последнее известное
  состояние доступности 3x-ui панели (одна логическая строка на компонент).
  `changed_at` сдвигается только при реальной смене состояния. Хранит prev-state
  между запусками health-check-job-а, чтобы алертить админам только на смену
  up↔down. Repo [app/db/repos/health.py](./app/db/repos/health.py).

Индексы: `users(tg_id)`, `subscriptions(user_id)`, `subscriptions(user_id,status)`,
`subscriptions(expires_at)`, partial-unique `idx_subscriptions_one_trial(user_id)
WHERE is_trial=1`, `idx_subscriptions_tg_sub_charge(tg_sub_charge_id)`,
`promos(code)`, `promo_redemptions(promo_id)`,
`promo_redemptions(user_id)`, `payments(user_id)`, `payments(telegram_charge_id)`,
`traffic_snapshots(subscription_id, taken_at)`,
`subscription_notifications(subscription_id)`, `plan_inbounds(plan_id)`,
`wallet_transactions(user_id)`, partial-unique `idx_wallet_ref(ref) WHERE ref IS NOT NULL`,
`referrals(referrer_id)`, `gift_codes(code)`, `gift_codes(buyer_id)`,
`tickets(user_id)`, `tickets(status)`, `ticket_messages(ticket_id)`,
`audit_log(created_at)`, `audit_log(admin_id)`, unique `health_status(component)`.

### [app/db/engine.py](./app/db/engine.py)
Async-движок поверх `aiosqlite`.

- `async def init_db() -> None` — создаёт директорию `DB_PATH.parent`,
  открывает соединение, применяет `schema.sql` через `executescript`,
  затем вызывает `_apply_migrations(conn)`.
- `async def _apply_migrations(conn)` — два набора миграций плюс backfill:
  1. Идемпотентные `ALTER TABLE` (try/except на "duplicate column"/
     "already exists"). Текущий перечень: добавление
     `subscriptions.xui_sub_id TEXT NOT NULL DEFAULT ''`,
     `plans.traffic_gb INTEGER NOT NULL DEFAULT 0`,
     `users.lang TEXT NOT NULL DEFAULT 'ru'`,
     `subscriptions.is_trial INTEGER NOT NULL DEFAULT 0`,
     `subscriptions.auto_renew` / `subscriptions.tg_sub_charge_id` и
     `users.is_blocked INTEGER NOT NULL DEFAULT 0`.
  2. `CREATE TABLE/INDEX IF NOT EXISTS` для таблиц, появившихся после
     первоначальной схемы. Применяются и на свежих БД (no-op, т.к.
     SQL идемпотентен), и при апгрейде существующих. Текущий перечень:
     `subscription_notifications` + индекс `idx_subscription_notifications_sub`,
     `plan_inbounds` + индекс `idx_plan_inbounds_plan`,
     `wallet_transactions` + индекс `idx_wallet_transactions_user` +
     partial-unique `idx_wallet_ref(ref) WHERE ref IS NOT NULL`,
     partial-unique `idx_subscriptions_one_trial(user_id) WHERE is_trial=1`,
     `referrals` + индекс `idx_referrals_referrer`,
     `gift_codes` + индексы `idx_gift_codes_code`/`idx_gift_codes_buyer`,
     `tickets` + индексы `idx_tickets_user`/`idx_tickets_status`,
     `ticket_messages` + индекс `idx_ticket_messages_ticket`,
     `audit_log` + индексы `idx_audit_log_created`/`idx_audit_log_admin`,
     `health_status` (unique-колонка `component`).
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

- Dataclass `User(id, tg_id, username, first_name, is_admin, created_at,
  lang="ru", is_blocked=False)`. Поля `lang` / `is_blocked` объявлены с
  дефолтами в конце, чтобы существующие позиционные конструкторы `User(...)`
  в тестах не ломались. `is_blocked` помечает забаненного админом юзера.
- `User.from_row(row)` — построение из `aiosqlite.Row`; терпит row без
  колонок `lang` / `is_blocked` (дефолты `"ru"` / `False`).
- `async def get_by_tg_id(conn, tg_id) -> User | None` (SELECT включает `lang`).
- `async def get_by_id(conn, user_id) -> User | None` (SELECT включает `lang`).
- `async def get_by_username(conn, username) -> User | None` —
  case-insensitive (`COLLATE NOCASE`); удаляет ведущий `@`, пустой
  запрос → `None`. Используется админским поиском по @handle.
- `async def create(conn, tg_id, username, first_name, is_admin=False, *,
  language_code=None) -> User` — `language_code` нормализуется через
  `resolve_lang` и пишется в колонку `lang`.
- `async def get_or_create(conn, tg_id, username, first_name, *,
  language_code=None) -> User` — идемпотентен; `is_admin` синхронизируется с
  `settings.ADMIN_IDS`; `language_code` влияет только на создание НОВОГО
  юзера (язык существующего не перетирается).
- `async def list_all_tg_ids(conn) -> list[int]` — `tg_id` всех
  пользователей, старейшие первыми (`ORDER BY id`); используется
  админской рассылкой (`app.handlers.admin.broadcast`).
- `async def set_admin(conn, user_id, value: bool)`.
- `async def set_blocked(conn, user_id, blocked: bool)` — выставляет флаг
  `is_blocked` (бан/разбан); вызывается из админской карточки юзера.
- `async def is_blocked(conn, tg_id) -> bool` — узкий lookup по `tg_id`
  (без полного `User`); используется `BlockedUserMiddleware`. Для неизвестного
  юзера возвращает `False`.
- `async def set_lang(conn, user_id, lang)` — сохраняет язык интерфейса
  (нормализуется через `resolve_lang` защитно); используется роутером
  выбора языка.
- `async def get_lang(conn, user_id) -> str` — читает язык; для
  отсутствующего юзера возвращает `DEFAULT_LANG`.

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
  xui_client_email, xui_sub_id, expires_at, created_at, plan_id, status,
  is_trial=False, auto_renew=False, tg_sub_charge_id=None)`. `is_trial` —
  флаг пробной подписки; `auto_renew` — включено ли автопродление;
  `tg_sub_charge_id` — `telegram_payment_charge_id` нативной Star-подписки
  (или `None` для wallet-fallback / разовой покупки). Все три — последние поля
  с дефолтами, чтобы позиционные конструкторы в тестах не ломались; `from_row`
  читает каждую колонку, если она присутствует в выборке.
- Dataclass `TrafficSnapshot(id, subscription_id, up, down, taken_at)`.
- `async def create(conn, user_id, xui_inbound_id, xui_client_uuid,
  xui_client_email, expires_at, plan_id, xui_sub_id="", is_trial=False)
  -> Subscription` (status='active'; `xui_sub_id` — `subId` из 3x-ui для
  public subscription URL). При `is_trial=True` insert подчиняется
  partial-unique индексу `idx_subscriptions_one_trial` — второй trial для
  того же юзера => `IntegrityError`.
- `async def has_trial(conn, user_id) -> bool` — есть ли у юзера trial-подписка
  (race-tolerant SELECT перед `activate_trial`; жёсткая гарантия — индекс).
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
- `async def set_auto_renew(conn, sub_id, value, tg_sub_charge_id=None)` —
  переключает `auto_renew` и (опционально) пишет `tg_sub_charge_id`. При
  `tg_sub_charge_id=None` пишется только `auto_renew`, поэтому выключение флага
  не затирает ранее сохранённый charge id (нужен для повторного включения).
- `async def list_auto_renew_due(conn, within_hours=24) -> list[Subscription]` —
  active И `auto_renew=1` И `tg_sub_charge_id IS NULL` (только wallet-fallback,
  нативные Star-подписки продлевает Telegram) И `expires_at<=now+within_hours`,
  ORDER BY `expires_at ASC`. Драйвер `scheduler.auto_renew_job`.
- `async def get_active_auto_renew_for(conn, user_id, plan_id) ->
  Subscription | None` — активная нативная Star-подписка юзера по плану
  (`auto_renew=1 AND tg_sub_charge_id IS NOT NULL`), latest-expiring первой.
  Используется `buy.on_successful_payment` для поиска подписки, которую
  продлевает очередной recurring-charge.
- `async def list_expired_active(conn, now=None) -> list[Subscription]` —
  для expire-job-а: active И `expires_at<=now`.
- `async def list_active(conn) -> list[Subscription]`.
- `async def list_expiring_in(conn, days) -> list[Subscription]` —
  active в окне `(now, now+days]`.
- `async def add_traffic_snapshot(conn, sub_id, up, down) -> TrafficSnapshot`.
- `async def last_traffic_snapshot(conn, sub_id) -> TrafficSnapshot | None`.
- Литерал `NotificationKind = Literal["3d","1d","0d","expired","traffic80"]` +
  `NOTIFICATION_KINDS: frozenset` — допустимые kind (валидируются в коде, т.к.
  колонка БД теперь free-text).
- `async def try_mark_notification_sent(conn, sub_id, kind) -> bool` —
  атомарный `INSERT OR IGNORE` в `subscription_notifications`; валидирует
  `kind` против `NOTIFICATION_KINDS` (иначе `ValueError`). Возвращает `True`,
  если строка была вставлена (значит можно слать сообщение), и `False`, если
  запись `(sub_id, kind)` уже существовала. Используется scheduler-job-ами для
  дедупликации напоминаний и трафик-алерта (UNIQUE-constraint гарантирует, что
  каждое kind отправляется ровно один раз).

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

### [app/db/repos/wallet.py](./app/db/repos/wallet.py)
Репозиторий append-only ledger баланса в Stars (таблица `wallet_transactions`).

- Литерал `WalletTxnType = Literal["topup","spend","refund","referral_bonus",
  "admin_grant","payment"]`.
- Dataclass `WalletTxn(id, user_id, type, amount, ref, created_at)` + `from_row`.
- `async def balance(conn, user_id) -> int` — `COALESCE(SUM(amount),0)` по строкам
  пользователя (баланс не хранится столбцом).
- `async def add(conn, *, user_id, type, amount, ref=None) -> WalletTxn | None` —
  вставка строки ledger; `None` при дубле non-null `ref` (ловит `IntegrityError`
  partial-unique `idx_wallet_ref`, без commit при дубле). Коммитит при успехе.
- `async def get_by_ref(conn, ref) -> WalletTxn | None` — поиск по уникальному
  non-null `ref` (используется pay-from-balance для восстановления id spend-txn).
- `async def list_for_user(conn, user_id, limit=20) -> list[WalletTxn]` —
  `ORDER BY created_at DESC, id DESC LIMIT`.

### [app/db/repos/referrals.py](./app/db/repos/referrals.py)
Репозиторий реферального ledger (таблица `referrals`).

- Литерал `ReferralStatus = Literal["pending","rewarded"]`.
- Dataclass `Referral(id, referrer_id, referred_id, status, created_at,
  rewarded_at)` + `from_row`.
- `async def create_pending(conn, *, referrer_id, referred_id) -> Referral | None`
  — `INSERT OR IGNORE` против UNIQUE(referred_id); `None`, если приглашённый
  уже привязан (привязка ровно один раз — первый `/start` побеждает).
- `async def get(conn, referral_id) -> Referral | None`.
- `async def get_by_referred(conn, referred_id) -> Referral | None` — лукап по
  UNIQUE `referred_id`.
- `async def try_mark_rewarded(conn, referred_id) -> Referral | None` —
  атомарный `UPDATE … WHERE referred_id=? AND status='pending'`; возвращает
  обновлённую строку при выигрыше (`rowcount=1`) или `None` (уже награждён/
  гонка). Гарантирует выплату бонуса ровно один раз.
- `async def count_for_referrer(conn, referrer_id) -> int` — число приглашённых
  (любого статуса) для экрана «Пригласить друга».

### [app/db/repos/gift_codes.py](./app/db/repos/gift_codes.py)
Репозиторий подарочных кодов (таблица `gift_codes`).

- Литерал `GiftCodeStatus = Literal["active","redeemed","refunded"]`.
- Dataclass `GiftCode(id, code, plan_id, inbound_id, buyer_id, payment_id,
  status, redeemed_by, subscription_id, created_at, redeemed_at)` + `from_row`.
- `async def create(conn, *, code, plan_id, inbound_id, buyer_id,
  payment_id=None) -> GiftCode` — INSERT `active`; UNIQUE на `code` =>
  `IntegrityError` (retry в `gifts.make_gift_code`).
- `async def get(conn, gift_id) -> GiftCode | None`.
- `async def get_by_code(conn, code) -> GiftCode | None` — case-insensitive
  (`COLLATE NOCASE`).
- `async def try_redeem(conn, *, code, redeemed_by, subscription_id) -> bool` —
  атомарный claim+link под `transaction()` (BEGIN IMMEDIATE), guarded
  `UPDATE … WHERE status='active'`; `True`/`False`. Используется в тестах /
  когда подписка уже создана.
- `async def try_claim(conn, *, code, redeemed_by) -> GiftCode | None` —
  claim-first: атомарный `active→redeemed` под `transaction()` без
  `subscription_id` (link позже). `None`, если код отсутствует/уже занят/гонка.
- `async def link_subscription(conn, gift_id, subscription_id)` — привязка
  провижиненной подписки к claimed-коду.
- `async def set_status(conn, gift_id, status)` — компенсация (откат в
  `active` при XuiError) / refund.
- `async def list_for_buyer(conn, buyer_id) -> list[GiftCode]`.

### [app/db/repos/tickets.py](./app/db/repos/tickets.py)
Репозиторий тикетов поддержки (таблицы `tickets` + `ticket_messages`).

- Литералы `TicketStatus = Literal["open","answered","closed"]`,
  `TicketSender = Literal["user","admin"]`.
- Dataclass `Ticket(id, user_id, status, created_at, updated_at)` + `from_row`.
- Dataclass `TicketMessage(id, ticket_id, sender, text, tg_message_id,
  created_at)` + `from_row`.
- `async def create_ticket(conn, user_id) -> Ticket` — открывает тикет
  `'open'`.
- `async def add_message(conn, ticket_id, sender, text, tg_message_id=None)
  -> TicketMessage` — добавляет сообщение в транскрипт и бампит
  `tickets.updated_at` (статус не меняет — это решает сервис).
- `async def get(conn, ticket_id) -> Ticket | None`.
- `async def list_open(conn) -> list[Ticket]` — все non-closed тикеты, по
  `updated_at DESC` (открытые + отвеченные).
- `async def list_for_user(conn, user_id) -> list[Ticket]` — newest first.
- `async def get_open_for_user(conn, user_id) -> Ticket | None` — последний
  non-closed тикет юзера (для follow-up в тот же тикет).
- `async def set_status(conn, ticket_id, status)` — смена статуса + бамп
  `updated_at`.
- `async def list_messages(conn, ticket_id) -> list[TicketMessage]` —
  транскрипт в хронологическом порядке.

### [app/db/repos/audit.py](./app/db/repos/audit.py)
Репозиторий аудит-лога админ-действий (таблица `audit_log`).

- Dataclass `AuditEntry(id, admin_id, action, target_type, target_id, details,
  created_at)` + `from_row`.
- `async def add(conn, *, admin_id, action, target_type=None, target_id=None,
  details=None) -> AuditEntry` — append записи; коммитит.
- `async def get(conn, entry_id) -> AuditEntry | None`.
- `async def list_recent(conn, *, limit=20, offset=0) -> list[AuditEntry]` —
  newest first; пагинация для экрана «📜 Аудит».
- `async def count(conn) -> int` — общее число записей.

### [app/db/repos/health.py](./app/db/repos/health.py)
Репозиторий статуса доступности 3x-ui панели (таблица `health_status`). Хранит
prev-state между запусками health-check-job-а, чтобы алертить только на смену.

- Dataclass `HealthRow(id, component, status, last_error, changed_at)` +
  `from_row`; `HealthState = Literal['up','down']`; константа
  `DEFAULT_COMPONENT = 'xui'`.
- `async def get(conn, component='xui') -> HealthRow | None` — текущее состояние
  (None до первой пробы).
- `async def record(conn, *, status, last_error=None, component='xui') ->
  tuple[HealthRow, bool]` — upsert; возвращает `(row, changed)`, где `changed`
  True только при реальной смене состояния (включая первую пробу). `changed_at`
  бампится лишь на флипе; в steady-state обновляется только `last_error`.

## Пакет `app/handlers/`

### [app/handlers/\_\_init\_\_.py](./app/handlers/__init__.py)
Агрегатор роутеров и middleware верхнего уровня.

- `def register_routers(dp: Dispatcher) -> None`:
  1. Регистрирует `BlockedUserMiddleware` на `dp.update.outer_middleware`
     ПЕРВЫМ — апдейт забаненного юзера потребляется до любого хендлера и до
     `UserContextMiddleware` (админы никогда не блокируются).
  2. Регистрирует `UserContextMiddleware` на `dp.update.outer_middleware`
     (после блокировки — aiogram запускает outer-middleware в порядке
     регистрации) — каждый выживший апдейт получает `data['user']`.
  3. Подключает `start.router` (первым — `/start` должен срабатывать всегда).
  4. Подключает `admin_router` (с собственной `AdminOnlyMiddleware` на
     router-level).
  5. Подключает `user_router` (catch-all для юзерских колбеков и
     сообщений; FSM-стейты `BuyFlow`/`PromoActivate`/`SupportFlow` живут в нём).

### [app/handlers/start.py](./app/handlers/start.py)
Роутер команды `/start`.

- `router = Router(name="start")`.
- Константы `_REF_PREFIX = "ref_"`, `_GIFT_PREFIX = "gift_"`.
- `def _parse_deep_link(args: str | None) -> tuple[str, str] | None` —
  классифицирует deep-link аргумент `/start`: `"ref_123" → ("ref","123")`,
  `"gift_ABC" → ("gift","ABC")`. `None` для пустого/неизвестного аргумента
  или пустого значения после префикса.
- `async def _handle_ref_deep_link(value, user)` — привязка нового юзера к
  инвайтеру из `ref_<tg_id>` через `referrals_service.register_referral`
  (best-effort, не ломает `/start`).
- `async def _handle_gift_deep_link(message, bot, code, user, lang) -> bool` —
  активация `gift_<code>`: `gifts_service.redeem_gift` → `deliver_keys`
  получателю + `notify_gift_buyer` (импорт из `handlers.user.gift`); при
  `GiftRedeemError`/`XuiError` — сообщение об ошибке. `True` = ранний выход
  (без приветствия поверх доставленных ключей).
- `async def cmd_start(message, command=None, bot=None, user=None, lang=DEFAULT_LANG)` —
  хэндлер `CommandStart()`. Парсит deep-link через `_parse_deep_link`:
  `ref_<id>` → `_handle_ref_deep_link`; `gift_<code>` → `_handle_gift_deep_link`
  (при успехе — early return). Если `user.is_admin` — админ-меню; иначе
  `user_main_menu(has_subscription, can_trial=(TRIAL_DAYS>0 AND not
  has_trial))` с приоритетом «Моя подписка».

### [app/handlers/admin/\_\_init\_\_.py](./app/handlers/admin/__init__.py)
Агрегатор админ-роутера.

- `_build_admin_router()` строит `Router(name="admin")`, навешивает
  `AdminOnlyMiddleware` на `admin_router.message` и
  `admin_router.callback_query`, включает суб-роутеры
  `menu.router`, `plans.router`, `promos.router`, `users.router`,
  `stats.router`, `broadcast.router`, `tickets.router`, `audit.router`.
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
    HTML-карточку: header (имя/tg_id/username/is_admin/блокировка/created_at) +
    подписки (active с трафиком, inactive — компактный список до 5) +
    последние 10 платежей. Обрезает на 4000 символов.
  - `_render_card_message(message, target, edit=True)` — рендер (передаёт
    `is_blocked=target.is_blocked` в `user_card_kb`).
  - `_resolve_user_query(query) -> User | None` — цифры → `get_by_tg_id`,
    иначе → `get_by_username` (case-insensitive).
  - `_admin_id(user) -> int | None` — `users.id` действующего админа для
    аудит-записей (берётся из инжектированного `data['user']`).
  - `_resolve_plan_inbound(plan_id) -> int` — первый inbound тарифа (fallback
    `settings.XUI_INBOUND_ID`) для ручной выдачи.
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
    `sub.user_id == target.id`; аудит `user.revoke_sub`; перерисовка карточки.
  - `cb_toggle_admin` (`UserCB action=toggle_admin, id=users.id`) —
    flip `is_admin` через `users_repo.set_admin`; аудит `user.toggle_admin`.
  - `cb_toggle_block` (`UserCB action=toggle_block, id=users.id`) —
    бан/разбан через `users_repo.set_blocked`; гварды «нельзя забанить себя»
    и «нельзя забанить админа» (по флагу или `ADMIN_IDS`); аудит
    `user.block`/`user.unblock`; перерисовка карточки.
  - `cb_grant_open` → `cb_grant_plan` → `st_grant_days` — ручная выдача
    подписки (FSM `AdminGrantSub`): выбор тарифа (`GrantCB`), затем срок
    (число дней или «-» = срок тарифа); провижининг через
    `subs_service.grant_subscription` (xui-first), `deliver_keys` + уведомление
    юзеру (best-effort), аудит `user.grant_sub`.

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
  - `cb_export` (`StatsCB action=export`) — строит 3 CSV-блоба
    (payments/subscriptions/users) через `app.services.exports`, шлёт каждый
    как `BufferedInputFile`-документ в чат админа (`bot.send_document`,
    caption `admin.export.caption_*`, имя `<dataset>-<stamp>.csv`), пишет
    аудит-запись `stats.export`, отвечает тостом `admin.export.done`.
    Best-effort: ошибка сборки/отправки → alert `admin.export.failed`.

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
    запущена…», вызывает `broadcast_message`, пишет аудит `broadcast.send`
    (details: total/sent/blocked/failed) и редактирует сообщение в итоговую
    сводку (получатели/доставлено/заблокировали/ошибки) с `back_to_main_kb`.
    При отсутствии `post_*` в FSM — alert + сброс.
- `_plural(n)` — дательное окончание «пользовател-» (ю/ям) для счётчика.
- Отмена на любом шаге — общий `cancel_fsm` из `menu.py` (кнопка
  «✖ Отмена» переиспользует `AdminCB(area=main, action=cancel)`).

> Аудит-вызовы `audit_service.log_action` встроены также в `plans.py`
> (`plan.create`/`plan.edit`/`plan.deactivate`) и `promos.py`
> (`promo.create`/`promo.deactivate`).

### [app/handlers/admin/tickets.py](./app/handlers/admin/tickets.py)
Админский экран «💬 Тикеты»: список открытых, карточка с транскриптом,
двусторонний ответ/закрытие. FSM `AdminTicketReply.writing`.

- `router = Router(name="admin_tickets")`. Константа `_MAX_HISTORY = 20`.
- Helpers: `_safe`, `_status_label(status, lang)`, `_user_short(user)`,
  `_render_list(message, lang, edit)`, `_build_card(ticket, lang)` (header +
  последние 20 сообщений транскрипта), `_render_card(message, ticket, lang,
  edit)`.
- Хендлеры:
  - `cb_open` / `cb_list` (`AdminCB area=tickets action=open` / `TicketCB
    action=list`) — список открытых (`tickets_repo.list_open` + `tickets_list_kb`).
  - `cb_card` (`TicketCB action=card, id`) — карточка тикета с историей.
  - `cb_reply` (`TicketCB action=reply, id`) → `st_reply` — ответ админа:
    `tickets_service.reply_admin` (статус → `answered`), ретрансляция владельцу
    тикета (`support.reply_received` на его языке, best-effort), аудит
    `ticket.reply`, перерисовка карточки.
  - `cb_close` (`TicketCB action=close, id`) — `tickets_service.close_ticket`
    (статус → `closed`), уведомление владельца, аудит `ticket.close`.

### [app/handlers/admin/audit.py](./app/handlers/admin/audit.py)
Админский экран «📜 Аудит»: пагинированный просмотр лога админ-действий.

- `router = Router(name="admin_audit")`. Константа `_PAGE_SIZE = 10`.
- Helpers: `_safe`, `_admin_label(admin_id)` (резолвит имя действующего
  админа), `_target_suffix(entry)` (` → type#id`), `_details_suffix(entry)`
  (компактный JSON-блок), `_render(message, page, lang, edit)`.
- Хендлеры: `cb_open` (`AdminCB area=audit action=open` — первая страница),
  `cb_page` (`AuditCB action=open, page` — запрошенная страница). Кнопки
  prev/next показываются только при наличии страницы (через `audit_kb`).

## Пакет `app/keyboards/`

### [app/keyboards/\_\_init\_\_.py](./app/keyboards/__init__.py)
Маркер пакета inline-keyboards. Хранит admin- и user-клавиатуры в
отдельных подмодулях `admin.py` / `user.py`.

### [app/keyboards/admin.py](./app/keyboards/admin.py)
Inline-клавиатуры админ-флоу через `InlineKeyboardBuilder`. Все
builder-функции принимают keyword `lang=DEFAULT_LANG` и локализуют тексты
через `i18n.t` (namespace `admin.kb.*`); при `lang="ru"` строки идентичны
прежним хардкодам.

**CallbackData-фабрики** (prefix без `:` — это разделитель aiogram):
- `AdminCB(prefix="adm", area, action)` — навигация
  (`area` ∈ main/plans/promos/users/stats/**broadcast**/**tickets**/**audit**,
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
  в админском «Пользователи»; `action` ∈ search/card/revoke/toggle_admin/
  **grant_sub**/**toggle_block**. Для `revoke` — `id=sub_id`,
  `user_id=users.id`; для `grant_sub`/`toggle_block` — `id=users.id`.
- `GrantCB(prefix="admg", action, plan_id=0)` — выбор тарифа в ручной выдаче
  (`action=plan`, под `AdminGrantSub.waiting_plan` — не конфликтует с `PlanCB`).
- `TicketCB(prefix="admt", action, id=0)` — экран тикетов;
  `action` ∈ list/card/reply/close; `id=tickets.id`.
- `AuditCB(prefix="adma", action, page=0)` — пагинация аудита (`action=open`,
  `page` 0-based).
- `StatsCB(prefix="adms", action, field="")` — экран статистики;
  `action` ∈ open/period/refresh; `field` несёт период (`7d`/`30d`/`all`).

**Функции:**
- `admin_main_menu()` — 7 кнопок (Тарифы / Промокоды / Пользователи /
  Статистика / Рассылка / 💬 Тикеты / 📜 Аудит).
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
  (`☑` если `option.id ∈ selected`; пустой remark → fallback `Локация #<id>`);
  тап шлёт
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
- `user_card_kb(user_id, *, active_sub_id=None, is_admin=False,
  is_blocked=False)` — кнопки карточки пользователя: «Отозвать активную
  подписку» (если `active_sub_id`), «🎁 Выдать подписку», «Сделать/Снять
  админа», «🚫 Заблокировать»/«🟢 Разблокировать» (по `is_blocked`),
  «Найти другого», «В меню». Кнопки grant/block скрыты при `user_id == 0`
  (плейсхолдер «не найден»).
- `grant_plans_kb(plans)` — выбор тарифа для ручной выдачи (`GrantCB`).
- `tickets_list_kb(tickets)` — список открытых тикетов (`tickets`: пары
  `(ticket_id, label)`; тап → `TicketCB(action='card')`) + «В меню».
- `ticket_card_kb(ticket_id, *, is_closed=False)` — «✍ Ответить» / «✅ Закрыть
  тикет» (скрыты при `is_closed`) + «◀ К списку».
- `audit_kb(*, page=0, has_prev=False, has_next=False)` — prev/next (при
  наличии страницы) + «В меню».
- `stats_kb(active_period="30d")` — переключатель 7д/30д/Всё время
  (текущий помечен «· text ·»), «🔄 Обновить» (period в payload),
  «📥 Скачать CSV» (`StatsCB(action="export", field="all")`, `admin.export.btn`),
  «В меню».

callback_data всегда укладывается в Telegram-лимит 64 байта.

## Пакет `app/middlewares/`

### [app/middlewares/\_\_init\_\_.py](./app/middlewares/__init__.py)
Re-export `UserContextMiddleware`, `AdminOnlyMiddleware`, `BlockedUserMiddleware`.

### [app/middlewares/blocked.py](./app/middlewares/blocked.py)
Outer dispatcher-middleware `BlockedUserMiddleware(BaseMiddleware)`.

- `__call__` — извлекает `from_user` (через `user_ctx._extract_tg_user`), для
  апдейта без юзера пропускает. **Админы (`settings.ADMIN_IDS`) никогда не
  блокируются.** Для остальных вызывает `users_repo.is_blocked(conn, tg_id)`
  (узкий lookup, не зависит от `data['user']`); забаненному — короткий
  отказ (`blocked.refused`: реплай на Message / alert на CallbackQuery) и
  апдейт потребляется (`None`). При ошибке БД — fail-open (апдейт проходит).
- `_refuse(event)` — отправка отказа на message/callback из сырого Update.

Регистрируется ПЕРВЫМ (`dp.update.outer_middleware`), до
`UserContextMiddleware` — см. `handlers.register_routers`.

### [app/middlewares/user_ctx.py](./app/middlewares/user_ctx.py)
Outer dispatcher-middleware `UserContextMiddleware(BaseMiddleware)`.

- `_extract_tg_user(event)` — извлекает `from_user` из любого типа апдейта
  (Update.message / edited_message / channel_post / edited_channel_post /
  callback_query / inline_query / chosen_inline_result / shipping_query /
  pre_checkout_query / poll_answer / my_chat_member / chat_member /
  chat_join_request). Возвращает `None` если нет.
- `__call__` — открывает соединение через `get_conn`, вызывает
  `users_repo.get_or_create(conn, tg_id, username, first_name,
  language_code=tg_user.language_code)` и пишет результат в `data['user']`,
  а язык юзера — в `data['lang']` (хендлеры передают его в `i18n.t`). На
  отсутствии `from_user` или ошибке БД: `data['user'] = None`,
  `data['lang'] = DEFAULT_LANG` — апдейт продолжает движение.

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
- `AdminTicketReply(writing)` — единичный стейт ответа админа на тикет
  (`ticket_id` в FSM data); сообщение → `tickets_service.reply_admin` +
  ретрансляция владельцу.
- `AdminGrantSub(waiting_plan, waiting_days)` — wizard ручной выдачи
  подписки: выбор тарифа (`GrantCB`) → срок (число дней или «-» = срок
  тарифа); `user_id`/`plan_id`/`inbound_id` в FSM data.

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
- `build_import_links(sub_url) -> dict[str,str]` — deep-link-схемы импорта
  подписки в клиенты: `happ://import/<encoded>`,
  `v2rayng://install-config?url=<percent-encoded>`,
  `hiddify://import/<encoded>`, `streisand://import/<encoded>` (ключи
  `happ`/`v2rayng`/`hiddify`/`streisand`). Для пустого `sub_url` → `{}`. Telegram
  не принимает кастомные схемы в кнопках/href, поэтому показываются как копируемые
  `<code>`-блоки в гайде подключения.
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
- Helper `_reminder_text(kind, lang=DEFAULT_LANG)` — локализованный текст
  напоминания «истекает через 3 дня / завтра / сегодня» (ключ
  `reminder.<kind>` через `i18n.t`).
- Helper `_expired_text(lang=DEFAULT_LANG)` — финальное сообщение «подписка
  истекла» (ключ `reminder.expired`).
- Helper `_parse_iso(value) -> datetime` — парсит хранящиеся в БД
  ISO-строки (`YYYY-MM-DD HH:MM:SS` или с `+00:00`) в aware-datetime UTC.
- Helper `_days_left(expires_at, now) -> int` — целое число суток до
  дедлайна (отрицательное при просрочке; floor через `timedelta.days`).
- Helper `_kind_for_days_left(days_left) -> ReminderKind | None` —
  маппинг: `[3,4)` → `3d`, `[1,2)` → `1d`, `0` → `0d`, иначе `None`.
- Helper `_safe_send(bot, tg_id, text, reply_markup: InlineKeyboardMarkup | None = None)` —
  `bot.send_message` с глушением `TelegramAPIError` (юзер мог заблокировать
  бота). Опциональный `reply_markup` — inline-клавиатура (кнопка «Продлить»
  и трафик-алерты Ф4); при `None` поведение существующих вызовов не меняется.

- `async def expire_check_job(bot)` — раз в час: для каждой подписки из
  `subs_repo.list_expired_active(now)` вызывает
  `xui.update_client(enable=False)`, ставит `set_status(sub.id, 'expired')`,
  через `try_mark_notification_sent('expired')` гарантирует однократную
  отправку финального уведомления юзеру (`_expired_text(user.lang)`). Все
  ошибки (xui / БД / Telegram) логируются и не валят цикл.
- `async def reminders_job(bot)` — раз в сутки: `list_expiring_in(days=3)`,
  для каждой подписки вычисляет `_days_left`, маппит в `kind`, через
  `try_mark_notification_sent(sub_id, kind)` дедуплицирует и шлёт
  `_reminder_text(kind, user.lang)` (язык из `user.lang`) с прикреплённой
  `renew_reminder_kb(sub.id)` — кнопкой «🔁 Продлить в 1 тап»
  (`BuyCB(action='extend', sub_id=...)`), ведущей в существующий extend-флоу.
- `async def traffic_snapshot_job(bot)` — раз в 6 часов: для каждой
  `subs_repo.list_active(conn)` вызывает `xui.get_client_traffics(email)`,
  затем `subs_repo.add_traffic_snapshot(sub.id, up, down)`. После записи —
  `_maybe_alert_traffic(bot, sub, up+down)`: сравнивает накопленный трафик с
  квотой `plan.traffic_gb × _BYTES_PER_GB` и при пороге
  `settings.TRAFFIC_ALERT_PERCENT` (80) шлёт одноразовый алерт (`traffic.alert`)
  с `renew_reminder_kb`, дедуп через `subscription_notifications` kind
  `'traffic80'`. Безлимитные тарифы (`traffic_gb=0`), отсутствие плана или
  `percent=0` алерт пропускают. Каждый шаг изолирован try/except.
- `async def _maybe_alert_traffic(bot, sub, total) -> bool` — helper
  трафик-алерта (см. выше); возвращает `True`, если алерт отправлен.
- `async def auto_renew_job(bot)` — раз в сутки в 09:00 UTC (раньше reminders):
  fallback-автопродление списанием с баланса. Гейтится
  `settings.AUTO_RENEW_ENABLED`; затем `list_auto_renew_due(within_hours=24)`
  (только wallet-fallback подписки) и делегирует каждую `_renew_one_from_wallet`
  под per-sub try/except.
- `async def _renew_one_from_wallet(bot, sub) -> bool` — продлевает одну
  подписку: резолвит план+цену (`billing.calc_price`), `wallet.try_spend(ref=
  f'autorenew:<sub>:<expires_at>')` (replay-safe), при нехватке баланса — DM;
  на успех — `create_or_extend(extend_sub_id=sub.id)` (xui-first, рефанд на
  `XuiError`), синтетический payment `wallet:autorenew:<txn_id>`, DM
  `autorenew.renewed_dm`.
- `async def _alert_admins(bot, text)` — веерная рассылка health-алерта в DM
  каждому из `settings.ADMIN_IDS` + (если задан) `settings.SUPPORT_CHAT_ID`;
  per-recipient через `_safe_send` (best-effort).
- `async def health_check_job(bot)` — каждые ~30 минут: получает xui-клиент
  (ошибка получения = `down`), запускает `health_service.check_xui_health`,
  маппит результат в `'up'`/`'down'`, персистит через
  `health_repo.record(...)` (возвращает `changed`), обновляет
  `health_service.set_cached_status` для индикатора локаций и шлёт алерт
  админам (`health.alert_up`/`health.alert_down`) ТОЛЬКО при `changed=True` —
  ровно одно уведомление на смену up↔down, без спама. Тело в безопасной
  обёртке: любая ошибка логируется и не пробрасывается.
- Helper `_wrap(job, bot, name)` — closure-обёртка, которая ловит
  любые исключения job-а и логирует через loguru (чтобы один упавший
  job не остановил остальные).
- `def setup_scheduler(bot) -> AsyncIOScheduler` — создаёт scheduler
  с `timezone='UTC'` и регистрирует пять job-ов:
  - `expire_check`: `CronTrigger(minute=0)` каждый час; `coalesce=True`,
    `misfire_grace_time=30*60`, `max_instances=1`.
  - `reminders`: `CronTrigger(hour=10, minute=0)` раз в сутки;
    `coalesce=True`, `misfire_grace_time=6*60*60`, `max_instances=1`.
  - `traffic_snapshots`: `CronTrigger(hour='0,6,12,18', minute=5)`;
    `coalesce=True`, `misfire_grace_time=60*60`, `max_instances=1`.
  - `auto_renew`: `CronTrigger(hour=9, minute=0)` раз в сутки;
    `coalesce=True`, `misfire_grace_time=6*60*60`, `max_instances=1`.
  - `health_check`: `CronTrigger(minute='0,30')` каждые 30 минут;
    `coalesce=True`, `misfire_grace_time=10*60`, `max_instances=1`.
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

- Константы `_STARS_MIN = 1` (TG требует amount>=1), `_PAYLOAD_BYTE_LIMIT = 128`,
  `SUBSCRIPTION_PERIOD_SECONDS = 2_592_000` (30 дней — единственное
  допустимое значение `subscription_period` для нативных Star-подписок).
- Тип `InvoiceKind = Literal["buy", "topup", "gift", "sub"]` —
  дискриминатор вида invoice (ключ `"k"` в payload).
- Dataclass `InvoicePrice(stars, raw_discount, extra_days)`.
- Dataclass `InvoiceContext(plan_id, promo_id, inbound_id, sub_id,
  kind="buy", gift=0, topup=0)` (`frozen`, `slots`) — структурированный
  декод payload. **Итерируется** как legacy 4-tuple
  `(plan_id, promo_id, inbound_id, sub_id)` через `__iter__`, чтобы старые
  распаковки продолжали работать. `kind` — точка ветвления хендлеров
  оплаты (`buy`/`topup`/`gift`/`sub`).
- `def calc_price(plan, promo) -> InvoicePrice` — обёртка над
  `promos.compute_discount` + `max(_STARS_MIN, final_price)`.
- `def _encode_payload(obj) -> str` — общий сериализатор payload (компактный
  JSON + guard на `_PAYLOAD_BYTE_LIMIT`); используется всеми билдерами.
- `def build_invoice_payload(plan_id, promo_id, inbound_id, *, sub_id: int = 0) -> str` —
  payload `kind="buy"`: компактный JSON `{"p":..., "r": ... | null, "i": ..., "s": ...}`
  с короткими ключами (<128 байт даже для крупных id); **без** ключа `"k"`
  (legacy без `"k"` декодится как `buy`). Ключ `"s"` (sub_id-to-extend)
  **опускается целиком** при `sub_id == 0` (свежая покупка); legacy-payloads
  без `"s"` парсятся как `sub_id=0`.
- `def build_topup_payload(stars) -> str` — payload пополнения кошелька
  `{"k":"topup","t":stars}` (Ф2); проверяет `stars >= _STARS_MIN`.
- `def build_gift_payload(plan_id, inbound_id, promo_id=None) -> str` —
  payload покупки подарка `{"k":"gift","g":1,"p":...,"r":...|null,"i":...}` (Ф3).
- `def build_subscription_payload(plan_id, inbound_id, *, sub_id=0) -> str` —
  payload нативной Star-подписки `{"k":"sub","p":...,"i":...,"s":...?}` без
  promo-ключа (Ф4); `"s"` опускается при `sub_id=0`.
- `def parse_invoice_payload(payload) -> InvoiceContext` —
  обратная функция, возвращает `InvoiceContext` (итерируется как legacy
  4-tuple). Дискриминатор `"k"`: отсутствует → `kind="buy"` (вся
  legacy-совместимость); `topup` → плата за кошелёк (несёт `"t"`, без
  plan/inbound); `gift` → подарок (`g=1`); `sub` → нативная Star-подписка.
  Принимает как новые ключи (`p`/`r`/`i`/`s`), так и legacy
  (`plan_id`/`promo_id` без `i`/`s`); при отсутствии `i` — fallback на
  `settings.XUI_INBOUND_ID` с WARNING-логом; при отсутствии `s` — `sub_id=0`.
  `ValueError` на малформность и неизвестный `kind`; `promo_id=0`
  нормализуется в `None`.
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
- `async def create_subscription_invoice_link(bot, plan, *, inbound_id, sub_id=0) -> str` —
  нативная recurring Star-подписка через
  `bot.create_invoice_link(currency="XTR", provider_token="",
  subscription_period=SUBSCRIPTION_PERIOD_SECONDS=2592000,
  payload=build_subscription_payload(...))`. `subscription_period` есть
  ТОЛЬКО у `create_invoice_link`, не у `send_invoice`. Промо к recurring
  не применяются. Используется в Ф4.
- `async def send_gift_invoice(bot, chat_id, plan, promo, *, inbound_id) -> Message` —
  Stars-invoice на покупку подарочного кода. Та же цена что `send_invoice`
  (промо применяется), но payload через `build_gift_payload` (`kind="gift"`,
  `gift=1`) — `on_successful_payment` минтит код вместо подписки покупателю.
  Всегда новая подписка получателю (без `sub_id`/extend).
- `async def send_topup_invoice(bot, chat_id, stars, *, lang=DEFAULT_LANG) -> Message` —
  Stars-invoice пополнения кошелька. Payload через `build_topup_payload`
  (`kind="topup"`), без plan/inbound. `stars=max(_STARS_MIN, stars)`,
  `LabeledPrice=stars`, `currency="XTR"`. Тексты title/label/description
  локализованы через `t()` (namespace `wallet.invoice_*`). Кредит баланса
  происходит позже в `on_successful_payment` при подтверждении оплаты.

### [app/services/wallet.py](./app/services/wallet.py)
Сервис баланса в Stars поверх `app.db.repos.wallet` — идемпотентность по `ref`.

- `async def credit(conn, user_id, amount, *, type, ref=None) -> bool` —
  начисление `+amount` (через `wallet_repo.add`). `False` при дубле `ref`
  (повторный top-up/реферал-бонус не начисляет дважды), `ValueError` при
  `amount <= 0`.
- `async def try_spend(conn, user_id, amount, *, ref) -> bool` — атомарное
  списание под `app.db.engine.transaction` (`BEGIN IMMEDIATE`): пересчёт
  баланса + raw `INSERT 'spend'` с `amount=-amount` в одной транзакции (не
  использует `wallet_repo.add`, чтобы не коммитить рано и не разрывать границу
  транзакции). `False` при нехватке баланса (overdraw) ИЛИ дубле `ref` (replay —
  `IntegrityError` ловится снаружи `transaction`). `BEGIN IMMEDIATE` сериализует
  писателей → защита от double-spend; детерминированный `ref` → защита от replay.
  `ref` обязателен; `ValueError` при `amount <= 0`.

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
- `class TrialAlreadyUsedError(Exception)` — поднимается `activate_trial`,
  когда у юзера уже есть trial (handler маппит в локализованное сообщение).
- `async def activate_trial(conn, xui, user, *, inbound_id, days, traffic_gb) -> Subscription` —
  провижинит пробную подписку (один trial на юзера). Переиспользует
  `_provision` (xui-first) с `plan_id=None`, `is_trial=True`. Защита в два
  слоя: (1) дешёвый pre-check `subs_repo.has_trial` → `TrialAlreadyUsedError`
  до обращения к панели (без orphan-клиента); (2) backstop — `IntegrityError`
  от partial-unique `idx_subscriptions_one_trial` при гонке → тот же
  `TrialAlreadyUsedError`. `_provision` принимает доп. kwarg `is_trial=False`
  и прокидывает его в `subs_repo.create`.
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

### [app/services/exports.py](./app/services/exports.py)
CSV-экспорт основных таблиц для админ-дашборда (кнопка «📥 Скачать CSV»).

- `async def export_payments_csv(conn) -> bytes`,
  `export_subscriptions_csv(conn) -> bytes`, `export_users_csv(conn) -> bytes`.
- Stdlib `csv` + `io.StringIO`, кодировка `utf-8-sig` (BOM — корректная
  кириллица в Excel). Каждый экспортёр пишет фиксированный заголовок, затем
  `SELECT ... ORDER BY id`; `NULL` → пустая ячейка. Экспорт подписок НЕ включает
  `xui_client_uuid` (секрет подключения). Потребитель — `cb_export` в
  [app/handlers/admin/stats.py](./app/handlers/admin/stats.py).

### [app/services/health.py](./app/services/health.py)
Проба доступности 3x-ui панели + process-local snapshot для индикатора локаций.

- `async def check_xui_health(xui) -> tuple[bool, str | None]` — лёгкая проба
  через `list_inbounds`, обёрнутая в `asyncio.wait_for(timeout=10s)`. Ловит
  `TimeoutError` / `XuiError` / любое исключение → `(False, reason)`; иначе
  `(True, None)`. Проба никогда не пробрасывает исключение.
- `def get_cached_status() -> HealthState | None` /
  `def set_cached_status(status)` — process-local snapshot последнего состояния
  (`'up'`/`'down'`/`None`). Обновляется scheduler-job-ом после каждой пробы;
  читается `location_indicator` в клавиатурах для 🟢/🔴/⚪ без обращения к панели.

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

### [app/services/referrals.py](./app/services/referrals.py)
Сервис реферальной программы.

- `def parse_ref_arg(arg) -> int | None` — извлекает tg_id инвайтера из
  `ref_<tg_id>` (None при невалидном/нечисловом/нулевом значении).
- `async def register_referral(conn, *, referrer_tg_id, referred) -> bool` —
  привязывает приглашённого к инвайтеру: защита self-referral
  (`referrer.id == referred.id`), unknown-inviter (нет юзера с таким tg_id),
  «уже привязан» (повторный `/start` — no-op, первый инвайтер сохраняет
  кредит). Под капотом `referrals_repo.create_pending` (INSERT OR IGNORE).
- `async def reward_referrer_after_first_payment(conn, bot, *, referred) -> bool`
  — после первого платежа приглашённого: skip если `REFERRAL_BONUS_STARS=0`;
  атомарный `try_mark_rewarded` (None при гонке/уже-награждён → stop);
  `wallet.credit(referrer_id, bonus, type='referral_bonus',
  ref=f"referral:{referred_id}")` (вторая идемпотентность по UNIQUE wallet ref)
  + DM пригласившему (best-effort). Вызывается в `buy.on_successful_payment`
  (Step 6b, best-effort, не ломает доставку ключей).

### [app/services/gifts.py](./app/services/gifts.py)
Сервис подарочных подписок.

- `class GiftRedeemError(Exception)` с `reason: "not_found" | "not_active"`.
- `async def make_gift_code(conn, *, plan_id, inbound_id, buyer_id,
  payment_id=None) -> GiftCode` — минт кода `GIFT-`+8 hex (`secrets.token_hex`),
  retry до 5 раз на `IntegrityError` (UNIQUE-коллизия кода).
- `async def redeem_gift(conn, xui, *, code, redeemer) -> tuple[GiftCode,
  Subscription]` — claim-first с компенсацией: `get_by_code` (active?), резолв
  плана (deleted → `GiftRedeemError("not_active")` до claim), `try_claim`
  (атомарный `active→redeemed`; None → `not_active`),
  `create_or_extend(extend_sub_id=None, inbound_id=code.inbound_id, promo=None)`
  (xui-first), `link_subscription`. При `XuiError` — `set_status(...,'active')`
  (компенсация, код снова redeemable) + re-raise.

### [app/services/tickets.py](./app/services/tickets.py)
Сервис двустороннего флоу тикетов поддержки. Владеет машиной статусов
(хендлеры не знают о переходах):

- `async def open_ticket(conn, user, text, *, tg_message_id=None) ->
  tuple[Ticket, TicketMessage]` — reuse-or-create: переиспользует
  non-closed тикет юзера или создаёт новый; добавляет сообщение и ставит
  статус `'open'`.
- `async def reply_user(conn, ticket_id, text, *, tg_message_id=None) ->
  TicketMessage` — follow-up юзера в существующий тикет, статус `'open'`.
- `async def reply_admin(conn, ticket_id, text, *, tg_message_id=None) ->
  TicketMessage` — ответ админа, статус `'answered'`.
- `async def close_ticket(conn, ticket_id)` — статус `'closed'` (идемпотентно).

Framework-agnostic (только БД); ретрансляцию в Telegram делают хендлеры.

### [app/services/audit.py](./app/services/audit.py)
Сервис аудит-трейла админ-действий.

- `async def log_action(conn, admin_id, action, target_type=None,
  target_id=None, details=None) -> AuditEntry | None` — записывает действие
  в `audit_log`. **Crash-safe**: любое исключение логируется и проглатывается
  (возврат `None`), чтобы аудит-фейл никогда не ломал само админ-действие.
  `details` (mapping) сериализуется в компактный JSON (fallback `str(...)`).
- `_serialise_details(details) -> str | None` — JSON-сериализация details.

### [app/bot_meta.py](./app/bot_meta.py)
Кэш идентичности бота для построения deep-link-ов.

- `async def get_bot_username(bot) -> str` — `Bot.get_me()` один раз,
  мемоизация по `bot.id` (для ссылок `?start=ref_/gift_`); fallback `''`.
- `def clear_cache()` — сброс кэша (для тестов).

## Пакет `app/handlers/user/`

Пользовательский флоу: меню, помощь, покупка, активация промокода, пробный
период, рефералы, подарки, поддержка. Без gate-middleware — доступен всем.

### [app/handlers/user/\_\_init\_\_.py](./app/handlers/user/__init__.py)
Агрегатор `user_router`. Подключает в порядке
`menu → my_subscription → buy → promo → trial → referral → gift → support →
wallet → language → help`.

### [app/handlers/user/menu.py](./app/handlers/user/menu.py)
Главное меню пользователя.

- `router = Router(name="user_menu")`.
- `_has_active_subscription(user_db_id) -> bool` — обёртка над
  `subs_repo.get_active_for_user`.
- `_can_trial(user_db_id) -> bool` — `TRIAL_DAYS>0 AND not has_trial`
  (показ кнопки «🎁 Пробный период»).
- `_send_main_menu(message, user, edit=bool)` — единая точка рендера
  (`edit_text` или `answer`); прокидывает `can_trial` в `user_main_menu`.
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
    для нативных Star-подписок (`tg_sub_charge_id` задан) — отдельная
    строка «⏹ Отменить автопродление» (`SubCB(action='cancel_renew')`)
    при `auto_renew=1` или «🔁 Включить автопродление»
    (`SubCB(action='enable_renew')`) при отменённом; внизу «◀ В меню»
    (`UserCB(area='menu')`). Кнопка «Продлить» скрывается для неактивных,
    так как `buy.cb_pick_action_extend` отклоняет non-active подписки.
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
  - `cb_cancel_auto_renew` (`SubCB action=cancel_renew`) /
    `cb_enable_auto_renew` (`SubCB action=enable_renew`) — отмена /
    повторное включение автопродления нативной Star-подписки через общий
    `_toggle_auto_renew(cancel: bool)`. Гарантии: ownership + наличие
    `tg_sub_charge_id`. Вызывает `bot.edit_user_star_subscription(user_id,
    telegram_payment_charge_id=sub.tg_sub_charge_id, is_canceled=cancel)`,
    затем зеркалит локально `set_auto_renew(not cancel)` и перерендеривает
    экран. На `TelegramAPIError` — алерт `autorenew.cancel_failed` без
    изменения локального флага (нет drift'а локального/удалённого состояния).

### [app/handlers/user/help.py](./app/handlers/user/help.py)
Инструкция по подключению.

- `router = Router(name="user_help")`.
- Константа `_HELP_TEXT` — три рекомендуемых клиента (v2rayNG для Android,
  Streisand для iOS, Hiddify для desktop) и три способа импорта
  (vless URI, Subscription URL, QR).
- `cb_help` (`UserCB area=help`) — `edit_text(_HELP_TEXT, back_to_menu_kb)`.

### [app/handlers/user/_keys.py](./app/handlers/user/_keys.py)
Helper для выдачи ключей юзеру. Используется и в `buy.py`, и в `promo.py`.

- `def build_howto_text(sub_url, lang=DEFAULT_LANG) -> str` — собирает
  локализованный гайд «📲 Как подключиться» (ключи `keys.howto.*`, RU+EN; первым
  идёт Happ как кросс-платформенный клиент, у его блока есть fallback на ручное
  добавление Subscription URL) с per-client deep-link-ссылками импорта
  (Happ/v2RayNG/Hiddify/Streisand) из `build_import_links` в копируемых
  `<code>`-блоках + manual-fallback. Для пустого `sub_url` → `''`.
- `async def deliver_keys(bot, xui, chat_id, sub, *, header, lang) -> None` —
  отправляет сообщения: (1) summary с expires_at и vless URI в `<code>`;
  (2) QR PNG через `bot.send_photo` (`BufferedInputFile` из `make_qr_png`);
  (3) Subscription URL + клавиатура с URL-кнопкой `Subscription URL`
  (vless:// не идёт в URL-кнопке — Telegram такие схемы не принимает) +
  `subscription_kb(sub.id)`; (4) при наличии sub_url — сообщение-гайд
  `build_howto_text` со ссылками импорта. При `XuiError` на `get_inbound`
  логирует и продолжает без vless URI; QR строится по sub_url.

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
  - `_can_pay_from_balance(user, plan, promo) -> bool` — `True`, если
    `wallet_repo.balance(user.id) >= billing.calc_price(plan, promo).stars`
    (`False` при `user=None`). Вызывается во всех рендерах confirm-карточки
    и определяет показ кнопки «💰 Оплатить с баланса» в `confirm_kb`.
  - `_credit_topup(message, user, charge_id, total_amount, topup_stars, lang)` —
    финализация пополнения кошелька (`kind="topup"`). Два слоя идемпотентности:
    `payments.create` с реальным `telegram_charge_id` (UNIQUE) + `wallet.credit`
    с `ref=f"topup:{charge_id}"` (partial-unique) → баланс кредитуется ровно один
    раз даже при повторном `successful_payment`. Кредитует фактически списанный
    `total_amount` (mismatch с payload логируется WARNING). При успехе шлёт
    `wallet.topup_success` с новым балансом; при replay молчит.
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
  - `cb_subscribe` (`action=sub`) — нативная recurring Star-подписка.
    Показывается на confirm-карточке кнопкой «🔁 Подписка (автопродление)»
    (`confirm_kb(offer_subscription=...)`) только для подходящего 30-дневного
    тарифа при новой не-gift покупке (`_offers_subscription`). Гейтится
    `AUTO_RENEW_ENABLED`; ре-валидирует план + inbound allow-list, затем
    `billing.create_subscription_invoice_link(...)` (kind='sub',
    `subscription_period=2592000`) и редактирует сообщение, показывая
    `subscription_link_kb(link)` (URL-кнопку оформления).
  - `cb_pay_from_balance` (`action=balance`) — оплата подписки с баланса
    кошелька без Telegram-инвойса. Ре-валидация plan/promo/inbound/ownership
    (как `cb_confirm`); `wallet_service.try_spend(ref=f"buy:{callback.id}")`
    (callback.id уникален на тап → дедуп редоставки) списывает
    `calc_price.stars` под `BEGIN IMMEDIATE`; при нехватке — alert
    `wallet.insufficient`. После списания `wallet_repo.get_by_ref` →
    `synthetic_charge_id=f"wallet:{txn_id}"`; `subs_service.create_or_extend`;
    при `XuiError` — компенсирующий `wallet.credit(type="refund",
    ref=f"refund:{txn_id}")` + `wallet.pay_failed`; иначе синтетический
    `payments.create(telegram_charge_id="wallet:{txn_id}")` (для stats/
    total_stars), `promos.apply` (best-effort) и `deliver_keys`
    (`wallet.paid_from_balance_header`).
- Stateless-обработчики платежа:
  - `on_pre_checkout` (`pre_checkout_query`) — `parse_invoice_payload`
    возвращает 4-tuple `(plan_id, promo_id, inbound_id, sub_id)`;
    read-only проверки plan/promo; при `sub_id == 0` дополнительно
    `inbound_id ∈ get_inbounds(plan_id)`; при `sub_id > 0` проверяется
    ownership + active-status подписки (`inbound_id` не валидируется,
    т.к. extend всегда наследует существующий); answer `ok=True/False`.
  - `cb_gift_buy` (`GiftCB action=buy`, кнопка «🎁 Подарить подписку») — вход
    в покупку подарка: `state.clear()`, `gift=1`+`sub_id=0` в FSM, рендер
    `plans_kb` (всегда new-sub flow; action-экран «продлить/новая» пропущен).
    Поле `gift` протянуто через FSM и `confirm_kb` во всех new-sub ветках
    (`cb_pick_plan`/`cb_pick_inbound`/`cb_apply_promo`/`msg_promo_code`); в
    `cb_confirm` при `gift=1` шлёт `billing.send_gift_invoice` (а не обычный).
  - `_mint_gift(message, bot, user, charge_id, total_amount, ctx_plan_id,
    ctx_promo_id, ctx_inbound_id, lang)` — финализация покупки подарка:
    `payments.create` (UNIQUE charge_id гейтит минт), `make_gift_code(payment_id)`
    внутри not-duplicate ветки, DM покупателю код + ссылку `?start=gift_<code>`
    (bot username через `bot_meta.get_bot_username`). Подписка покупателю НЕ
    провижинится.
  - `_handle_recurring(message, bot, user, charge_id, total_amount, ctx,
    is_first, sub_expiration, lang)` — финализация нативной recurring
    Star-подписки (`kind='sub'`). **Первый charge** (`is_first_recurring`):
    `create_or_extend(extend_sub_id=None)` + `set_auto_renew(True,
    tg_sub_charge_id=charge_id)` + payment + `deliver_keys`. **Очередной charge**:
    `get_active_auto_renew_for(user, plan)`, extend к
    `subscription_expiration_date` (Unix→UTC) + `update_client(expiryTime=...)` +
    payment + DM `autorenew.renewed_dm`. Идемпотентность — UNIQUE charge_id.
    Хелперы `_expiry_ms_from_unix` / `_datetime_from_unix`.
  - `on_successful_payment` (`F.successful_payment`) — идемпотентен по
    `payments_repo.get_by_charge_id`; парсит payload. При `ctx.kind=="topup"`
    делегирует в `_credit_topup` (пополнение кошелька) и возвращается. При
    `ctx.kind=="gift"` (или `ctx.gift`) делегирует в `_mint_gift` (минт кода
    вместо подписки) и возвращается. При `payment.is_recurring is True` или
    `ctx.kind=="sub"` делегирует в `_handle_recurring` (нативная Star-подписка)
    и возвращается. Иначе (buy/extend) логирует
    WARNING для legacy-payload без `i` (fallback на
    `settings.XUI_INBOUND_ID`); refetch plan/promo;
    `subs_service.create_or_extend(..., inbound_id=..., extend_sub_id=<sub_id or None>)`
    (xui-first; на `XuiError` фиксирует платёж без подписки и
    уведомляет юзера; на `ValueError` от `_provision` — подписка
    больше не подходит для extend — пишет в логи и уведомляет);
    `payments_repo.create` (`IntegrityError` на duplicate
    игнорируется; `subscription_id` ссылается на (новую или
    extended) подписку); `promos.apply` (best-effort); реферальная награда
    `referrals_service.reward_referrer_after_first_payment` (Step 6b,
    best-effort); `deliver_keys` с заголовком, отражающим extend vs new.

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

### [app/handlers/user/wallet.py](./app/handlers/user/wallet.py)
Роутер экрана «👛 Кошелёк» (`router = Router(name="user_wallet")`),
зарегистрирован в `user/__init__.py` после `promo`.

- Helpers `_txn_label(txn, lang)` (локализованная метка типа транзакции из
  `wallet.type_<type>`) и `_render_wallet_text(balance, txns, lang)`
  (заголовок + строка баланса + история; строка истории —
  `<sign><abs amount>⭐ · <label>`, знак `+`/`−` по знаку `amount`).
- `cb_open` (`WalletCB action=open`, кнопка «👛 Кошелёк» из `user_main_menu`) —
  `wallet_repo.balance` + `list_for_user(limit=20)`, рендер `wallet_screen_kb`
  (кнопка «➕ Пополнить» только при непустых `WALLET_TOPUP_PRESETS`). При
  `user=None` — alert.
- `cb_topup` (`WalletCB action=topup`) — меню пресетов `wallet_topup_kb` либо
  `wallet.no_presets` при пустом списке.
- `cb_pick` (`WalletCB action=pick, stars=...`) — `billing.send_topup_invoice`
  для выбранной суммы (кредит баланса происходит позже в
  `on_successful_payment`). Все тексты — через `t()` (namespace `wallet.*`).

### [app/handlers/user/trial.py](./app/handlers/user/trial.py)
Роутер активации пробного периода (`router = Router(name="user_trial")`),
зарегистрирован в `user/__init__.py` после `promo`.

- Helpers `_options_to_jsonable`, `_trial_enabled_for(user)`
  (`TRIAL_DAYS>0 AND not has_trial`), `_activate_and_deliver(...)`
  (`activate_trial(days=TRIAL_DAYS, traffic_gb=TRIAL_TRAFFIC_GB)` → `deliver_keys`;
  маппинг `TrialAlreadyUsedError` → alert, `XuiError` → apology, clear state).
- `cb_open` (`TrialCB action=open`, кнопка «🎁 Пробный период» из меню) —
  re-check гейта; `list_user_inbounds`: 1 inbound → авто-активация, иначе
  `TrialFlow.choosing_inbound` + `inbound_select_kb`.
- `cb_pick_inbound` (`InboundCB action=pick` под `TrialFlow.choosing_inbound`)
  — валидирует offered inbound → активация.
- `cb_back_inbound` (`InboundCB action=back`) — отмена в главное меню.

### [app/handlers/user/referral.py](./app/handlers/user/referral.py)
Роутер экрана «👥 Пригласить друга» (`router = Router(name="user_referral")`),
зарегистрирован после `trial`.

- `_build_ref_link(bot_username, tg_id)` → `https://t.me/<bot>?start=ref_<tg_id>`.
- `cb_open` (`ReferralCB action=open`) — строит ссылку (username через
  `bot_meta.get_bot_username`, кэш per `bot.id`), показывает `count_for_referrer`
  + рекламу бонуса (`referral.screen_body` при `REFERRAL_BONUS_STARS>0`, иначе
  `referral.screen_body_no_bonus`). Тексты `referral.*`.

### [app/handlers/user/gift.py](./app/handlers/user/gift.py)
Роутер активации подарка (`router = Router(name="user_gift")`),
зарегистрирован после `referral`.

- `async def notify_gift_buyer(bot, gift)` — DM покупателю об активации кода
  (best-effort; shared с deep-link путём в `start.py`).
- `cb_redeem` (`GiftCB action=redeem`, кнопка «🎁 У меня есть подарок») —
  вход в `GiftRedeem.waiting_code`, промпт ввода кода.
- `msg_code` (под `GiftRedeem.waiting_code`) — `redeem_gift(code, redeemer)`:
  при `GiftRedeemError` маппинг `not_found`/`not_active` в сообщение (остаётся
  в state), при `XuiError` — apology; при успехе `deliver_keys` получателю +
  `notify_gift_buyer` + clear state. Тексты `gift.*`. (Активация по deep-link
  `gift_<code>` — в `start.cmd_start`.)

### [app/handlers/user/support.py](./app/handlers/user/support.py)
Роутер поддержки (`router = Router(name="user_support")`), зарегистрирован
после `gift`. FSM `SupportFlow.writing`.

- `_safe`, `_user_label(user)` — компактная подпись юзера для уведомления.
- `async def notify_admins(bot, *, ticket_id, user, text)` — fan-out нового
  сообщения тикета: DM каждому `settings.ADMIN_IDS` и (если задан)
  `settings.SUPPORT_CHAT_ID`; best-effort per-recipient.
- `cb_open` (`SupportCB action=open`, кнопка «❓ Поддержка») — интро + промпт,
  вход в `SupportFlow.writing`.
- `st_message` (под `SupportFlow.writing`) — фиксирует сообщение через
  `tickets_service.open_ticket` (reuse-or-create + `tg_message_id`),
  уведомляет админов, подтверждает юзеру, чистит state. Тексты `support.*`.
  (Ответ админа доставляется юзеру из `handlers.admin.tickets`.)

### [app/handlers/user/language.py](./app/handlers/user/language.py)
Роутер выбора языка интерфейса (`router = Router(name="user_language")`),
зарегистрирован в `user/__init__.py` перед `help`.

- `cb_open` (`LangCB action=open`, кнопка «🌐 Язык / Language» из
  `user_main_menu`) — рисует `language_menu_kb(current)` (текущий язык
  берётся из `user.lang`) с текстом `lang.choose`.
- `cb_set` (`LangCB action=set, lang=<code>`) — валидирует код против
  `SUPPORTED_LANGS` (на неизвестном — alert `lang.unsupported`),
  сохраняет язык через `users_repo.set_lang`, перерисовывает меню уже на
  новом языке и отвечает `lang.changed`. Текущий язык каждого апдейта
  доступен хендлерам через `data['lang']` (middleware), глобальный стейт
  не нужен.

## Пакет `app/i18n/`
Собственная dependency-free локализация. Причина не использовать
aiogram gettext: тесты дёргают хендлеры напрямую без middleware-контекста,
а чистая функция `t(key, lang, **params)` остаётся тестируемой. Дефолт —
русский, чтобы legacy-вызовы без `lang` давали прежние RU-строки.

### [app/i18n/\_\_init\_\_.py](./app/i18n/__init__.py)
Публичный API:
- `t(key, lang=None, /, **params)` — перевод ключа с безопасным
  `format_map` (резолв `lang → en → сам key`; никогда не падает,
  пропущенный плейсхолдер рендерится как `{name}` через `_SafeDict`).
  Плюральный dict-ключ, запрошенный через `t`, возвращает сам key.
- `pluralize(key, n, lang=None, /, **params)` — выбор плюральной формы по
  словарю категорий `one/few/many/other`; в шаблон прокидывается `n`.
- `resolve_lang(language_code)` — нормализация Telegram-кода (`en-US→en`,
  `zh-Hans→zh`) к одному из `SUPPORTED_LANGS`, иначе `DEFAULT_LANG`.
- Константы: `SUPPORTED_LANGS=(ru,en,uk,fa,zh)`, `DEFAULT_LANG="ru"`,
  `FALLBACK_LANG="en"`, `LANG_NAMES` (флаг + самоназвание языка).

### [app/i18n/catalog.py](./app/i18n/catalog.py)
Собирает `CATALOG {lang: {key: value}}` из модулей `locales/*`.
`lookup(key, lang)` реализует политику резолва `lang → en` (FALLBACK),
возвращает `str | dict | None` (к raw key не падает — этот шаг в `t()`).

### [app/i18n/plural.py](./app/i18n/plural.py)
Реестр плюральных селекторов. `plural_category(n, lang) → one/few/many/other`.
RU-селектор зеркалит `_pluralize_subs` из `my_subscription.py` (3 формы
1 / 2-4 / 5-20); `uk` использует RU-правило; `en` — one/other; остальные —
`_plural_other` (всегда `other`).

### [app/i18n/locales/](./app/i18n/locales/)
Каталоги сообщений. `ru.py` — источник истины (строки 1:1 с прежними
хардкодами; namespace'ы `menu.*`, `help.*`, `keys.*`, `mysub.*`, `buy.*`,
`promo.*`, `reminder.*`, `wallet.*`, `admin.*`/`admin.kb.*`, `kb.*`, `lang.*`,
`trial.*`, `referral.*`, `gift.*`, `blocked.*`, `support.*`,
`admin.tickets.*`, `admin.grant.*`, `admin.ban.*`, `admin.audit.*`).
`wallet.*` покрывает инвойс пополнения, экран Кошелёк, историю/типы транзакций
и оплату с баланса. `en.py` — полный fallback (покрывает все ключи RU).
`uk.py`/`fa.py`/`zh.py` — заглушки (пустые `MESSAGES`), ключи фоллбекаются на `en`.

## Пакет `app/keyboards/` — пользовательские клавиатуры

### [app/keyboards/user.py](./app/keyboards/user.py)
Inline-клавиатуры юзерского флоу.

**CallbackData-фабрики:**
- `UserCB(prefix="u", area)` — area ∈ menu/help/my/cancel.
- `BuyCB(prefix="ub", action, plan_id=0, promo_id=0, inbound_id=0, sub_id=0,
  gift=0)` — action ∈ open/plan/apply_promo/confirm/balance/sub/cancel/extend/new.
  `sub` — оформление нативной recurring Star-подписки (`buy.cb_subscribe`).
  Поле `inbound_id` пробрасывается через шаги после выбора inbound (`0` =
  шаг был автоматически пропущен из-за единственного inbound в
  allow-list). Поле `sub_id` (>0) несёт id подписки, которую надо
  продлить (extend-ветка action-экрана и кнопка «🛒 Продлить #N» с
  `my_subscription`); `0` = новая подписка / n/a. Поле `gift` (`1`) помечает
  покупку подарка (минт кода вместо подписки). Packed payload:
  `ub:<action>:<plan_id>:<promo_id>:<inbound_id>:<sub_id>:<gift>`.
- `TrialCB(prefix="ut", action)` — action ∈ open (кнопка «🎁 Пробный период»;
  выбор inbound переиспользует `InboundCB` под `TrialFlow.choosing_inbound`).
- `ReferralCB(prefix="ur", action)` — action ∈ open (экран «👥 Пригласить друга»).
- `GiftCB(prefix="ug", action)` — action ∈ buy (покупка подарка) / redeem
  (активация «🎁 У меня есть подарок»).
- `SupportCB(prefix="usup", action)` — action ∈ open (кнопка «❓ Поддержка»;
  вход в `SupportFlow.writing`).
- `InboundCB(prefix="inb", action, plan_id=0, promo_id=0, inbound_id=0)` —
  action ∈ pick/back. Используется и в buy-флоу (`plan_id>0`), и в
  free-days promo-флоу (`plan_id=0`, `promo_id>0`); хендлер маршрутизирует
  по тому, какой id ненулевой.
- `SubCB(prefix="us", action, sub_id=0)` — action ∈
  keys/back/cancel_renew/enable_renew. `cancel_renew` / `enable_renew` —
  отмена / включение автопродления нативной Star-подписки
  (`my_subscription.cb_cancel_auto_renew` / `cb_enable_auto_renew`).
- `LangCB(prefix="lng", action, lang="")` — action ∈ open/set. `open`
  открывает меню выбора языка; `set` применяет язык из поля `lang`.
- `PromoActCB(prefix="up", action, inbound_id=0, sub_id=0)` —
  action ∈ open/extend/new/cancel. Поле `sub_id>0` несёт id подписки,
  которую нужно продлить через free_days промо (выбор на
  `promo_action_kb`); `0` = новая подписка / n/a. Packed payload:
  `up:<action>:<inbound_id>:<sub_id>` (например `up:open:0:0`,
  `up:extend:0:42`).
- `WalletCB(prefix="uw", action, stars=0)` — action ∈ open/topup/pick.
  `open` открывает экран Кошелёк, `topup` — меню пресетов, `pick` несёт
  выбранную сумму `stars` для top-up-инвойса.

**Функции:** все builder'ы принимают keyword `lang=DEFAULT_LANG` и
локализуют тексты через `i18n.t` (namespace'ы `menu.*`/`kb.*`); при
`lang="ru"` строки идентичны прежним хардкодам.
- `user_main_menu(*, has_subscription, can_trial=False, lang=DEFAULT_LANG) -> InlineKeyboardMarkup` —
  «Моя подписка» / «Купить» / [«🎁 Пробный период» (`TrialCB(action="open")`,
  только при `can_trial`)] / «👛 Кошелёк» (`WalletCB(action="open")`) /
  «Активировать промокод» / «👥 Пригласить друга» (`ReferralCB(action="open")`) /
  «🎁 Подарить подписку» (`GiftCB(action="buy")`) / «🎁 У меня есть подарок»
  (`GiftCB(action="redeem")`) / «❓ Поддержка» (`SupportCB(action="open")`) /
  «Помощь» / «🌐 Язык / Language» (`LangCB(action="open")`). Порядок первых
  двух меняется по флагу. `can_trial` = `TRIAL_DAYS>0 AND not has_trial`
  (вычисляется caller-ом).
- `back_to_menu_kb(lang=DEFAULT_LANG)` — одна кнопка «◀ В меню».
- `cancel_kb(lang=DEFAULT_LANG)` — одна кнопка «✖ Отмена» (cancel-таргет — `UserCB(area=cancel)`).
- `plans_kb(plans, lang=DEFAULT_LANG)` — один пункт на тариф (`title · Nд · M⭐`) + «В меню».
- `location_indicator(lang=DEFAULT_LANG) -> str` — маппит process-local
  health-snapshot (`health_service.get_cached_status`, обновляется
  `health_check_job` каждые ~30 мин) в маркер 🟢 (up) / 🔴 (down) / ⚪
  (None/unknown) через ключи `location.indicator_*`. Синхронный; используется
  `inbound_select_kb` для префикса каждой локации.
- `inbound_select_kb(plan_id, options, promo_id=0, lang=DEFAULT_LANG)` — single-select
  inbounds: одна кнопка на `InboundOption` с текстом
  `<indicator> <remark> (port <port>)` (индикатор из `location_indicator`,
  remark с fallback `Локация #<id>` через `kb.inbound_fallback_remark`),
  callback `InboundCB(action="pick", plan_id, promo_id, inbound_id=option.id)`.
  Внизу «◀ Назад» (`InboundCB(action="back", plan_id, promo_id)`).
- `confirm_kb(plan_id, promo_id=0, inbound_id=0, *, sub_id=0,
  can_pay_from_balance=False, gift=0, offer_subscription=False,
  lang=DEFAULT_LANG)` — «Оплатить»
  (`BuyCB(action="confirm", plan_id, promo_id, inbound_id, sub_id, gift)`) /
  «💰 Оплатить с баланса» (только при `can_pay_from_balance=True` И `not gift`,
  `BuyCB(action="balance", ...)`) / «🔁 Подписка (автопродление)» (только при
  `offer_subscription=True` И `not gift` И `sub_id==0`,
  `BuyCB(action="sub", plan_id, inbound_id)`) / «Применить промокод» (скрыта
  если `promo_id≠0`; пробрасывает `inbound_id`, `sub_id`, `gift`) / «Отмена».
  `gift=1` помечает invoice как покупку подарка (мастер тот же, но в
  `cb_confirm` шлётся `send_gift_invoice`).
  `sub_id>0` означает, что invoice — это продление конкретной подписки
  (extend-ветка): значение прокидывается в `billing.send_invoice(sub_id=...)`,
  далее в payload, далее в `subs_service.create_or_extend(extend_sub_id=...)`.
- `subscription_link_kb(url, lang=DEFAULT_LANG)` — URL-кнопка
  «🔁 Подписка (автопродление)» (`url=` на invoice-ссылку
  `billing.create_subscription_invoice_link`) + «◀ В меню». Используется
  `buy.cb_subscribe`.
- `renew_reminder_kb(sub_id, lang=DEFAULT_LANG)` — одиночная кнопка
  «🔁 Продлить в 1 тап» (`BuyCB(action="extend", sub_id=...)`). Прикрепляется
  `reminders_job` к напоминаниям и `traffic_snapshot_job` к трафик-алертам.
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
- `subscription_kb(sub_id, lang=DEFAULT_LANG)` — «Получить ключ ещё раз» / «◀ В меню».
- `language_menu_kb(current=DEFAULT_LANG)` — меню выбора языка: по строке
  на каждый язык из `SUPPORTED_LANGS` (метка из `LANG_NAMES`, текущий с
  префиксом ✅), callback `LangCB(action="set", lang=<code>)`; внизу
  «◀ В меню».
- `wallet_screen_kb(*, has_presets, lang=DEFAULT_LANG)` — экран Кошелёк:
  кнопка «➕ Пополнить» (`WalletCB(action="topup")`, только при `has_presets`)
  + «◀ В меню».
- `wallet_topup_kb(presets, lang=DEFAULT_LANG)` — меню пресетов пополнения:
  по кнопке на сумму (`WalletCB(action="pick", stars=...)`) + «◀ Назад»
  (`WalletCB(action="open")`).

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
- `TrialFlow(choosing_inbound)` — активация пробного периода. Нет шага
  выбора плана (длина/трафик из `TRIAL_DAYS`/`TRIAL_TRAFFIC_GB`) и нет
  extend-ветки (trial — всегда новая подписка). При единственном inbound шаг
  пропускается (авто-активация в `cb_open`), иначе — выбор inbound через
  `inbound_select_kb` под этим стейтом.
- `GiftRedeem(waiting_code)` — активация подарка по ручному вводу кода
  (`cb_redeem` → ввод → `redeem_gift`). Deep-link путь (`/start gift_<code>`)
  минует FSM и активируется прямо в `start.cmd_start`.
- `SupportFlow(writing)` — единичный стейт написания сообщения в поддержку
  (`cb_open` → ввод → `tickets_service.open_ticket` + уведомление админов).

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

### Сквозные (E2E) тесты

E2E-тесты соединяют НЕСКОЛЬКО хендлеров/job-ов в один пользовательский или
админский journey и проверяют состояние реальной SQLite между шагами (через
`get_conn()` + repo-функции). Мокаются только внешние границы — Telegram Bot
API (`AsyncMock` бот) и клиент 3x-ui (`request_json`); middleware, роутинг,
services, repos и БД работают по-настоящему. Харнесс — journey-цепочки прямых
вызовов хендлеров (как остальные тесты проекта), не dispatcher-feed.

- [`tests/test_e2e_purchase.py`](tests/test_e2e_purchase.py) — покупка:
  полный путь нового юзера (open → pick plan → confirm → pre_checkout →
  successful_payment → `active`-подписка + `payments` + доставка ключей
  vless/QR/sub URL/`happ://import/`); идемпотентность повторного
  `successful_payment` (нет второй подписки/платежа); кошелёк (top-up
  кредитует один раз + оплата с баланса провижинит и списывает).
- [`tests/test_e2e_growth.py`](tests/test_e2e_growth.py) — рост: trial
  (активация создаёт `is_trial`-подписку, повтор отклонён); рефералы (bind
  по `/start ref_<tg>` + награда инвайтеру ровно раз на первой оплате,
  self-referral игнор); подарки (оплата минтит код без подписки покупателю,
  получатель активирует `/start gift_<code>`, повторный redeem заблокирован);
  нативное автопродление (первый recurring → провижин + `auto_renew` +
  charge id, последующий → продление, отмена → `edit_user_star_subscription`);
  wallet-fallback `auto_renew_job` (списание раз + продление, нехватка
  баланса → уведомление, same-period повтор без двойного списания).
- [`tests/test_e2e_ops.py`](tests/test_e2e_ops.py) — операции: трафик-алерт
  (один раз + dedup на следующем снапшоте); напоминание с inline-кнопкой
  продления; тикеты (юзер открыл → админы уведомлены → админ ответил → статус
  open→answered + транскрипт в БД); админ grant + ban + audit и блокировка
  следующего апдейта `BlockedUserMiddleware`; health-check (down/up алерты,
  стабильное состояние без спама); CSV-экспорт (3 документа, в подписочном CSV
  нет `xui_client_uuid`); i18n (смена языка на `en` пишет `users.lang='en'`,
  рендер выдаёт английскую строку).

### Граничные (boundary/edge) тесты

Целенаправленная проверка краевых значений по доменам: off-by-one,
min/max, пустые/нулевые/отрицательные входы, точные пороги, переполнение
лимитов, истечение «ровно сейчас», идемпотентность на границе ёмкости.

- [`tests/test_edge_billing_wallet.py`](tests/test_edge_billing_wallet.py) —
  payload ровно на 128 байт (`<=`) и за границей; legacy без `"k"`→`buy`;
  `sub_id` 0/1; clamp цены к 1 Star (percent=100, flat≥price); `try_spend`
  на `==balance` / `+1` / 0 / дубль `ref`; `credit`/`add` дубль `ref` и
  `ref=None`; `payments` UNIQUE charge_id и инклюзивные границы
  `total_stars_period`.
- [`tests/test_edge_promos_subs.py`](tests/test_edge_promos_subs.py) —
  `compute_discount` по типам (percent 1/100, flat 0/==price/>price,
  free_days); `validate` (expires==now, max_uses 0/1, used==max граница,
  NOCASE); `try_redeem`/`apply` на границе ёмкости и конкуренции;
  подписки (`expires_at==now` в expired vs active, окно `list_expiring_in`);
  trial partial-unique; рефералы (self/дубль/награда раз, bonus=0); подарки
  (NOCASE, double-redeem, коллизии `make_gift_code`, откат при XuiError).
- [`tests/test_edge_config_i18n_links.py`](tests/test_edge_config_i18n_links.py)
  — `_parse_csv_ints` (пусто/None/пробелы/хвостовая запятая/JSON/не-массив);
  валидаторы числовых полей (`ge`/`le`/`gt` границы → ValidationError);
  `resolve_lang` (None/""/`en-US`/верхний регистр/неподдержанный);
  `t` (отсутствующий ключ→ключ, fallback uk→en, безопасный плейсхолдер);
  `pluralize` RU/EN формы (0,1,2,5,11,21,100,1000, отрицательные);
  `build_import_links` (пусто→{}, 4 ключа, спецсимволы); `build_subscription_url`
  (схлопывание слешей).
- [`tests/test_edge_scheduler_xui_ops.py`](tests/test_edge_scheduler_xui_ops.py)
  — `_days_left`/`_kind_for_days_left` (3/2/1/0/expired); `list_auto_renew_due`
  окно `within_hours` и исключения (auto_renew=0, нативная, не active);
  `auto_renew_job` баланс `==price` / `price-1` / повтор; трафик-алерт ровно на
  пороге/±/`traffic_gb=0`/`percent=0`/dedup; xui (ms-конверсия expiry,
  `totalGB=0`, null-ответ→{}, продление сохраняет квоту, идемпотентный del);
  exports (CSV-экранирование, нет uuid); health (`check_xui_health` up/down,
  `record()` переходы changed).

**Заметки i18n (intended, не баги):** `resolve_lang` режет тег по дефису
(`en_GB`→DEFAULT), а `t()` для неподдержанного `lang` отдаёт `FALLBACK_LANG`
(`en`), не прогоняя его через `resolve_lang` — в проде `lang` всегда берётся из
`user.lang`, уже нормализованного при создании, поэтому расхождение не
проявляется.
