# install-3x-ui.sh

Идемпотентный bash-скрипт для **полной автоматической установки 3x-ui**
(VLESS + Reality) и опциональной разворачивания Telegram-бота из этого
репозитория на чистом Ubuntu 22.04/24.04 или Debian 12 сервере.

Файл: [`deploy/install-3x-ui.sh`](./install-3x-ui.sh).

---

## Что делает скрипт

1. **Префлайт**. Проверяет, что запущен от root, что ОС — Debian/Ubuntu.
   Устанавливает зависимости: `curl wget tar jq openssl qrencode
   ca-certificates iproute2`.
2. **UFW**. Если firewall активен — открывает порты `22/tcp`,
   `<panel-port>/tcp`, `<vless-port>/tcp`, `<sub-port>/tcp`. Если ufw нет
   или неактивен — тихо пропускает.
3. **Установка 3x-ui**. Скачивает официальный
   `install.sh` из [MHSanaei/3x-ui](https://github.com/MHSanaei/3x-ui) и
   запускает его, передавая `n` на вопрос «Customize settings?» — настройку
   делаем сами на следующем шаге.
4. **Конфигурация панели** через CLI `x-ui setting`:
   - `username`, `password`, `port`, `webBasePath`;
   - `subPort` и `subPath` (если поддерживаются CLI, иначе через REST API
     панели по `/panel/setting/update`).
5. **Логин в REST API панели** (`POST /login`), session cookie сохраняется
   во временном файле (удаляется в trap exit).
6. **Генерация Reality x25519 ключей**:
   - первая попытка — через API `/server/getNewX25519Cert`;
   - fallback — через бинарь `xray` из поставки 3x-ui (`xray x25519`).
7. **Создание VLESS+Reality inbound** через
   `POST /panel/api/inbounds/add`. `clients: []` — бот будет наполнять
   список сам. ID нового inbound сохраняется и попадёт в `.env`.
8. **Генерация `.env`**. Если запущено с `--install-bot`, пишется в
   `/opt/3x-ui-tg-bot/.env`, иначе — в `/root/3x-ui-tg-bot.env`. Права
   `600`.
9. **Опционально: установка бота** (`--install-bot`):
   - ставит `python3` (или `python3.12` через PPA, если системный < 3.12);
   - создаёт системного пользователя `tgbot`;
   - клонирует репозиторий бота в `/opt/3x-ui-tg-bot`;
   - создаёт venv и `pip install -e .`;
   - копирует systemd-юнит `deploy/tg-vpn-bot.service` и поднимает сервис;
   - выводит последние 20 строк `journalctl -u tg-vpn-bot`.
10. **Финальный отчёт**: URL панели, логин/пароль, ID inbound, public key
    Reality, путь к `.env`, команды для проверки и рекомендации по бэкапу.

---

## Аргументы

| Аргумент | Обязательный | Описание | Значение по умолчанию |
|----------|--------------|----------|-----------------------|
| `--bot-token=<str>` | да | Токен Telegram-бота от BotFather | — |
| `--admin-id=<csv>` | да | Telegram user ID админов через запятую | — |
| `--domain=<fqdn>` | да | Публичный FQDN сервера (попадает в `XUI_SERVER_HOST` и Reality SNI по умолчанию) | — |
| `--panel-port=<int>` | нет | Порт админ-панели | случайный 20000-65535 |
| `--panel-user=<str>` | нет | Логин панели | `admin` |
| `--panel-pass=<str>` | нет | Пароль панели | `openssl rand -base64 18` |
| `--panel-path=<str>` | нет | Web base path (для маскировки) | `/<12 hex>/` |
| `--vless-port=<int>` | нет | Порт VLESS Reality inbound | `443` |
| `--reality-dest=<host:port>` | нет | Маскировочный сайт Reality | `www.microsoft.com:443` |
| `--reality-sni=<str>` | нет | SNI Reality | host из `reality-dest` |
| `--sub-port=<int>` | нет | Порт подписок | `2096` |
| `--sub-path=<str>` | нет | Path подписок | `/sub/` |
| `--install-bot` | нет | Также установить бота | off |
| `--bot-repo=<url>` | если `--install-bot` | git URL репозитория бота | — |
| `--non-interactive` | нет | Не задавать вопросов; падать при недостаче параметров | off |
| `--help` | — | Справка | — |

Если что-то из обязательных аргументов не передано и `--non-interactive`
не указан — скрипт спросит интерактивно.

---

## Примеры запуска

### Минимальный

```bash
sudo bash deploy/install-3x-ui.sh \
    --bot-token=1234567:ABCDEF \
    --admin-id=123456789 \
    --domain=vpn.example.com
```

После завершения `/root/3x-ui-tg-bot.env` готов к использованию — скопируйте
его в `/opt/3x-ui-tg-bot/.env`, когда будете ставить бота вручную.

### Полная установка (панель + бот) одной командой

```bash
sudo bash deploy/install-3x-ui.sh \
    --bot-token=1234567:ABCDEF \
    --admin-id=123456789,987654321 \
    --domain=vpn.example.com \
    --panel-port=54321 \
    --panel-user=admin \
    --panel-pass='SuperSecret!42' \
    --panel-path=/secret-admin/ \
    --vless-port=443 \
    --reality-dest=www.cloudflare.com:443 \
    --install-bot \
    --bot-repo=https://github.com/youruser/3x-ui-tg-bot.git \
    --non-interactive
```

### Запуск напрямую из репозитория

```bash
bash <(curl -sSL https://raw.githubusercontent.com/youruser/3x-ui-tg-bot/main/deploy/install-3x-ui.sh) \
    --bot-token=1234567:ABCDEF \
    --admin-id=123456789 \
    --domain=vpn.example.com \
    --install-bot \
    --bot-repo=https://github.com/youruser/3x-ui-tg-bot.git
```

---

## Файлы и лог

- Лог скрипта: `/var/log/install-3x-ui.log` (создаётся только если запущено
  от root и `/var/log` доступен).
- Cookie-файл REST API панели: временный, удаляется в trap EXIT.
- Сгенерированный `.env`:
  - с `--install-bot`: `/opt/3x-ui-tg-bot/.env` (owner: `tgbot:tgbot`,
    chmod 600);
  - без бота: `/root/3x-ui-tg-bot.env` (chmod 600).
- БД 3x-ui: `/etc/x-ui/x-ui.db` (бэкапить).
- БД бота: `/opt/3x-ui-tg-bot/data/bot.db` (бэкапить).

---

## Идемпотентность

- Повторный запуск **не переустанавливает 3x-ui**, если он уже стоит и
  юнит `x-ui.service` зарегистрирован, но **применит новые** параметры
  `x-ui setting`.
- Если `.env` уже существует — спросит «перезаписать (o) / .bak (b)»; в
  `--non-interactive` всегда делает `.bak`.
- Если каталог `/opt/3x-ui-tg-bot/.git` уже есть — делает `git pull
  --ff-only` вместо `clone`.
- Каждый запуск **создаёт новый inbound** (с remark `bot-vless-reality`).
  Если повторная установка не нужна — удалите старый inbound из панели
  заранее или измените код перед запуском.

---

## Troubleshooting

### Установщик 3x-ui завис на вопросе

В новых версиях `install.sh` иногда добавляются интерактивные вопросы.
Скрипт отправляет `n\n` в stdin, но если поменялся формат — установщик
может всё равно ждать ввода. Перезапустите с `--non-interactive`
**после** того, как `x-ui` уже установлен (повторный запуск пропустит
установщик и применит только настройки).

### `Сервис x-ui не активен`

Проверьте лог установщика и журнал:

```bash
tail -100 /var/log/install-3x-ui.log
journalctl -u x-ui -n 200 --no-pager
```

Часто причина — занятый `panel-port`. Перезапустите с другим портом:

```bash
x-ui uninstall   # если хотите полностью переустановить
sudo bash deploy/install-3x-ui.sh ... --panel-port=54321
```

### `Не удалось сгенерировать x25519-ключи Reality`

Скрипт не нашёл ни API `/server/getNewX25519Cert`, ни бинарь
`xray-linux-*` в `/usr/local/x-ui/bin/`. Возможно установлена очень
старая версия 3x-ui. Обновите панель:

```bash
x-ui update
```

И запустите скрипт повторно (он не будет переустанавливать панель,
но повторит настройку).

### `Создание inbound не удалось: ...`

Чаще всего: `port already in use` — другой процесс держит `--vless-port`.
Проверьте `ss -tlnp | grep ":<port>"`. Передайте `--vless-port=<other>`
и запустите снова (старый, не созданный inbound удалять не нужно).

### Бот не стартует (`tg-vpn-bot.service` в failed)

```bash
journalctl -u tg-vpn-bot -n 100 --no-pager
```

Типичные причины:
- Неверный `BOT_TOKEN` → бот падает на старте при попытке `getMe`.
- `XUI_VERIFY_SSL=true` при self-signed сертификате панели → скрипт уже
  ставит `false`, но если правили вручную — верните `false`.
- Опечатки в `XUI_BASE_URL` / `XUI_SUB_BASE_URL` → сравните с разделом
  `/var/log/install-3x-ui.log`.

### Полное удаление

```bash
# Бот
sudo systemctl disable --now tg-vpn-bot
sudo rm -f /etc/systemd/system/tg-vpn-bot.service
sudo systemctl daemon-reload
sudo rm -rf /opt/3x-ui-tg-bot
sudo userdel -r tgbot 2>/dev/null

# 3x-ui
sudo x-ui uninstall
```

---

## Обновление

### Обновление 3x-ui

```bash
sudo x-ui update
sudo systemctl restart x-ui
```

Этот скрипт сам обновлять панель не умеет — это работа `x-ui update`.

### Обновление бота

```bash
cd /opt/3x-ui-tg-bot
sudo -u tgbot git pull
sudo -u tgbot /opt/3x-ui-tg-bot/.venv/bin/pip install -e .
sudo systemctl restart tg-vpn-bot
```

---

## Безопасность

- Скрипт **отключает сохранение истории shell** (`set +o history`) на
  время выполнения, чтобы пароль/токен не утекли в `.bash_history`.
- Cookie-файл REST API панели — `mktemp` в `/tmp`, удаляется в trap EXIT.
- `.env` всегда `chmod 600`.
- Передача `--panel-pass` / `--bot-token` через CLI **видна в `ps auxf`**
  во время выполнения. Если это критично — запускайте без аргументов
  (интерактивный режим) или используйте `--panel-pass="$(cat
  /root/.panel-pass)"`.
