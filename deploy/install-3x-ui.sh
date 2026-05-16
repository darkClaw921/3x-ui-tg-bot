#!/usr/bin/env bash
#
# install-3x-ui.sh - Автоматическая установка 3x-ui (VLESS+Reality) и
# опционально Telegram-бота (3x-ui-tg-bot) на чистый Ubuntu/Debian сервер.
#
# Что делает:
#   1. Проверяет окружение (root, Ubuntu/Debian, нужные утилиты).
#   2. Открывает порты в ufw (если активен).
#   3. Ставит официальный 3x-ui (https://github.com/MHSanaei/3x-ui).
#   4. Через CLI `x-ui setting` задаёт логин/пароль/порт/webBasePath/subPort/subPath.
#   5. Логинится в REST API панели, создаёт VLESS+Reality inbound с
#      сгенерированными x25519-ключами и shortIds.
#   6. Генерирует .env для бота (заполняя XUI_*, BOT_TOKEN, ADMIN_IDS).
#   7. По флагу --install-bot клонирует репо бота, ставит venv, systemd-юнит.
#
# Подробности — в deploy/install-3x-ui.md.

set -euo pipefail

# ---------------------------------------------------------------------- #
# Глобальные константы и состояние
# ---------------------------------------------------------------------- #

readonly SCRIPT_NAME="install-3x-ui.sh"
readonly LOG_FILE="/var/log/install-3x-ui.log"
COOKIE_FILE="$(mktemp -t xui-cookie.XXXXXX)"
readonly COOKIE_FILE
readonly BOT_DIR="/opt/3x-ui-tg-bot"
readonly XUI_DB="/etc/x-ui/x-ui.db"

# Очистка временных файлов и истории
cleanup() {
    local rc=$?
    rm -f "$COOKIE_FILE" 2>/dev/null || true
    if [[ $rc -ne 0 ]]; then
        err "Скрипт завершился с ошибкой (код $rc)."
        err "Что можно сделать:"
        err "  1. Изучить лог: $LOG_FILE"
        err "  2. Удалить 3x-ui (если установлен): x-ui uninstall"
        err "  3. Удалить бота (если установлен): systemctl disable --now tg-vpn-bot; rm -rf $BOT_DIR"
        err "  4. Запустить установщик повторно."
    fi
    return $rc
}
trap cleanup EXIT

# Отключаем сохранение чувствительных данных в истории интерактивной оболочки
set +o history 2>/dev/null || true

# ---------------------------------------------------------------------- #
# Логи (цветной вывод + tee в файл)
# ---------------------------------------------------------------------- #

if [[ -t 1 ]]; then
    readonly C_RESET=$'\033[0m'
    readonly C_RED=$'\033[31m'
    readonly C_GREEN=$'\033[32m'
    readonly C_YELLOW=$'\033[33m'
    readonly C_BLUE=$'\033[34m'
    readonly C_BOLD=$'\033[1m'
else
    readonly C_RESET=""
    readonly C_RED=""
    readonly C_GREEN=""
    readonly C_YELLOW=""
    readonly C_BLUE=""
    readonly C_BOLD=""
fi

# Лог-файл создаём только если можем (root + /var/log существует)
init_log_file() {
    if [[ $EUID -eq 0 ]] && [[ -d /var/log ]]; then
        : >> "$LOG_FILE" 2>/dev/null || true
        chmod 600 "$LOG_FILE" 2>/dev/null || true
    fi
}

_log() {
    local level="$1"; shift
    local color="$1"; shift
    local ts
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    printf '%s[%s]%s %s%s%s %s\n' "$color" "$level" "$C_RESET" "$C_BOLD" "$ts" "$C_RESET" "$*" >&2
    if [[ -w "$LOG_FILE" ]] 2>/dev/null; then
        printf '[%s] [%s] %s\n' "$level" "$ts" "$*" >> "$LOG_FILE" 2>/dev/null || true
    fi
}

info()  { _log "INFO"  "$C_BLUE"   "$@"; }
ok()    { _log "OK"    "$C_GREEN"  "$@"; }
warn()  { _log "WARN"  "$C_YELLOW" "$@"; }
err()   { _log "ERR"   "$C_RED"    "$@"; }
fatal() { err "$@"; exit 1; }

# ---------------------------------------------------------------------- #
# Аргументы CLI и значения по умолчанию
# ---------------------------------------------------------------------- #

BOT_TOKEN=""
ADMIN_IDS=""
DOMAIN=""
PANEL_PORT=""
PANEL_USER="admin"
PANEL_PASS=""
PANEL_PATH=""
VLESS_PORT="443"
REALITY_DEST="www.microsoft.com:443"
REALITY_SNI=""
SUB_PORT="2096"
SUB_PATH="/sub/"
INSTALL_BOT="false"
BOT_REPO=""
NON_INTERACTIVE="false"
SSL_MODE="auto"           # auto|nginx|skip
LE_EMAIL=""
NGINX_PORT="auto"         # auto = 443 если VLESS!=443, иначе 8443

usage() {
    cat >&2 <<USAGE
${C_BOLD}$SCRIPT_NAME${C_RESET} — установка 3x-ui и настройка под Telegram-бота.

Запуск: sudo bash $SCRIPT_NAME [опции]

Опции:
  --bot-token=<str>           Токен Telegram-бота (обязателен).
  --admin-id=<ids>            ID админов через запятую, например 12345,67890 (обязателен).
  --domain=<fqdn>             FQDN сервера, например vpn.example.com (обязателен).
  --panel-port=<int>          Порт админ-панели 3x-ui. По умолчанию: случайный 20000-65535.
  --panel-user=<str>          Логин панели. По умолчанию: admin.
  --panel-pass=<str>          Пароль панели. По умолчанию: openssl rand -base64 18.
  --panel-path=<str>          webBasePath (например /abcd1234ef/). По умолчанию: /<12 hex>/.
  --vless-port=<int>          Порт VLESS Reality inbound. По умолчанию: 443.
  --reality-dest=<host:port>  Маскировочный сайт. По умолчанию: www.microsoft.com:443.
  --reality-sni=<str>         SNI Reality. По умолчанию: совпадает с host из reality-dest.
  --sub-port=<int>            Порт подписок. По умолчанию: 2096.
  --sub-path=<str>            Path подписок. По умолчанию: /sub/.
  --install-bot               Также установить бота как systemd-сервис.
  --bot-repo=<url>            git URL проекта бота (нужен с --install-bot).
  --ssl-mode=<mode>           auto|nginx|skip. По умолчанию: auto
                              (FQDN -> nginx+LE, IP -> skip).
  --le-email=<email>          Email для Let's Encrypt. По умолчанию: без email
                              (--register-unsafely-without-email).
  --nginx-port=<int>          Порт HTTPS для nginx reverse-proxy. По умолчанию: auto
                              (443; если VLESS=443 — берётся 8443).
  --non-interactive           Не задавать вопросов; падать при недостаче параметров.
  --help                      Показать эту справку и выйти.

Пример:
  sudo bash $SCRIPT_NAME \\
      --bot-token=123:abcdef \\
      --admin-id=12345 \\
      --domain=vpn.example.com \\
      --install-bot \\
      --bot-repo=https://github.com/you/3x-ui-tg-bot.git
USAGE
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --bot-token=*)       BOT_TOKEN="${1#*=}";       shift ;;
            --admin-id=*)        ADMIN_IDS="${1#*=}";       shift ;;
            --admin-ids=*)       ADMIN_IDS="${1#*=}";       shift ;;
            --domain=*)          DOMAIN="${1#*=}";          shift ;;
            --panel-port=*)      PANEL_PORT="${1#*=}";      shift ;;
            --panel-user=*)      PANEL_USER="${1#*=}";      shift ;;
            --panel-pass=*)      PANEL_PASS="${1#*=}";      shift ;;
            --panel-path=*)      PANEL_PATH="${1#*=}";      shift ;;
            --vless-port=*)      VLESS_PORT="${1#*=}";      shift ;;
            --reality-dest=*)    REALITY_DEST="${1#*=}";    shift ;;
            --reality-sni=*)     REALITY_SNI="${1#*=}";     shift ;;
            --sub-port=*)        SUB_PORT="${1#*=}";        shift ;;
            --sub-path=*)        SUB_PATH="${1#*=}";        shift ;;
            --install-bot)       INSTALL_BOT="true";        shift ;;
            --bot-repo=*)        BOT_REPO="${1#*=}";        shift ;;
            --ssl-mode=*)        SSL_MODE="${1#*=}";        shift ;;
            --le-email=*)        LE_EMAIL="${1#*=}";        shift ;;
            --nginx-port=*)      NGINX_PORT="${1#*=}";      shift ;;
            --non-interactive)   NON_INTERACTIVE="true";    shift ;;
            --help|-h)           usage; exit 0 ;;
            *)
                err "Неизвестный аргумент: $1"
                usage
                exit 2
                ;;
        esac
    done
}

# ---------------------------------------------------------------------- #
# Хелперы
# ---------------------------------------------------------------------- #

ask() {
    # ask <var-name> <prompt> [default]
    local __name="$1" __prompt="$2" __default="${3:-}"
    local __val=""
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        if [[ -z "$__default" ]]; then
            fatal "Параметр '$__name' не задан, режим --non-interactive."
        fi
        printf -v "$__name" '%s' "$__default"
        return 0
    fi
    if [[ -n "$__default" ]]; then
        read -r -p "$__prompt [$__default]: " __val
        __val="${__val:-$__default}"
    else
        while [[ -z "$__val" ]]; do
            read -r -p "$__prompt: " __val
        done
    fi
    printf -v "$__name" '%s' "$__val"
}

ask_secret() {
    # ask_secret <var-name> <prompt> [default]
    local __name="$1" __prompt="$2" __default="${3:-}"
    local __val=""
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        if [[ -z "$__default" ]]; then
            fatal "Секретный параметр '$__name' не задан, режим --non-interactive."
        fi
        printf -v "$__name" '%s' "$__default"
        return 0
    fi
    read -r -s -p "$__prompt: " __val
    echo >&2
    if [[ -z "$__val" && -n "$__default" ]]; then
        __val="$__default"
    fi
    if [[ -z "$__val" ]]; then
        fatal "Значение '$__name' не может быть пустым."
    fi
    printf -v "$__name" '%s' "$__val"
}

rand_port() {
    # Случайный порт 20000-65535, не занятый локально.
    local p
    for _ in $(seq 1 50); do
        p=$(( (RANDOM % (65535 - 20000)) + 20000 ))
        if ! ss -tlnH "sport = :$p" 2>/dev/null | grep -q .; then
            printf '%d' "$p"
            return 0
        fi
    done
    fatal "Не удалось подобрать свободный порт в диапазоне 20000-65535."
}

rand_hex() {
    # rand_hex <bytes>
    openssl rand -hex "${1:-12}"
}

rand_base64() {
    # rand_base64 <bytes>
    openssl rand -base64 "${1:-18}" | tr -d '\n=' | tr '/+' '_-'
}

port_in_use() {
    local p="$1"
    ss -tlnH "sport = :$p" 2>/dev/null | grep -q .
}

ensure_root() {
    if [[ $EUID -ne 0 ]]; then
        fatal "Скрипт нужно запускать от root: sudo bash $SCRIPT_NAME ..."
    fi
}

ensure_os() {
    if [[ ! -r /etc/os-release ]]; then
        fatal "Не удаётся прочитать /etc/os-release — поддерживаются только Debian/Ubuntu."
    fi
    # shellcheck disable=SC1091
    . /etc/os-release
    local id_like="${ID:-} ${ID_LIKE:-}"
    case "$id_like" in
        *ubuntu*|*debian*) ok "ОС: ${PRETTY_NAME:-$ID}" ;;
        *) fatal "Неподдерживаемая ОС (${PRETTY_NAME:-unknown}). Только Debian/Ubuntu." ;;
    esac
}

# ---------------------------------------------------------------------- #
# Шаг 1: префлайт + apt-зависимости
# ---------------------------------------------------------------------- #

preflight() {
    info "Шаг 1: префлайт-проверки и установка зависимостей."
    ensure_root
    ensure_os
    init_log_file

    export DEBIAN_FRONTEND=noninteractive
    info "apt update..."
    apt-get update -y -qq
    info "Установка зависимостей (curl, wget, tar, jq, openssl, qrencode, ca-certificates, iproute2)..."
    apt-get install -y -qq --no-install-recommends \
        curl wget tar jq openssl qrencode ca-certificates iproute2
    ok "Зависимости установлены."
}

# ---------------------------------------------------------------------- #
# Шаг 2: ufw
# ---------------------------------------------------------------------- #

configure_ufw() {
    info "Шаг 2: настройка ufw (если активен)."
    if ! command -v ufw >/dev/null 2>&1; then
        warn "ufw не установлен — пропускаю."
        return 0
    fi
    if ! ufw status 2>/dev/null | grep -q "Status: active"; then
        warn "ufw неактивен — пропускаю."
        return 0
    fi
    local ports=("22/tcp" "$VLESS_PORT/tcp")
    # Если nginx-режим — открываем 80 (HTTP→HTTPS redirect + ACME) и NGINX_PORT.
    # Панель и sub-сервер биндим на 127.0.0.1, наружу торчит только nginx.
    if [[ "$SSL_MODE" == "nginx" ]]; then
        ports+=("80/tcp" "$NGINX_PORT/tcp")
    else
        # skip-режим: панель торчит наружу напрямую
        ports+=("$PANEL_PORT/tcp" "$SUB_PORT/tcp")
    fi
    for p in "${ports[@]}"; do
        info "ufw allow $p"
        ufw allow "$p" >/dev/null || warn "Не удалось открыть $p в ufw."
    done
    ok "ufw сконфигурирован."
}

# ---------------------------------------------------------------------- #
# Шаг 3: установка 3x-ui (официальный installer)
# ---------------------------------------------------------------------- #

install_3x_ui() {
    info "Шаг 3: установка 3x-ui (official installer)."
    if command -v x-ui >/dev/null 2>&1 && systemctl list-unit-files 2>/dev/null | grep -q '^x-ui\.service'; then
        warn "3x-ui уже установлен — пропускаю установку, конфигурацию обновлю."
        return 0
    fi

    local installer
    installer="$(mktemp -t xui-install.XXXXXX.sh)"
    info "Скачиваю install.sh от MHSanaei/3x-ui..."
    if ! curl -fsSL --max-time 60 \
        https://raw.githubusercontent.com/mhsanaei/3x-ui/master/install.sh \
        -o "$installer"; then
        rm -f "$installer"
        fatal "Не удалось скачать установщик 3x-ui."
    fi
    chmod +x "$installer"

    # Установщик 3x-ui v3+ задаёт три интерактивных вопроса:
    #   1. "Customize Panel Port settings?" [y/n]    → 'n' (рандомный порт; всё равно перезапишем через x-ui setting)
    #   2. "Choose an option (default 2 for IP):"    → '4' (skip SSL — TLS оформляем через nginx или вовсе пропускаем)
    #   3. "Bind the panel to 127.0.0.1 only? [y/N]" → 'y' в nginx-режиме (трафик идёт через reverse-proxy)
    #                                                  'n' в skip-режиме (бот ходит снаружи по DOMAIN:PORT)
    local bind_answer="n"
    [[ "$SSL_MODE" == "nginx" ]] && bind_answer="y"
    local installer_input
    installer_input="$(printf 'n\n4\n%s\n' "$bind_answer")"

    info "Запускаю установщик 3x-ui (ssl_mode=$SSL_MODE, bind_localhost=$bind_answer)..."
    if ! printf '%s' "$installer_input" | bash "$installer" 2>&1 | tee -a "$LOG_FILE"; then
        rm -f "$installer"
        fatal "Установщик 3x-ui завершился с ошибкой."
    fi
    rm -f "$installer"

    if ! command -v x-ui >/dev/null 2>&1; then
        fatal "Команда x-ui не найдена после установки."
    fi
    ok "3x-ui установлен."
}

wait_service_active() {
    local svc="$1" timeout="${2:-60}" i=0
    info "Жду активации systemd-сервиса '$svc' (timeout ${timeout}s)..."
    while (( i < timeout )); do
        if systemctl is-active --quiet "$svc"; then
            ok "Сервис '$svc' активен."
            return 0
        fi
        sleep 1
        i=$((i + 1))
    done
    err "Сервис '$svc' не активен. Логи:"
    journalctl -u "$svc" -n 30 --no-pager >&2 || true
    fatal "Не дождался активации '$svc'."
}

# ---------------------------------------------------------------------- #
# Шаг 4: настройка панели через `x-ui setting`
# ---------------------------------------------------------------------- #

configure_panel_settings() {
    info "Шаг 4: настройка панели (логин/пароль/порт/webBasePath)."
    wait_service_active x-ui 60

    # webBasePath в 3x-ui ожидается БЕЗ trailing slash для команды setting,
    # но в URL панели нужны слэши с обоих сторон. PANEL_PATH задаём как /xxx/.
    local web_base_path_clean
    web_base_path_clean="${PANEL_PATH#/}"
    web_base_path_clean="${web_base_path_clean%/}"

    info "x-ui setting -username/-password/-port/-webBasePath..."
    if ! x-ui setting \
        -username "$PANEL_USER" \
        -password "$PANEL_PASS" \
        -port "$PANEL_PORT" \
        -webBasePath "$web_base_path_clean" 2>&1 | tee -a "$LOG_FILE"; then
        fatal "x-ui setting (основные параметры) завершилась с ошибкой."
    fi

    # Sub-сервер настраивается отдельным набором флагов. Не все билды его
    # поддерживают на уровне CLI; пробуем, при отсутствии флага — настроим
    # через REST API панели.
    info "Пробую настроить subPort/subPath через CLI..."
    if x-ui setting -subPort "$SUB_PORT" -subPath "$SUB_PATH" >/dev/null 2>&1; then
        ok "subPort/subPath заданы через CLI."
        SUB_CONFIGURED_VIA_CLI="true"
    else
        warn "CLI не поддерживает -subPort/-subPath, настрою через API после логина."
        SUB_CONFIGURED_VIA_CLI="false"
    fi

    info "Перезапуск x-ui..."
    systemctl restart x-ui
    wait_service_active x-ui 60
}

# ---------------------------------------------------------------------- #
# Шаг 5: логин в REST API панели
# ---------------------------------------------------------------------- #

PANEL_BASE_LOCAL=""    # http(s)://127.0.0.1:<port><path без trailing slash>
PANEL_BASE_PUBLIC=""   # публичный URL для отображения в отчёте

build_panel_urls() {
    local path_clean="${PANEL_PATH%/}"
    [[ -z "$path_clean" ]] || [[ "${path_clean:0:1}" == "/" ]] || path_clean="/$path_clean"
    # Сама панель 3x-ui после установщика — HTTP-only (мы выбрали "skip SSL").
    # TLS терминирует либо nginx (наш setup_nginx_panel), либо его нет вовсе.
    PANEL_BASE_LOCAL="http://127.0.0.1:${PANEL_PORT}${path_clean}"
    if [[ "$SSL_MODE" == "nginx" ]]; then
        local port_suffix=""
        [[ "$NGINX_PORT" != "443" ]] && port_suffix=":${NGINX_PORT}"
        PANEL_BASE_PUBLIC="https://${DOMAIN}${port_suffix}${path_clean}"
    else
        PANEL_BASE_PUBLIC="http://${DOMAIN}:${PANEL_PORT}${path_clean}"
    fi
}

panel_curl() {
    # panel_curl <method> <path> [json-body]
    local method="$1" path="$2" body="${3:-}"
    local url="${PANEL_BASE_LOCAL}${path}"
    local args=(
        -sS -k --max-time 30
        -b "$COOKIE_FILE" -c "$COOKIE_FILE"
        -H "Accept: application/json"
        -X "$method"
        "$url"
    )
    if [[ -n "$body" ]]; then
        args+=(-H "Content-Type: application/json" --data "$body")
    fi
    curl "${args[@]}"
}

panel_login() {
    info "Шаг 5: логин в REST API панели ($PANEL_BASE_LOCAL/login)..."
    local resp
    resp="$(curl -sS -k --max-time 30 \
        -c "$COOKIE_FILE" \
        -H 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode "username=${PANEL_USER}" \
        --data-urlencode "password=${PANEL_PASS}" \
        "${PANEL_BASE_LOCAL}/login")" || fatal "Не удалось залогиниться в панель (curl error)."
    local success
    success="$(jq -r '.success // false' <<<"$resp" 2>/dev/null || echo false)"
    if [[ "$success" != "true" ]]; then
        err "Ответ панели: $resp"
        fatal "Логин в панель не прошёл: $(jq -r '.msg // "unknown"' <<<"$resp" 2>/dev/null)"
    fi
    ok "Логин в панель успешен."
}

# ---------------------------------------------------------------------- #
# Шаг 6: генерация Reality x25519 ключей
# ---------------------------------------------------------------------- #

REALITY_PRIVATE_KEY=""
REALITY_PUBLIC_KEY=""
REALITY_SHORT_ID=""

generate_reality_keys() {
    info "Шаг 6: генерация Reality x25519 ключей."

    # Попытка 1: через API панели
    local resp success
    resp="$(panel_curl GET /server/getNewX25519Cert 2>/dev/null || true)"
    if [[ -n "$resp" ]]; then
        success="$(jq -r '.success // false' <<<"$resp" 2>/dev/null || echo false)"
        if [[ "$success" == "true" ]]; then
            REALITY_PRIVATE_KEY="$(jq -r '.obj.privateKey' <<<"$resp")"
            REALITY_PUBLIC_KEY="$(jq -r '.obj.publicKey' <<<"$resp")"
            ok "Ключи получены через API панели."
        fi
    fi

    # Попытка 2: через бинарь xray
    if [[ -z "$REALITY_PRIVATE_KEY" || -z "$REALITY_PUBLIC_KEY" ]]; then
        warn "API getNewX25519Cert недоступен, пробую бинарь xray..."
        local xray_bin=""
        for candidate in /usr/local/x-ui/bin/xray-linux-* /usr/local/x-ui/bin/xray /usr/bin/xray; do
            if [[ -x "$candidate" ]]; then
                xray_bin="$candidate"
                break
            fi
        done
        if [[ -n "$xray_bin" ]]; then
            local kp
            kp="$("$xray_bin" x25519 2>/dev/null || true)"
            REALITY_PRIVATE_KEY="$(awk -F': *' '/^Private key:/{print $2}' <<<"$kp")"
            REALITY_PUBLIC_KEY="$(awk -F': *' '/^Public key:/{print $2}' <<<"$kp")"
            if [[ -n "$REALITY_PRIVATE_KEY" && -n "$REALITY_PUBLIC_KEY" ]]; then
                ok "Ключи получены через $xray_bin x25519."
            fi
        fi
    fi

    if [[ -z "$REALITY_PRIVATE_KEY" || -z "$REALITY_PUBLIC_KEY" ]]; then
        fatal "Не удалось сгенерировать x25519-ключи Reality (нет ни API, ни xray)."
    fi

    REALITY_SHORT_ID="$(openssl rand -hex 8)"
    ok "shortId: $REALITY_SHORT_ID"
}

# ---------------------------------------------------------------------- #
# Шаг 7: создание VLESS+Reality inbound через API
# ---------------------------------------------------------------------- #

INBOUND_ID=""

create_inbound() {
    info "Шаг 7: создание VLESS+Reality inbound (port=$VLESS_PORT, dest=$REALITY_DEST, sni=$REALITY_SNI)."

    local settings_json stream_json sniffing_json payload

    settings_json="$(jq -nc \
        '{clients:[], decryption:"none", fallbacks:[]}')"

    stream_json="$(jq -nc \
        --arg dest "$REALITY_DEST" \
        --arg sni  "$REALITY_SNI" \
        --arg priv "$REALITY_PRIVATE_KEY" \
        --arg pub  "$REALITY_PUBLIC_KEY" \
        --arg sid  "$REALITY_SHORT_ID" \
        '{
          network: "tcp",
          security: "reality",
          realitySettings: {
            show: false,
            xver: 0,
            dest: $dest,
            serverNames: [$sni],
            privateKey: $priv,
            minClient: "",
            maxClient: "",
            maxTimediff: 0,
            shortIds: [$sid],
            settings: {
              publicKey: $pub,
              fingerprint: "chrome",
              serverName: "",
              spiderX: "/"
            }
          },
          tcpSettings: {
            acceptProxyProtocol: false,
            header: { type: "none" }
          }
        }')"

    sniffing_json='{"enabled":true,"destOverride":["http","tls","quic"]}'

    payload="$(jq -nc \
        --arg remark "bot-vless-reality" \
        --argjson port "$VLESS_PORT" \
        --arg settings "$settings_json" \
        --arg stream "$stream_json" \
        --arg sniffing "$sniffing_json" \
        '{
          up: 0,
          down: 0,
          total: 0,
          remark: $remark,
          enable: true,
          expiryTime: 0,
          listen: "",
          port: $port,
          protocol: "vless",
          settings: $settings,
          streamSettings: $stream,
          sniffing: $sniffing
        }')"

    if port_in_use "$VLESS_PORT"; then
        warn "Порт $VLESS_PORT уже занят локально — inbound может не подняться."
    fi

    local resp
    resp="$(panel_curl POST /panel/api/inbounds/add "$payload")" \
        || fatal "Не удалось вызвать /panel/api/inbounds/add."
    local success
    success="$(jq -r '.success // false' <<<"$resp" 2>/dev/null || echo false)"
    if [[ "$success" != "true" ]]; then
        err "Ответ API: $resp"
        fatal "Создание inbound не удалось: $(jq -r '.msg // "unknown"' <<<"$resp")"
    fi

    INBOUND_ID="$(jq -r '.obj.id // empty' <<<"$resp")"
    if [[ -z "$INBOUND_ID" ]]; then
        # Некоторые билды возвращают obj=null; в этом случае подтянем список.
        warn "В ответе нет obj.id, забираю список inbound'ов..."
        local list
        list="$(panel_curl GET /panel/api/inbounds/list)"
        INBOUND_ID="$(jq -r --arg r "bot-vless-reality" \
            '.obj | map(select(.remark==$r)) | sort_by(.id) | last.id // empty' <<<"$list")"
    fi

    [[ -n "$INBOUND_ID" ]] || fatal "Не удалось определить ID созданного inbound."
    ok "Inbound создан, ID=$INBOUND_ID."
}

# ---------------------------------------------------------------------- #
# Доп. шаг: настройка subPort/subPath через API, если CLI не справился
# ---------------------------------------------------------------------- #

configure_sub_via_api() {
    if [[ "${SUB_CONFIGURED_VIA_CLI:-false}" == "true" ]]; then
        return 0
    fi
    info "Настраиваю subPort/subPath через API панели..."
    local resp
    resp="$(panel_curl GET /panel/setting/all 2>/dev/null || true)"
    if [[ -z "$resp" ]] || [[ "$(jq -r '.success // false' <<<"$resp")" != "true" ]]; then
        warn "API /panel/setting/all недоступно — пропускаю; subscription может остаться на дефолтном порту/пути."
        warn "Настройте subPort=$SUB_PORT и subPath=$SUB_PATH вручную в админ-панели."
        return 0
    fi

    local current sub_path_clean update_payload
    current="$(jq -c '.obj' <<<"$resp")"
    sub_path_clean="$SUB_PATH"
    [[ "${sub_path_clean:0:1}" == "/" ]] || sub_path_clean="/$sub_path_clean"
    [[ "${sub_path_clean: -1}" == "/" ]] || sub_path_clean="${sub_path_clean}/"

    update_payload="$(jq -c \
        --arg subPort "$SUB_PORT" \
        --arg subPath "$sub_path_clean" \
        '. + {subPort:($subPort|tonumber), subPath:$subPath, subEnable:true}' <<<"$current")"

    resp="$(panel_curl POST /panel/setting/update "$update_payload")"
    if [[ "$(jq -r '.success // false' <<<"$resp")" != "true" ]]; then
        warn "Не удалось обновить subPort/subPath через API: $(jq -r '.msg // "unknown"' <<<"$resp")"
        warn "Настройте subPort/subPath вручную."
    else
        ok "subPort/subPath обновлены через API."
        info "Перезапуск x-ui..."
        systemctl restart x-ui
        wait_service_active x-ui 60
    fi
}

# ---------------------------------------------------------------------- #
# Шаг 7.5: nginx reverse-proxy + Let's Encrypt (только если SSL_MODE=nginx)
# ---------------------------------------------------------------------- #

NGINX_SITE_CONF="/etc/nginx/sites-available/3x-ui-panel.conf"
NGINX_SITE_LINK="/etc/nginx/sites-enabled/3x-ui-panel.conf"
LE_CERT_DIR=""

setup_nginx_panel() {
    if [[ "$SSL_MODE" != "nginx" ]]; then
        info "SSL_MODE=$SSL_MODE — пропускаю настройку nginx."
        return 0
    fi

    info "Шаг 7.5: установка nginx + выпуск Let's Encrypt сертификата для $DOMAIN."

    # 1. Проверка/установка nginx и certbot
    if command -v nginx >/dev/null 2>&1; then
        ok "nginx уже установлен ($(nginx -v 2>&1 | awk '{print $3}'))."
    else
        info "Устанавливаю nginx..."
        apt-get install -y -qq --no-install-recommends nginx
    fi
    if ! command -v certbot >/dev/null 2>&1; then
        info "Устанавливаю certbot..."
        apt-get install -y -qq --no-install-recommends certbot
    fi
    systemctl enable nginx >/dev/null 2>&1 || true

    # 2. Освобождаем порт 80 для HTTP-01 challenge (standalone)
    info "Останавливаю nginx на время выпуска сертификата (нужен свободный :80)..."
    systemctl stop nginx >/dev/null 2>&1 || true
    if port_in_use 80; then
        local who
        who="$(ss -tlnpH 'sport = :80' 2>/dev/null | head -1)"
        fatal "Порт 80 занят (не nginx). Освободите и перезапустите. Занят: $who"
    fi

    # 3. certbot certonly --standalone
    local certbot_args=(
        certonly --standalone
        -d "$DOMAIN"
        --non-interactive
        --agree-tos
        --keep-until-expiring
    )
    if [[ -n "$LE_EMAIL" ]]; then
        certbot_args+=(--email "$LE_EMAIL")
    else
        certbot_args+=(--register-unsafely-without-email)
    fi

    info "certbot ${certbot_args[*]}"
    if ! certbot "${certbot_args[@]}" 2>&1 | tee -a "$LOG_FILE"; then
        systemctl start nginx >/dev/null 2>&1 || true
        fatal "Не удалось получить Let's Encrypt сертификат для $DOMAIN. \
Проверьте: (1) A-запись DOMAIN указывает на этот сервер, (2) порт 80 доступен извне, (3) DNS пропагирован."
    fi
    LE_CERT_DIR="/etc/letsencrypt/live/$DOMAIN"
    [[ -f "$LE_CERT_DIR/fullchain.pem" ]] || fatal "$LE_CERT_DIR/fullchain.pem не найден после certbot."
    ok "Сертификат выпущен: $LE_CERT_DIR"

    # 4. Пишем nginx server-блок
    info "Создаю $NGINX_SITE_CONF..."
    local sub_path_clean="$SUB_PATH"
    [[ "${sub_path_clean:0:1}" == "/" ]] || sub_path_clean="/$sub_path_clean"
    [[ "${sub_path_clean: -1}" == "/" ]] || sub_path_clean="${sub_path_clean}/"
    local panel_path_clean="${PANEL_PATH%/}"
    [[ "${panel_path_clean:0:1}" == "/" ]] || panel_path_clean="/$panel_path_clean"

    cat >"$NGINX_SITE_CONF" <<NGINX
# Сгенерировано $SCRIPT_NAME $(date -Iseconds)

server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;

    # Оставляем /.well-known/acme-challenge/ для будущих renew через webroot.
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen $NGINX_PORT ssl;
    listen [::]:$NGINX_PORT ssl;
    http2 on;
    server_name $DOMAIN;

    ssl_certificate     $LE_CERT_DIR/fullchain.pem;
    ssl_certificate_key $LE_CERT_DIR/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;

    # Заголовки безопасности
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
    add_header X-Frame-Options SAMEORIGIN always;
    add_header X-Content-Type-Options nosniff always;

    client_max_body_size 50m;

    # 3x-ui admin panel
    location ${panel_path_clean}/ {
        proxy_pass http://127.0.0.1:${PANEL_PORT}${panel_path_clean}/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
    }

    # 3x-ui subscription server (XUI_SUB_BASE_URL)
    location ${sub_path_clean} {
        proxy_pass http://127.0.0.1:${SUB_PORT}${sub_path_clean};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location = / {
        return 404;
    }
}
NGINX
    mkdir -p /etc/nginx/sites-enabled
    ln -sf "$NGINX_SITE_CONF" "$NGINX_SITE_LINK"

    # 5. Сносим default-сайт если занимает :80/:443 — мы свой redirect уже отдаём
    if [[ -L /etc/nginx/sites-enabled/default ]]; then
        info "Отключаю /etc/nginx/sites-enabled/default (конфликт по server_name _)."
        rm -f /etc/nginx/sites-enabled/default
    fi

    # 6. Проверка и запуск nginx
    info "nginx -t"
    if ! nginx -t 2>&1 | tee -a "$LOG_FILE"; then
        fatal "nginx -t завершилась с ошибкой. Конфиг: $NGINX_SITE_CONF"
    fi
    systemctl restart nginx
    wait_service_active nginx 30
    ok "nginx запущен, панель доступна по $PANEL_BASE_PUBLIC/"

    # 7. Гарантируем что 3x-ui биндится только на 127.0.0.1 (на случай, если установщик не справился)
    info "Принудительно биндю панель 3x-ui на 127.0.0.1..."
    x-ui setting -listenIP "127.0.0.1" >/dev/null 2>&1 || warn "x-ui setting -listenIP не поддержан в этой версии CLI."
    systemctl restart x-ui >/dev/null 2>&1 || true

    # 8. Renew-hook: после успешного обновления сертификата перезагружать nginx
    mkdir -p /etc/letsencrypt/renewal-hooks/deploy
    cat >/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh <<'HOOK'
#!/usr/bin/env bash
systemctl reload nginx 2>/dev/null || true
HOOK
    chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
    ok "Renew-hook для nginx установлен."
}

# ---------------------------------------------------------------------- #
# Шаг 8: генерация .env
# ---------------------------------------------------------------------- #

ENV_PATH=""

write_env() {
    info "Шаг 8: генерация .env для Telegram-бота."
    local path_clean="${PANEL_PATH%/}"
    [[ -z "$path_clean" ]] || [[ "${path_clean:0:1}" == "/" ]] || path_clean="/$path_clean"

    local sub_path_with_slash="$SUB_PATH"
    [[ "${sub_path_with_slash:0:1}" == "/" ]] || sub_path_with_slash="/$sub_path_with_slash"
    [[ "${sub_path_with_slash: -1}" == "/" ]] || sub_path_with_slash="${sub_path_with_slash}/"

    if [[ "$INSTALL_BOT" == "true" ]]; then
        ENV_PATH="${BOT_DIR}/.env"
        mkdir -p "$BOT_DIR"
    else
        ENV_PATH="/root/3x-ui-tg-bot.env"
    fi

    if [[ -f "$ENV_PATH" ]]; then
        local answer="b"
        if [[ "$NON_INTERACTIVE" != "true" ]]; then
            read -r -p "$ENV_PATH уже существует. Перезаписать (o), сохранить .bak (b)? [b]: " answer
            answer="${answer:-b}"
        fi
        case "$answer" in
            o|O) info "Перезаписываю $ENV_PATH" ;;
            *)   cp -a "$ENV_PATH" "${ENV_PATH}.bak.$(date +%s)"; info "Бэкап создан: ${ENV_PATH}.bak.*" ;;
        esac
    fi

    local xui_base_url xui_sub_base_url xui_verify_ssl
    if [[ "$SSL_MODE" == "nginx" ]]; then
        local port_suffix=""
        [[ "$NGINX_PORT" != "443" ]] && port_suffix=":${NGINX_PORT}"
        xui_base_url="https://${DOMAIN}${port_suffix}${path_clean}"
        xui_sub_base_url="https://${DOMAIN}${port_suffix}${sub_path_with_slash}"
        xui_verify_ssl="true"
    else
        # skip-режим: панель HTTP-only, торчит напрямую
        xui_base_url="http://${DOMAIN}:${PANEL_PORT}${path_clean}"
        xui_sub_base_url="http://${DOMAIN}:${SUB_PORT}${sub_path_with_slash}"
        xui_verify_ssl="false"
    fi

    umask 077
    cat >"$ENV_PATH" <<ENVFILE
# Сгенерировано $SCRIPT_NAME $(date -Iseconds)
BOT_TOKEN=${BOT_TOKEN}
ADMIN_IDS=${ADMIN_IDS}
DB_PATH=./data/bot.db
XUI_BASE_URL=${xui_base_url}
XUI_USERNAME=${PANEL_USER}
XUI_PASSWORD=${PANEL_PASS}
XUI_INBOUND_ID=${INBOUND_ID}
XUI_SERVER_HOST=${DOMAIN}
XUI_SUB_BASE_URL=${xui_sub_base_url}
XUI_VERIFY_SSL=${xui_verify_ssl}
LOG_LEVEL=INFO
ENVFILE
    chmod 600 "$ENV_PATH"
    ok ".env записан в $ENV_PATH (XUI_BASE_URL=$xui_base_url)"
}

# ---------------------------------------------------------------------- #
# Шаг 9: установка бота (опционально)
# ---------------------------------------------------------------------- #

install_bot() {
    if [[ "$INSTALL_BOT" != "true" ]]; then
        return 0
    fi
    info "Шаг 9: установка Telegram-бота как systemd-сервиса."
    [[ -n "$BOT_REPO" ]] || fatal "--install-bot указан, но --bot-repo не задан."

    info "Устанавливаю python3, venv, git..."
    apt-get install -y -qq --no-install-recommends \
        python3 python3-venv python3-dev git build-essential

    # Проверка версии Python (>=3.12 требуется проектом)
    local pyver
    pyver="$(python3 -c 'import sys;print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
    info "Системный python3 = $pyver"
    if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)'; then
        warn "python3<3.12. Пробую установить python3.12 через deadsnakes PPA (только Ubuntu)."
        if grep -qi ubuntu /etc/os-release; then
            apt-get install -y -qq --no-install-recommends software-properties-common
            add-apt-repository -y ppa:deadsnakes/ppa || true
            apt-get update -y -qq
            apt-get install -y -qq --no-install-recommends python3.12 python3.12-venv python3.12-dev || \
                fatal "Не удалось установить python3.12. Поставьте его вручную и перезапустите."
            PYTHON_BIN="python3.12"
        else
            fatal "Нужен Python>=3.12. На Debian: соберите вручную или используйте контейнер."
        fi
    else
        PYTHON_BIN="python3"
    fi

    if ! id -u tgbot >/dev/null 2>&1; then
        info "Создаю системного пользователя 'tgbot'..."
        useradd -m -s /bin/bash tgbot
    fi

    if [[ -d "$BOT_DIR/.git" ]]; then
        warn "$BOT_DIR уже содержит git-репозиторий — делаю pull."
        sudo -u tgbot git -C "$BOT_DIR" pull --ff-only || warn "git pull не удался, продолжаю."
    else
        info "Клонирую $BOT_REPO → $BOT_DIR"
        # Если ENV_PATH = $BOT_DIR/.env, временно вынесем его на время клонирования
        local saved_env=""
        if [[ -f "$ENV_PATH" && "$ENV_PATH" == "$BOT_DIR/.env" ]]; then
            saved_env="$(mktemp)"
            mv "$ENV_PATH" "$saved_env"
        fi
        # git clone требует пустую целевую директорию
        if [[ -d "$BOT_DIR" ]]; then
            rmdir "$BOT_DIR" 2>/dev/null || fatal "$BOT_DIR не пуст и не git-репо."
        fi
        sudo -u tgbot mkdir -p "$BOT_DIR" || true
        chown tgbot:tgbot "$BOT_DIR"
        sudo -u tgbot git clone "$BOT_REPO" "$BOT_DIR" || fatal "git clone не удался."
        if [[ -n "$saved_env" ]]; then
            mv "$saved_env" "$BOT_DIR/.env"
            chown tgbot:tgbot "$BOT_DIR/.env"
            chmod 600 "$BOT_DIR/.env"
        fi
    fi

    chown -R tgbot:tgbot "$BOT_DIR"

    info "Создаю venv: $BOT_DIR/.venv (python=$PYTHON_BIN)"
    sudo -u tgbot "$PYTHON_BIN" -m venv "$BOT_DIR/.venv"
    info "pip install -e $BOT_DIR"
    sudo -u tgbot "$BOT_DIR/.venv/bin/pip" install --upgrade pip wheel >/dev/null
    sudo -u tgbot "$BOT_DIR/.venv/bin/pip" install -e "$BOT_DIR" || fatal "pip install -e не удался."

    local svc_src="$BOT_DIR/deploy/tg-vpn-bot.service"
    if [[ -f "$svc_src" ]]; then
        cp "$svc_src" /etc/systemd/system/tg-vpn-bot.service
    else
        warn "$svc_src не найден, создаю минимальный systemd-юнит."
        cat >/etc/systemd/system/tg-vpn-bot.service <<UNIT
[Unit]
Description=3x-ui Telegram VPN bot
After=network.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$BOT_DIR
EnvironmentFile=$BOT_DIR/.env
ExecStart=$BOT_DIR/.venv/bin/python -m app.main
Restart=on-failure
RestartSec=5
User=tgbot
Group=tgbot
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tg-vpn-bot

[Install]
WantedBy=multi-user.target
UNIT
    fi

    systemctl daemon-reload
    systemctl enable --now tg-vpn-bot
    sleep 3
    info "Последние логи бота:"
    journalctl -u tg-vpn-bot -n 20 --no-pager >&2 || true

    if systemctl is-active --quiet tg-vpn-bot; then
        ok "tg-vpn-bot запущен."
    else
        warn "tg-vpn-bot не активен — проверьте журнал: journalctl -u tg-vpn-bot -n 50"
    fi
}

# ---------------------------------------------------------------------- #
# Шаг 10: финальный отчёт
# ---------------------------------------------------------------------- #

final_report() {
    # Готовим динамические куски заранее, чтобы не плодить nested heredoc внутри $(...)
    local sub_url ssl_block extra_checks=""
    if [[ "$SSL_MODE" == "nginx" ]]; then
        local _ps=""
        [[ "$NGINX_PORT" != "443" ]] && _ps=":${NGINX_PORT}"
        sub_url="https://${DOMAIN}${_ps}${SUB_PATH}"
        ssl_block="  Nginx:      listen :${NGINX_PORT} ssl, конфиг ${NGINX_SITE_CONF}
  Сертификат: ${LE_CERT_DIR}/fullchain.pem (Let s Encrypt)
  Renew:      systemd timer certbot.timer (deploy-hook перезагружает nginx)"
        extra_checks="  systemctl status nginx
  certbot certificates"
    else
        sub_url="http://${DOMAIN}:${SUB_PORT}${SUB_PATH}"
        ssl_block="  Без TLS. Панель торчит на ${PANEL_BASE_PUBLIC}/ наружу — поставьте reverse-proxy или используйте SSH-туннель."
    fi

    cat >&2 <<REPORT

${C_GREEN}${C_BOLD}===== УСТАНОВКА 3X-UI ЗАВЕРШЕНА =====${C_RESET}

${C_BOLD}Панель 3x-ui${C_RESET}
  URL:      ${PANEL_BASE_PUBLIC}/
  Login:    ${PANEL_USER}
  Password: ${PANEL_PASS}

${C_BOLD}VLESS+Reality inbound${C_RESET}
  ID:           ${INBOUND_ID}
  Port:         ${VLESS_PORT}
  Reality dest: ${REALITY_DEST}
  Reality SNI:  ${REALITY_SNI}
  Public key:   ${REALITY_PUBLIC_KEY}
  Short ID:     ${REALITY_SHORT_ID}

${C_BOLD}Subscription${C_RESET}
  URL: ${sub_url}

${C_BOLD}SSL / nginx${C_RESET}
  Режим:     ${SSL_MODE}
${ssl_block}

${C_BOLD}Файл .env${C_RESET}
  Путь: ${ENV_PATH}
  Права: 600

${C_BOLD}Проверки${C_RESET}
  systemctl status x-ui
  curl -k -I ${PANEL_BASE_PUBLIC}/
${extra_checks}
REPORT
    if [[ "$INSTALL_BOT" == "true" ]]; then
        cat >&2 <<REPORT
  systemctl status tg-vpn-bot
  journalctl -u tg-vpn-bot -f
REPORT
    else
        cat >&2 <<REPORT

${C_BOLD}Как развернуть бота${C_RESET}
  1. Скопируйте ${ENV_PATH} → ${BOT_DIR}/.env (после установки бота)
  2. Или перезапустите этот скрипт с --install-bot --bot-repo=<url>
REPORT
    fi
    cat >&2 <<REPORT

${C_BOLD}Бэкапы${C_RESET}
  - 3x-ui DB: $XUI_DB
  - Bot DB:   ${BOT_DIR}/data/bot.db (если установлен бот)
  - .env:     ${ENV_PATH}

${C_YELLOW}Не публикуйте пароли и .env в открытых репозиториях.${C_RESET}

REPORT
}

# ---------------------------------------------------------------------- #
# Заполнение/валидация параметров
# ---------------------------------------------------------------------- #

finalize_params() {
    # Обязательные
    [[ -n "$BOT_TOKEN" ]] || ask_secret BOT_TOKEN "Telegram BOT_TOKEN"
    [[ -n "$ADMIN_IDS" ]] || ask        ADMIN_IDS "Telegram ADMIN_IDS (CSV)"
    [[ -n "$DOMAIN"    ]] || ask        DOMAIN    "FQDN сервера (например vpn.example.com)"

    # Опциональные с дефолтами
    [[ -n "$PANEL_PORT" ]] || PANEL_PORT="$(rand_port)"
    [[ -n "$PANEL_PASS" ]] || PANEL_PASS="$(rand_base64 18)"
    [[ -n "$PANEL_PATH" ]] || PANEL_PATH="/$(rand_hex 6)/"
    # нормализация PANEL_PATH: всегда /xxx/
    [[ "${PANEL_PATH:0:1}" == "/" ]] || PANEL_PATH="/$PANEL_PATH"
    [[ "${PANEL_PATH: -1}" == "/" ]] || PANEL_PATH="${PANEL_PATH}/"

    # REALITY_SNI: если не задан — берём host из reality-dest
    if [[ -z "$REALITY_SNI" ]]; then
        REALITY_SNI="${REALITY_DEST%%:*}"
    fi

    # SSL_MODE: auto -> nginx если DOMAIN это FQDN, иначе skip
    case "$SSL_MODE" in
        auto)
            if [[ "$DOMAIN" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
                SSL_MODE="skip"
                warn "DOMAIN=$DOMAIN похож на IP — переключаю SSL_MODE=skip (LE для IP не поддержано в этом скрипте)."
            elif [[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
                SSL_MODE="nginx"
            else
                SSL_MODE="skip"
                warn "DOMAIN=$DOMAIN не похож ни на FQDN, ни на IP — SSL_MODE=skip."
            fi
            ;;
        nginx|skip) ;;
        *) fatal "Неизвестный --ssl-mode=$SSL_MODE (допустимо auto|nginx|skip)." ;;
    esac

    # NGINX_PORT: auto. Если nginx-режим и VLESS=443 — берём 8443; иначе 443.
    if [[ "$SSL_MODE" == "nginx" ]]; then
        if [[ "$NGINX_PORT" == "auto" ]]; then
            if [[ "$VLESS_PORT" == "443" ]]; then
                NGINX_PORT="8443"
                warn "VLESS_PORT=443 и nginx по умолчанию занимает 443 — переношу nginx на 8443."
                warn "Если хотите наоборот (nginx на 443, VLESS на 8443) — задайте --vless-port=8443 --nginx-port=443."
            else
                NGINX_PORT="443"
            fi
        fi
        if [[ "$NGINX_PORT" == "$VLESS_PORT" ]]; then
            fatal "NGINX_PORT=$NGINX_PORT совпадает с VLESS_PORT=$VLESS_PORT. Задайте разные."
        fi
    else
        NGINX_PORT=""
    fi

    # Валидация числовых полей
    local port_vars=(PANEL_PORT VLESS_PORT SUB_PORT)
    [[ -n "$NGINX_PORT" ]] && port_vars+=(NGINX_PORT)
    for var in "${port_vars[@]}"; do
        local v="${!var}"
        if ! [[ "$v" =~ ^[0-9]+$ ]] || (( v < 1 || v > 65535 )); then
            fatal "$var=$v — не валидный порт (1..65535)."
        fi
    done

    # Проверка занятости панель/sub-портов (vless проверим перед созданием inbound)
    if port_in_use "$PANEL_PORT"; then
        fatal "PANEL_PORT=$PANEL_PORT уже занят. Передайте другой через --panel-port."
    fi
    if port_in_use "$SUB_PORT"; then
        warn "SUB_PORT=$SUB_PORT уже занят — sub-сервер 3x-ui может не запуститься на этом порту."
    fi

    # Установка бота требует bot-repo
    if [[ "$INSTALL_BOT" == "true" && -z "$BOT_REPO" ]]; then
        if [[ "$NON_INTERACTIVE" == "true" ]]; then
            fatal "--install-bot указан, но --bot-repo не задан."
        fi
        ask BOT_REPO "git URL репозитория бота"
    fi

    # ADMIN_IDS: убрать пробелы, проверить что это int csv
    ADMIN_IDS="$(tr -d '[:space:]' <<<"$ADMIN_IDS")"
    if ! [[ "$ADMIN_IDS" =~ ^[0-9]+(,[0-9]+)*$ ]]; then
        fatal "ADMIN_IDS должен быть CSV целых чисел (например 12345,67890). Получено: '$ADMIN_IDS'"
    fi

    build_panel_urls
}

# ---------------------------------------------------------------------- #
# main
# ---------------------------------------------------------------------- #

main() {
    parse_args "$@"
    info "Старт $SCRIPT_NAME"

    ensure_root
    ensure_os
    init_log_file

    finalize_params

    info "Конфигурация:"
    info "  domain         = $DOMAIN"
    info "  panel_port     = $PANEL_PORT"
    info "  panel_user     = $PANEL_USER"
    info "  panel_path     = $PANEL_PATH"
    info "  vless_port     = $VLESS_PORT"
    info "  reality_dest   = $REALITY_DEST"
    info "  reality_sni    = $REALITY_SNI"
    info "  sub_port       = $SUB_PORT"
    info "  sub_path       = $SUB_PATH"
    info "  install_bot    = $INSTALL_BOT"
    info "  admin_ids      = $ADMIN_IDS"
    info "  ssl_mode       = $SSL_MODE"
    info "  nginx_port     = ${NGINX_PORT:-n/a}"
    info "  le_email       = ${LE_EMAIL:-<none>}"

    preflight
    configure_ufw
    install_3x_ui
    configure_panel_settings
    panel_login
    configure_sub_via_api
    generate_reality_keys
    create_inbound
    setup_nginx_panel
    write_env
    install_bot
    final_report

    ok "Готово."
}

main "$@"
