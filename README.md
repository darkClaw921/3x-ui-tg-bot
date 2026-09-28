<div align="center">

<img src="./assets/hero.svg" alt="3x-ui Telegram VPN Bot" width="100%" />

<br/>

<h1>3x-ui Telegram VPN Bot</h1>

<p><b>VPN-подписки прямо в Telegram.</b> Бот продаёт доступ за Telegram&nbsp;Stars,<br/>
управляет клиентами в панели <a href="https://github.com/MHSanaei/3x-ui">3x-ui</a> и выдаёт <code>vless://</code>-ключи, QR-коды и Subscription&nbsp;URL.</p>

<p>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white" />
  <img alt="aiogram" src="https://img.shields.io/badge/aiogram-3.x-2CA5E0?logo=telegram&logoColor=white" />
  <img alt="SQLite" src="https://img.shields.io/badge/SQLite-aiosqlite-003B57?logo=sqlite&logoColor=white" />
  <img alt="VLESS" src="https://img.shields.io/badge/VLESS-%2BReality-10b981" />
  <img alt="Telegram Stars" src="https://img.shields.io/badge/Payments-Telegram%20Stars-FFD43B?logo=telegram&logoColor=black" />
  <img alt="License" src="https://img.shields.io/badge/License-MIT-22c55e" />
</p>

</div>

---

## ✨ Возможности

| | |
|---|---|
| 💳 **Оплата в Stars** | Продажа подписок за Telegram Stars — без внешних платёжных провайдеров. |
| 🔑 **Мгновенная выдача ключа** | После оплаты бот присылает `vless://`-ссылку, **QR-код**, **Subscription URL** и **дип-линки импорта** в Happ / v2RayNG / Hiddify / Streisand. |
| 🔁 **Автопродление** | Нативные **Telegram Star Subscriptions** (рекуррентные), кнопка «Продлить в 1 тап» в напоминаниях и fallback-списание с внутреннего баланса. |
| 👛 **Кошелёк (баланс в Stars)** | Пополнение баланса и оплата покупок/продлений с него; append-only ledger с защитой от двойного списания. |
| 👥 **Реферальная программа** | Персональная ссылка `?start=ref_<id>`, бонус на баланс пригласившему после первой оплаты приглашённого. |
| 🎁 **Пробный период и подарки** | Бесплатный trial (один на юзера) и подарочные подписки по коду/дип-линку `?start=gift_<code>`. |
| 🎟 **Промокоды** | Три типа: `percent` (скидка %), `flat_stars` (скидка в Stars), `free_days` (бесплатные дни). |
| 📦 **Несколько подписок и локаций** | Несколько активных подписок одновременно; выбор сервера/локации (`plan_inbounds`) с индикатором доступности. |
| 🌐 **Мультиязычность** | RU + EN (полные) + заготовки uk/fa/zh с fallback на EN; автоопределение по `language_code` и выбор языка в меню. |
| ❓ **Поддержка (тикеты)** | Двусторонний чат пользователь ↔ админы прямо в боте, с историей в БД. |
| 🛠 **Админ-операционка** | Тарифы, промокоды, карточки и **бан** пользователей, **ручная выдача** подписки, статистика с **CSV-экспортом**, рассылки, **аудит-лог** действий. |
| 🩺 **Мониторинг** | Health-check панели 3x-ui с алертом админам только на смену состояния + алерты по трафику (порог %). |
| ⏱ **Фоновые задачи** | APScheduler: истечение подписок, напоминания, снапшоты трафика, автопродление и health-check. |
| 🚀 **Установка в один скрипт** | `deploy/install-3x-ui.sh` ставит панель 3x-ui (VLESS+Reality), Let's Encrypt и самого бота. |

## 🔄 Как это работает

<div align="center">

```
 ┌──────────────┐   /start    ┌──────────────┐   REST API   ┌──────────────┐
 │  Пользователь │ ──────────▶ │ Telegram-бот  │ ───────────▶ │  3x-ui Panel  │
 │   в Telegram  │   Stars ⭐  │  (aiogram 3)  │   add client │  VLESS+Reality│
 └──────────────┘             └──────────────┘              └──────┬───────┘
        ▲                                                          │
        │      vless:// · QR-код · Subscription URL                │
        └──────────────────────────────────────────────────────────┘
```

</div>

1. Пользователь жмёт **«Купить подписку»**, выбирает тариф и (опционально) вводит промокод.
2. Бот выставляет счёт в **Telegram Stars** и ждёт оплату.
3. После успешного платежа бот создаёт клиента в **3x-ui** через REST API.
4. Пользователю прилетает **`vless://`-ссылка, QR-код и Subscription URL** — можно подключаться.

Локальное состояние (пользователи, тарифы, промокоды, подписки, платежи) живёт в **SQLite**;
актуальные клиенты — в панели 3x-ui.

## 🧱 Стек

- **Python 3.12** + [**aiogram 3.x**](https://docs.aiogram.dev/) — long polling.
- **aiosqlite** — БД. · **httpx** — REST к 3x-ui. · **qrcode[pil]** — QR.
- **APScheduler** — фоновые задачи. · **pydantic-settings** — конфиг из `.env`. · **loguru** — логи.

## 🚀 Быстрый старт

### Вариант A — всё одной командой (чистый Ubuntu/Debian)

Проверяет IP сервера на блокировку РКН, ставит панель **3x-ui** (с VLESS+Reality inbound + сразу готовым подключением), при FQDN — **Let's Encrypt** сертификат, и опционально самого бота как systemd-сервис. **Домен и бот необязательны** — без них ставится только VPN на IP этого сервера:

```bash
# Только VPN (без домена, без бота) — самый быстрый способ получить рабочее подключение
sudo bash <(curl -sSL https://raw.githubusercontent.com/darkClaw921/3x-ui-tg-bot/main/deploy/install-3x-ui.sh) \
    --non-interactive
```

```bash
# Полная установка: VPN + бот на своём домене
sudo bash <(curl -sSL https://raw.githubusercontent.com/darkClaw921/3x-ui-tg-bot/main/deploy/install-3x-ui.sh) \
    --bot-token=1234567:ABCDEF \
    --admin-id=123456789 \
    --domain=vpn.example.com \
    --install-bot \
    --bot-repo=https://github.com/darkClaw921/3x-ui-tg-bot.git
```

Скопируйте нужную команду (при желании подставьте свои `--bot-token`, `--admin-id` и `--domain`) — и через пару минут получите работающую панель и готовое VPN-подключение, а если указан `--install-bot` — ещё и запущенного бота.

<details>
<summary><b>Что делает скрипт и какие есть флаги</b></summary>

<br/>

Скрипт самостоятельно:

- **проверяет публичный IP сервера по реестру блокировок Роскомнадзора** (antifilter.download) ещё до установки чего-либо — если IP/подсеть заблокированы, останавливается с объяснением (VPN на таком IP не будет работать для пользователей из РФ независимо от протокола);
- поставит 3x-ui из официального репозитория (отвечая на интерактивные вопросы установщика);
- задаст логин/пароль/порт/`webBasePath`;
- сгенерирует x25519-ключи Reality, создаст inbound **и сразу добавит в него клиента** — готовая `vless://`-ссылка на подключение печатается в финальном отчёте, не дожидаясь бота;
- при `--ssl-mode=on` (включается автоматически, если `--domain` — это FQDN): поставит `certbot`, выпустит Let's Encrypt сертификат через HTTP-01 challenge на `:80` и пропишет пути в SQLite-настройках 3x-ui (`webCertFile`/`webKeyFile`/`subCertFile`/`subKeyFile`) — панель и subscription-сервер сразу работают по HTTPS **без reverse-proxy**. Renewal-hook (`/etc/letsencrypt/renewal-hooks/deploy/restart-x-ui.sh`) перезапускает x-ui после `certbot renew`;
- запишет готовый `.env` для бота с корректными `XUI_BASE_URL`, `XUI_SUB_BASE_URL`, `XUI_VERIFY_SSL`;
- по флагу `--install-bot` склонирует репозиторий, создаст venv и поднимет бота как systemd-сервис.

Полезные флаги:

- `--ssl-mode=auto|on|off` — `auto` (по умолчанию): FQDN → выпускается LE-сертификат, IP → панель остаётся HTTP-only (`XUI_VERIFY_SSL=false`).
- `--le-email=<addr>` — email для Let's Encrypt. Если не задан, сертификат выпускается с `--register-unsafely-without-email`.
- `--client-email=<str>` — имя первого клиента inbound (по умолчанию `admin`).
- `--skip-blocklist-check` / `--force-blocked-ip` — пропустить проверку РКН-блокировки или продолжить установку, даже если IP в реестре.

Полное описание аргументов, troubleshooting и обновление — в [`deploy/install-3x-ui.md`](./deploy/install-3x-ui.md).

</details>

### Вариант B — локальный запуск

```bash
git clone https://github.com/darkClaw921/3x-ui-tg-bot.git
cd 3x-ui-tg-bot

python3.12 -m venv .venv
source .venv/bin/activate     # macOS / Linux
pip install -e .

cp .env.example .env
# заполните переменные в .env (минимум BOT_TOKEN, XUI_*)

python -m app.main
```

После запуска отправьте боту `/start` — он должен ответить приветствием.

## ⚙️ Конфигурация

Все переменные читаются из `.env` (`pydantic-settings`). Шаблон — [`.env.example`](./.env.example).

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

| Переменная                   | По умолчанию      | Назначение                                              |
|------------------------------|-------------------|---------------------------------------------------------|
| `DB_PATH`                    | `./data/bot.db`   | Путь к файлу SQLite.                                    |
| `XUI_VERIFY_SSL`             | `true`            | Проверять TLS-сертификат панели. `false` — для self-signed. |
| `LOG_LEVEL`                  | `INFO`            | Уровень логирования (`DEBUG`/`INFO`/`WARNING`/`ERROR`). |
| `DEFAULT_LANGUAGE`           | `ru`              | Запасной язык интерфейса (`ru`/`en`/`uk`/`fa`/`zh`).    |
| `WALLET_TOPUP_PRESETS`       | `50,100,250,500`  | CSV сумм Stars для кнопок быстрого пополнения кошелька. Пусто — без пресетов. |
| `TRIAL_DAYS`                 | `0`               | Длительность пробного периода в днях. `0` — пробный период выключен. |
| `TRIAL_TRAFFIC_GB`           | `0`               | Лимит трафика пробной подписки в ГБ. `0` — безлимит.   |
| `REFERRAL_BONUS_STARS`       | `0`               | Бонус в Stars пригласившему после первой оплаты приглашённого. `0` — выключено. |
| `AUTO_RENEW_ENABLED`         | `true`            | Включает автопродление (нативные Star-подписки + fallback с баланса). |
| `TRAFFIC_ALERT_PERCENT`      | `80`              | Порог алерта по трафику (% от квоты тарифа). `0` — выключено. |
| `STAR_SUBSCRIPTION_PLAN_DAYS`| `30`              | Длительность тарифа (дней), дающая право на нативную Star-подписку (период фикс. 30 дней). |
| `SUPPORT_CHAT_ID`            | `0`               | Чат/группа для тикетов поддержки. `0` — уведомлять админов из `ADMIN_IDS` в личку. |

## 📖 Использование

<details>
<summary><b>👤 Пользователь</b></summary>

<br/>

1. Отправить `/start` боту → откроется главное меню.
2. *(опционально)* **«🎁 Пробный период»** — бесплатная подписка на пробный срок (один раз на пользователя, если `TRIAL_DAYS > 0`).
3. **«Купить подписку»** → выбрать тариф → выбрать локацию (если их несколько) → промокод (опционально) → подтвердить → оплатить через **Telegram Stars** или **с баланса кошелька**. Для месячного тарифа доступна кнопка **«🔁 Подписка (автопродление)»**.
4. После успешной оплаты бот пришлёт:
   - `vless://...` ссылку,
   - QR-код для импорта в XRay-клиент,
   - Subscription URL,
   - **дип-линки импорта** в Happ / v2RayNG / Hiddify / Streisand (см. ниже).
5. **«Моя подписка»** → статус (тариф, остаток дней, трафик), повторная выдача ключа, продление, отмена автопродления.
6. **«👛 Кошелёк»** → баланс, пополнение, история операций.
7. **«👥 Пригласить друга»** → персональная ссылка; бонус на баланс после первой оплаты приглашённого.
8. **«❓ Поддержка»** → создать тикет; переписка с админами идёт прямо в боте.
9. **«🌐 Язык»** → переключение языка интерфейса.
10. **«Активировать промокод»** → ввод кода (`free_days` — бесплатные дни; `percent`/`flat_stars` применяются при покупке).

</details>

<details>
<summary><b>📲 Подключение (импорт в клиент)</b></summary>

<br/>

После выдачи ключа бот присылает гайд «Как подключиться» с дип-линками импорта подписки в один тап:

| Клиент | Платформы | Дип-линк |
|---|---|---|
| **Happ** *(рекомендуем)* | iOS / Android / Windows / macOS | `happ://import/<sub_url>` |
| **v2RayNG / v2RayTun** | Android | `v2rayng://install-config?url=<sub_url>` |
| **Hiddify** | Android / iOS / Desktop | `hiddify://import/<sub_url>` |
| **Streisand** | iOS | `streisand://import/<sub_url>` |

Telegram не открывает кастомные схемы (`happ://`, `v2rayng://` …) как кнопки/ссылки, поэтому в гайде они даются **копируемыми блоками** — тапните, чтобы скопировать, и откройте ссылку.

> **Happ**: если дип-линк не открывается на вашей сборке — откройте Happ → **«+» → «Добавить подписку»** и вставьте **Subscription URL** (бот присылает его рядом со ссылкой). Это штатный способ Happ и работает всегда.

</details>

<details>
<summary><b>🛠 Администратор</b></summary>

<br/>

Доступ — только для Telegram-ID из `ADMIN_IDS`.

1. `/start` → видно меню «Админ».
2. **Тарифы** → создать (название, цена в Stars, длительность, лимит трафика, локации/inbound'ы), редактировать, активировать/деактивировать.
3. **Промокоды** → создать тип (`percent` / `flat_stars` / `free_days`), задать значение, лимит использований, срок действия.
4. **Пользователи** → найти юзера, увидеть подписку и трафик; **выдать подписку вручную**, **заблокировать/разблокировать**, выдать/снять админа, отозвать подписку.
5. **💬 Тикеты** → список открытых обращений, ответ пользователю через бота.
6. **📜 Аудит** → лог админских действий (кто, что, когда).
7. **Статистика** → сводка по платежам и промокодам + **📥 экспорт в CSV** (платежи / подписки / пользователи).
8. **Рассылки** → broadcast по всем пользователям.

</details>

## 🖥 Деплой (systemd)

Файл сервиса — [`deploy/tg-vpn-bot.service`](./deploy/tg-vpn-bot.service).

<details>
<summary><b>Шаги установки</b></summary>

<br/>

```bash
# 1. Создать системного пользователя для бота (домашняя директория — место проекта).
sudo useradd -r -m -d /opt/3x-ui-tg-bot -s /bin/bash tgbot

# 2. Склонировать репозиторий в /opt/3x-ui-tg-bot (от имени tgbot).
sudo -u tgbot git clone https://github.com/darkClaw921/3x-ui-tg-bot.git /opt/3x-ui-tg-bot
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

</details>

<details>
<summary><b>Обновление</b></summary>

<br/>

```bash
cd /opt/3x-ui-tg-bot
sudo -u tgbot git pull
sudo -u tgbot /opt/3x-ui-tg-bot/.venv/bin/pip install -e .
sudo systemctl restart tg-vpn-bot
```

</details>

<details>
<summary><b>Бэкап SQLite</b></summary>

<br/>

База SQLite живёт по пути из `DB_PATH` (по умолчанию `./data/bot.db`, при деплое — `/opt/3x-ui-tg-bot/data/bot.db`). Делайте регулярный бэкап:

```bash
# Безопасный snapshot через SQLite Online Backup API
sudo -u tgbot sqlite3 /opt/3x-ui-tg-bot/data/bot.db \
    ".backup '/var/backups/tg-vpn-bot-$(date +%F).db'"

# Cron (ежедневно в 03:00, хранить 30 дней)
sudo crontab -e
# 0 3 * * * sqlite3 /opt/3x-ui-tg-bot/data/bot.db ".backup '/var/backups/tg-vpn-bot-$(date +\%F).db'" && find /var/backups -name 'tg-vpn-bot-*.db' -mtime +30 -delete
```

Также имеет смысл бэкапить `.env` (вне публичных репозиториев).

</details>

## 📋 Требования

- **Python 3.12+** (см. `requires-python` в [pyproject.toml](./pyproject.toml)).
- **systemd** (для серверного деплоя) — Ubuntu 22.04/24.04, Debian 12+ и т.п.
- Развёрнутая **панель 3x-ui** с доступом к REST API (`/panel/api/inbounds/...`) и созданным inbound'ом, в котором бот будет управлять клиентами.
- Telegram-бот, созданный через [@BotFather](https://t.me/BotFather), с включёнными Stars-платежами.

## 🗂 Структура проекта

См. [architecture.md](./architecture.md) — там описан каждый файл и его назначение.

## ✅ E2E чек-лист

Перед промо-релизом или после крупных изменений прогоняется ручной end-to-end сценарий на staging-инстансе 3x-ui и dev-аккаунте Telegram-бота. Шаги — в [docs/e2e-checklist.md](./docs/e2e-checklist.md).

## 📄 Лицензия

Распространяется под лицензией **MIT** (см. поле `license` в [pyproject.toml](./pyproject.toml)).
