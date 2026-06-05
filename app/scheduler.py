"""APScheduler — фоновые задачи бота.

Поверх :class:`apscheduler.schedulers.asyncio.AsyncIOScheduler` живёт три
периодические job-а, обслуживающие жизненный цикл подписок:

* :func:`expire_check_job` — раз в час: переводит активные подписки с
  ``expires_at <= now`` в статус ``expired``, выключает соответствующего
  клиента в 3x-ui (``update_client(enable=False)``) и шлёт юзеру финальное
  уведомление «Подписка истекла».
* :func:`reminders_job` — раз в сутки: рассылает предупреждения за 3, 1 и 0
  дней до истечения. Дубли защищены таблицей ``subscription_notifications``
  (UNIQUE на ``(subscription_id, kind)``).
* :func:`traffic_snapshot_job` — раз в 6 часов: для каждой активной
  подписки запрашивает ``getClientTraffics`` и пишет snapshot в
  ``traffic_snapshots`` для построения графиков.
* :func:`health_check_job` — каждые ~30 минут: пробует достучаться до
  3x-ui панели (``list_inbounds`` с таймаутом), пишет состояние в
  ``health_status`` и шлёт алерт админам ТОЛЬКО при смене состояния
  up↔down (чтобы не спамить).

Все job-ы максимально устойчивы к ошибкам отдельных подписок: исключение в
одной итерации логируется через ``loguru`` и не валит ни весь job, ни
сам scheduler. Bot-инстанс пробрасывается через closure в
:func:`setup_scheduler`, поэтому модуль не лезет в импорты ``main`` (no
circular imports).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Literal

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

import aiosqlite

from app.config import settings
from app.db.engine import get_conn
from app.db.repos import health as health_repo
from app.db.repos import payments as payments_repo
from app.db.repos import plans as plans_repo
from app.db.repos import subscriptions as subs_repo
from app.db.repos import users as users_repo
from app.db.repos import wallet as wallet_repo
from app.i18n import DEFAULT_LANG, t
from app.keyboards.user import renew_reminder_kb
from app.services import billing
from app.services import health as health_service
from app.services import subscriptions as subs_service
from app.services import wallet as wallet_service
from app.xui import XuiError, get_xui_client
from app.xui.clients import get_client_traffics, update_client

# Bytes in one gigabyte (binary) — plan ``traffic_gb`` is forwarded to the
# panel as ``totalGB`` using this factor, so the alert threshold must use the
# same one to compare like-for-like with the panel's ``up + down`` counters.
_BYTES_PER_GB = 1024**3

# Тип «насколько близок дедлайн» — совпадает с CHECK-constraint в БД.
ReminderKind = Literal["3d", "1d", "0d"]


def _reminder_text(kind: ReminderKind, lang: str = DEFAULT_LANG) -> str:
    """Локализованный текст напоминания за N дней (``reminder.<kind>``).

    Тексты вынесены в каталоги :mod:`app.i18n`; язык берётся из ``user.lang``
    в :func:`reminders_job`. Дефолт ``ru`` сохраняет прежний текст.
    """
    return t(f"reminder.{kind}", lang)


def _expired_text(lang: str = DEFAULT_LANG) -> str:
    """Локализованный текст после истечения подписки (``reminder.expired``)."""
    return t("reminder.expired", lang)


# --------------------------------------------------------------------------- #
# Утилиты
# --------------------------------------------------------------------------- #


def _parse_iso(value: str) -> datetime:
    """Парсит ISO-строку из БД в aware-datetime (UTC).

    Подписки в БД хранятся через `_to_iso` (см. `db/repos/subscriptions.py`)
    в формате ``YYYY-MM-DD HH:MM:SS`` без TZ-маркера, иногда — с ``+00:00``.
    Здесь мы нормализуем оба случая в aware UTC.
    """
    # ``datetime.fromisoformat`` понимает оба варианта в 3.11+.
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _days_left(expires_at: str, now: datetime) -> int:
    """Сколько целых суток осталось до истечения (отрицательное = просрочено).

    Считаем по числу полных календарных суток разницы; используется только
    для маппинга на kind ('3d'/'1d'/'0d').
    """
    deadline = _parse_iso(expires_at)
    delta = deadline - now
    # ``delta.days`` округляется вниз: 0d <= 24h, 1d <= 48h и т.д.
    return delta.days


def _kind_for_days_left(days_left: int) -> ReminderKind | None:
    """Маппит «дней осталось» в kind напоминания.

    Возвращает ``None``, если подписке не пора слать ни одно из 3d/1d/0d
    напоминаний (например, осталось 5 дней — рано, или -2 — это уже работа
    expire-checker'а).
    """
    if days_left >= 3 and days_left < 4:
        return "3d"
    if days_left >= 1 and days_left < 2:
        return "1d"
    if days_left == 0:
        return "0d"
    return None


async def _safe_send(
    bot: Bot,
    tg_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Шлёт сообщение пользователю, проглатывая Telegram-ошибки.

    Юзер мог заблокировать бота, удалить чат или быть deactivated — это не
    повод валить job. Любая ошибка только логируется.

    ``reply_markup`` — опциональная inline-клавиатура (например, кнопка
    «Продлить» в напоминаниях и трафик-алертах из Ф4). При ``None``
    сообщение отправляется без клавиатуры — поведение существующих
    вызовов не меняется.
    """
    try:
        await bot.send_message(tg_id, text, reply_markup=reply_markup)
    except TelegramAPIError as exc:
        logger.warning(
            "scheduler: send_message failed tg_id={} err={}",
            tg_id,
            exc,
        )


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #


async def expire_check_job(bot: Bot) -> None:
    """Отключает истёкшие подписки и шлёт финальное уведомление.

    Алгоритм:

    1. Берём `list_expired_active(now)` — `status='active'` и
       `expires_at <= now`.
    2. Для каждой подписки:
       * `xui.update_client(enable=False)` — попытка дисейблить клиента в
         3x-ui (ошибка не валит цикл).
       * `subscriptions_repo.set_status(sub.id, 'expired')`.
       * Если уведомления kind='expired' ещё не было — шлём пользователю
         финальное сообщение и фиксируем факт.
    3. Идём дальше; ошибка в одной подписке не должна влиять на остальные.
    """
    logger.info("scheduler: expire_check_job start")
    sent_count = 0
    expired_count = 0

    try:
        async with get_conn() as conn:
            expired = await subs_repo.list_expired_active(conn)
    except Exception as exc:  # noqa: BLE001 — top-level safety net
        logger.exception("scheduler: expire_check_job failed to list expired: {}", exc)
        return

    if not expired:
        logger.info("scheduler: expire_check_job — no subscriptions to expire")
        return

    xui = None
    try:
        xui = await get_xui_client()
    except Exception as exc:  # noqa: BLE001
        # Без xui-клиента не сможем дисейблить — но статусы в БД всё равно
        # обновим, иначе мы навсегда зависнем на «истекших».
        logger.error("scheduler: cannot get xui client: {}", exc)

    for sub in expired:
        # 1) Disable в 3x-ui — soft-fail.
        if xui is not None:
            try:
                await update_client(
                    xui,
                    email=sub.xui_client_email,
                    enable=False,
                )
            except XuiError as exc:
                logger.warning(
                    "scheduler: xui.update_client(disable) failed sub_id={} err={}",
                    sub.id,
                    exc,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "scheduler: unexpected error disabling client sub_id={}: {}",
                    sub.id,
                    exc,
                )

        # 2) Перевод статуса в expired + уведомление через тот же conn,
        #    чтобы dedup и пометка статуса делались атомарно с точки зрения
        #    одной подписки.
        try:
            async with get_conn() as conn:
                await subs_repo.set_status(conn, sub.id, "expired")
                expired_count += 1

                should_send = await subs_repo.try_mark_notification_sent(
                    conn, sub.id, "expired"
                )

                user = await users_repo.get_by_id(conn, sub.user_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "scheduler: DB error while expiring sub_id={}: {}", sub.id, exc
            )
            continue

        if should_send and user is not None:
            await _safe_send(bot, user.tg_id, _expired_text(user.lang))
            sent_count += 1

    logger.info(
        "scheduler: expire_check_job done expired={} notified={}",
        expired_count,
        sent_count,
    )


async def reminders_job(bot: Bot) -> None:
    """Шлёт напоминания за 3 / 1 / 0 дней до истечения.

    Берём всех с активной подпиской, у которой ``expires_at`` попадает в
    окно ближайших 3 суток, маппим число оставшихся дней в ``ReminderKind``,
    дедуплицируем через ``subscription_notifications`` (UNIQUE-constraint)
    и шлём по одному сообщению на пользователя/подписку/kind.
    """
    logger.info("scheduler: reminders_job start")
    now = datetime.now(UTC).replace(microsecond=0)
    sent_count = 0

    try:
        async with get_conn() as conn:
            candidates = await subs_repo.list_expiring_in(conn, days=3)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "scheduler: reminders_job failed to list expiring: {}", exc
        )
        return

    if not candidates:
        logger.info("scheduler: reminders_job — nothing to remind")
        return

    for sub in candidates:
        try:
            days_left = _days_left(sub.expires_at, now)
        except ValueError as exc:
            logger.warning(
                "scheduler: bad expires_at sub_id={} value={!r} err={}",
                sub.id,
                sub.expires_at,
                exc,
            )
            continue

        kind = _kind_for_days_left(days_left)
        if kind is None:
            # Не наш слот — пропускаем (3+d, или уже < 0).
            continue

        try:
            async with get_conn() as conn:
                should_send = await subs_repo.try_mark_notification_sent(
                    conn, sub.id, kind
                )
                user = await users_repo.get_by_id(conn, sub.user_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "scheduler: DB error in reminders_job sub_id={}: {}", sub.id, exc
            )
            continue

        if not should_send:
            # Уже слали этот kind для этой подписки — пропускаем.
            continue
        if user is None:
            logger.warning("scheduler: orphan subscription sub_id={} (no user)", sub.id)
            continue

        # Прикрепляем кнопку «🔁 Продлить в 1 тап» — ведёт в существующий
        # extend-флоу (BuyCB(action='extend', sub_id=...)), чтобы юзер мог
        # продлить подписку прямо из напоминания, не открывая меню. Все три
        # kind'а (3d/1d/0d) шлются для ещё-активных подписок, поэтому кнопка
        # уместна на каждом.
        await _safe_send(
            bot,
            user.tg_id,
            _reminder_text(kind, user.lang),
            reply_markup=renew_reminder_kb(sub.id, user.lang),
        )
        sent_count += 1

    logger.info("scheduler: reminders_job done sent={}", sent_count)


async def _maybe_alert_traffic(bot: Bot, sub: subs_repo.Subscription, total: int) -> bool:
    """Шлёт одноразовый алерт «израсходовано N% трафика», если порог пройден.

    Сравнивает накопленный трафик ``total`` (``up + down`` в байтах) с квотой
    тарифа подписки (``plan.traffic_gb`` × :data:`_BYTES_PER_GB`). Когда доля
    достигает ``settings.TRAFFIC_ALERT_PERCENT`` — отправляет пользователю
    одноразовое уведомление, дедуплицированное через
    ``subscription_notifications`` (kind ``'traffic80'``).

    Возвращает ``True``, если алерт был отправлен (для метрик job-а).

    Алерт пропускается, когда:

    * порог выключен (``TRAFFIC_ALERT_PERCENT == 0``);
    * у тарифа безлимит (``traffic_gb == 0``) или тариф недоступен;
    * порог ещё не достигнут;
    * алерт уже отправлялся (dedup).
    """
    percent = int(settings.TRAFFIC_ALERT_PERCENT)
    if percent <= 0:
        return False
    if sub.plan_id is None:
        return False

    async with get_conn() as conn:
        plan = await plans_repo.get(conn, sub.plan_id)
    if plan is None or int(plan.traffic_gb) <= 0:
        # Безлимитный тариф (или тариф удалён) — квоты нет, алерт не нужен.
        return False

    quota_bytes = int(plan.traffic_gb) * _BYTES_PER_GB
    threshold = quota_bytes * percent // 100
    if total < threshold:
        return False

    # Порог пройден — фиксируем once-only факт и шлём DM.
    try:
        async with get_conn() as conn:
            should_send = await subs_repo.try_mark_notification_sent(
                conn, sub.id, "traffic80"
            )
            user = await users_repo.get_by_id(conn, sub.user_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "scheduler: traffic-alert DB error sub_id={}: {}", sub.id, exc
        )
        return False

    if not should_send or user is None:
        return False

    await _safe_send(
        bot,
        user.tg_id,
        t("traffic.alert", user.lang, percent=percent, sub_id=sub.id),
        reply_markup=renew_reminder_kb(sub.id, user.lang),
    )
    return True


async def traffic_snapshot_job(bot: Bot) -> None:
    """Снимает трафик-снапшот для каждой активной подписки + трафик-алерты.

    Ошибки 3x-ui по конкретной подписке — log + skip; ошибки записи в БД
    — log + skip. Главное — job не падает целиком из-за одного клиента.

    После записи снапшота для каждой подписки сравнивает накопленный трафик
    с квотой тарифа и при пороге ``settings.TRAFFIC_ALERT_PERCENT`` шлёт
    одноразовый алерт через :func:`_maybe_alert_traffic` (dedup через
    ``subscription_notifications``). ``bot`` используется именно для отправки
    этих алертов.
    """
    logger.info("scheduler: traffic_snapshot_job start")
    written = 0
    alerted = 0

    try:
        async with get_conn() as conn:
            active = await subs_repo.list_active(conn)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "scheduler: traffic_snapshot_job failed to list active: {}", exc
        )
        return

    if not active:
        logger.info("scheduler: traffic_snapshot_job — no active subscriptions")
        return

    try:
        xui = await get_xui_client()
    except Exception as exc:  # noqa: BLE001
        logger.error("scheduler: cannot get xui client: {}", exc)
        return

    for sub in active:
        try:
            traffics = await get_client_traffics(xui, sub.xui_client_email)
        except XuiError as exc:
            logger.warning(
                "scheduler: get_client_traffics failed sub_id={} email={} err={}",
                sub.id,
                sub.xui_client_email,
                exc,
            )
            continue
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "scheduler: unexpected xui error sub_id={}: {}", sub.id, exc
            )
            continue

        # 3x-ui может вернуть пустой dict, если клиент не найден — пропускаем.
        if not traffics:
            logger.debug(
                "scheduler: empty traffics for sub_id={} email={}",
                sub.id,
                sub.xui_client_email,
            )
            continue

        up = int(traffics.get("up", 0) or 0)
        down = int(traffics.get("down", 0) or 0)

        try:
            async with get_conn() as conn:
                await subs_repo.add_traffic_snapshot(conn, sub.id, up, down)
            written += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "scheduler: failed to save snapshot sub_id={}: {}", sub.id, exc
            )
            continue

        # Трафик-алерт — одноразовое уведомление при достижении порога квоты.
        # Изолирован в try/except, чтобы ошибка алерта не валила снапшот-цикл.
        try:
            if await _maybe_alert_traffic(bot, sub, up + down):
                alerted += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "scheduler: traffic-alert failed sub_id={}: {}", sub.id, exc
            )

    logger.info(
        "scheduler: traffic_snapshot_job done written={} alerted={}",
        written,
        alerted,
    )


async def _renew_one_from_wallet(bot: Bot, sub: subs_repo.Subscription) -> bool:
    """Продлевает одну подписку списанием с баланса. Возвращает успех.

    Алгоритм для одной подписки из :func:`subs_repo.list_auto_renew_due`:

    1. Резолвим тариф (``sub.plan_id``) и его цену
       ``billing.calc_price(plan, None).stars`` (промо к автопродлению не
       применяются).
    2. ``wallet.try_spend(user_id, price, ref="autorenew:<sub>:<period>")``,
       где ``period`` — текущий ``expires_at`` подписки (ISO). Детерминированный
       ref делает списание replay-safe: повторный запуск job-а в тот же период
       (до того как ``expires_at`` сдвинется) не спишет дважды.
    3. На нехватку баланса — DM «не хватает баланса», без продления.
    4. На успех — ``create_or_extend(extend_sub_id=sub.id)`` (xui-first);
       при ошибке xui рефандим списание. Затем синтетический ``payments``-row
       (``telegram_charge_id="wallet:autorenew:<txn_id>"``) для статистики и
       DM пользователю.

    Любая ошибка возвращается наружу/логируется вызывающим
    :func:`auto_renew_job` (per-sub try/except), чтобы одна неудача не валила
    весь job.
    """
    async with get_conn() as conn:
        plan = await plans_repo.get(conn, sub.plan_id) if sub.plan_id else None
        user = await users_repo.get_by_id(conn, sub.user_id)
    if plan is None or user is None:
        logger.warning(
            "auto_renew: skip sub_id={} (plan={} user={})",
            sub.id,
            sub.plan_id,
            sub.user_id,
        )
        return False

    price = billing.calc_price(plan, None).stars
    # ``period`` фиксирует текущий период подписки — пока ``expires_at`` не
    # сдвинут продлением, ref остаётся прежним и второе списание отклоняется.
    period = sub.expires_at
    spend_ref = f"autorenew:{sub.id}:{period}"

    async with get_conn() as conn:
        spent = await wallet_service.try_spend(conn, user.id, price, ref=spend_ref)
    if not spent:
        # Либо нехватка баланса, либо replay (уже списали за этот период).
        async with get_conn() as conn:
            existing = await wallet_repo.get_by_ref(conn, spend_ref)
        if existing is not None:
            # Уже списывали за этот период — идемпотентный no-op, без DM.
            logger.info(
                "auto_renew: sub_id={} already charged for period {} — skip",
                sub.id,
                period,
            )
            return False
        # Реальная нехватка баланса — уведомляем юзера.
        await _safe_send(
            bot,
            user.tg_id,
            t("autorenew.insufficient_dm", user.lang, sub_id=sub.id, stars=price),
        )
        return False

    # Восстанавливаем txn id для синтетического платежа / возможного рефанда.
    async with get_conn() as conn:
        spend_txn = await wallet_repo.get_by_ref(conn, spend_ref)
    txn_id = spend_txn.id if spend_txn is not None else 0

    # Провижининг (xui-first). При ошибке — рефанд и выход.
    xui = await get_xui_client()
    try:
        async with get_conn() as conn:
            renewed = await subs_service.create_or_extend(
                conn=conn,
                xui=xui,
                user=user,
                plan=plan,
                promo=None,
                inbound_id=int(sub.xui_inbound_id),
                extend_sub_id=sub.id,
            )
    except XuiError as exc:
        logger.error(
            "auto_renew: xui provisioning failed sub_id={} txn={}: {}; refunding",
            sub.id,
            txn_id,
            exc,
        )
        async with get_conn() as conn:
            await wallet_service.credit(
                conn,
                user.id,
                price,
                type="refund",
                ref=f"refund:autorenew:{txn_id}",
            )
        return False

    # Синтетический платёж для статистики (dedup по UNIQUE charge_id).
    synthetic_charge_id = f"wallet:autorenew:{txn_id}"
    async with get_conn() as conn:
        try:
            await payments_repo.create(
                conn,
                user_id=user.id,
                subscription_id=renewed.id,
                telegram_charge_id=synthetic_charge_id,
                stars_amount=price,
                plan_id=plan.id,
                promo_id=None,
            )
        except aiosqlite.IntegrityError:
            logger.info(
                "auto_renew: duplicate synthetic payment {} — fine",
                synthetic_charge_id,
            )

    new_until = renewed.expires_at[:10] if renewed.expires_at else renewed.expires_at
    await _safe_send(
        bot,
        user.tg_id,
        t(
            "autorenew.renewed_dm",
            user.lang,
            sub_id=sub.id,
            stars=price,
            date=new_until,
        ),
    )
    logger.info(
        "auto_renew: sub_id={} renewed for {}⭐ → {}",
        sub.id,
        price,
        renewed.expires_at,
    )
    return True


async def auto_renew_job(bot: Bot) -> None:
    """Fallback-автопродление: списывает с баланса due-подписки.

    Покрывает подписки с ``auto_renew=1 AND tg_sub_charge_id IS NULL`` (т.е. НЕ
    нативные Telegram Star Subscriptions — те Telegram продлевает сам). Для
    каждой подписки, истекающей в ближайшие 24 часа, пытается списать стоимость
    тарифа с внутреннего Stars-баланса пользователя и продлить её.

    Управляется флагом ``settings.AUTO_RENEW_ENABLED`` — при ``False`` job
    немедленно завершается (in-flight нативные подписки это не затрагивает).

    Каждая подписка обрабатывается в отдельном try/except, поэтому ошибка по
    одной не валит остальные и сам job.
    """
    logger.info("scheduler: auto_renew_job start")
    if not settings.AUTO_RENEW_ENABLED:
        logger.info("scheduler: auto_renew_job — disabled via AUTO_RENEW_ENABLED")
        return

    try:
        async with get_conn() as conn:
            due = await subs_repo.list_auto_renew_due(conn, within_hours=24)
    except Exception as exc:  # noqa: BLE001
        logger.exception("scheduler: auto_renew_job failed to list due: {}", exc)
        return

    if not due:
        logger.info("scheduler: auto_renew_job — nothing due")
        return

    renewed_count = 0
    for sub in due:
        try:
            if await _renew_one_from_wallet(bot, sub):
                renewed_count += 1
        except Exception as exc:  # noqa: BLE001 — одна подписка не валит job
            logger.exception(
                "scheduler: auto_renew_job error for sub_id={}: {}", sub.id, exc
            )

    logger.info("scheduler: auto_renew_job done renewed={}", renewed_count)


async def _alert_admins(bot: Bot, text: str) -> None:
    """Fan a health alert out to every admin DM and the optional support chat.

    Targets are deduplicated ``settings.ADMIN_IDS`` plus
    ``settings.SUPPORT_CHAT_ID`` when set — same recipient policy the support
    ticket notifier uses. Each send is best-effort: a failure to reach one
    recipient (blocked the bot, never started it) is logged and does not abort
    the rest. Reuses :func:`_safe_send` for per-recipient resilience.
    """
    targets: list[int] = list(dict.fromkeys(int(a) for a in settings.ADMIN_IDS))
    if settings.SUPPORT_CHAT_ID:
        targets.append(int(settings.SUPPORT_CHAT_ID))
    for chat_id in targets:
        await _safe_send(bot, chat_id, text)


async def health_check_job(bot: Bot) -> None:
    """Probe the 3x-ui panel and alert admins only on an up↔down transition.

    Algorithm:

    1. Acquire the panel client and run :func:`app.services.health.check_xui_health`
       (a lightweight ``list_inbounds`` under a tight timeout). A failure to
       obtain the client is itself treated as ``down``.
    2. Map the probe result to a ``'up'`` / ``'down'`` state and persist it via
       :func:`app.db.repos.health.record`, which reports whether the state
       *changed* from the previously stored one.
    3. Refresh the process-local snapshot (:func:`health.set_cached_status`) so
       user-facing location keyboards can render a 🟢/🔴 indicator without
       hitting the panel.
    4. Alert admins **only** when the state changed — guaranteeing exactly one
       notification per transition and no per-probe spam.

    The whole body is wrapped so any unexpected error is logged and never
    propagates into the scheduler.
    """
    logger.info("scheduler: health_check_job start")

    ok: bool
    error: str | None
    try:
        xui = await get_xui_client()
    except Exception as exc:  # noqa: BLE001 — no client == panel unreachable
        ok, error = False, f"cannot obtain xui client: {exc}"
        logger.warning("scheduler: health_check_job {}", error)
    else:
        ok, error = await health_service.check_xui_health(xui)

    status: health_repo.HealthState = "up" if ok else "down"

    try:
        async with get_conn() as conn:
            _row, changed = await health_repo.record(
                conn, status=status, last_error=error
            )
    except Exception as exc:  # noqa: BLE001 — DB failure must not crash the job
        logger.exception("scheduler: health_check_job failed to persist: {}", exc)
        return

    # Publish the snapshot for keyboards regardless of whether it changed.
    health_service.set_cached_status(status)

    if changed:
        if ok:
            text = t("health.alert_up", DEFAULT_LANG)
        else:
            text = t("health.alert_down", DEFAULT_LANG, error=error or "unknown")
        await _alert_admins(bot, text)
        logger.info(
            "scheduler: health_check_job state CHANGED -> {} (alerted admins)",
            status,
        )
    else:
        logger.info("scheduler: health_check_job steady state={}", status)


# --------------------------------------------------------------------------- #
# Регистрация и lifecycle
# --------------------------------------------------------------------------- #


def _wrap(
    job: Callable[[Bot], Awaitable[None]],
    bot: Bot,
    name: str,
) -> Callable[[], Awaitable[None]]:
    """Closure-обёртка: фиксирует bot и ловит любые исключения job-а.

    APScheduler логирует исключения сам, но мы хотим контролируемый
    user-friendly формат, и хотим быть уверены, что один упавший job
    не остановит scheduler.
    """

    async def _runner() -> None:
        try:
            await job(bot)
        except Exception as exc:  # noqa: BLE001
            logger.exception("scheduler: job '{}' crashed: {}", name, exc)

    _runner.__name__ = f"_runner_{name}"
    return _runner


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Создаёт и наполняет :class:`AsyncIOScheduler` четырьмя job-ами.

    Не стартует scheduler — это ответственность вызывающей стороны
    (`scheduler.start()` в `app/main.py`), чтобы можно было настроить
    timezone / event-listeners перед запуском.
    """
    scheduler = AsyncIOScheduler(timezone="UTC")

    # 1) Expiry checker — раз в час, в начале часа (минута 0).
    scheduler.add_job(
        _wrap(expire_check_job, bot, "expire_check"),
        trigger=CronTrigger(minute=0, timezone="UTC"),
        id="expire_check",
        name="Expire-check (every hour)",
        # ``coalesce=True``: если scheduler проспал несколько часов, выполнить
        # один раз, а не накопленную пачку — это нужное для нас поведение.
        coalesce=True,
        # ``misfire_grace_time``: если job не запустился вовремя (например,
        # бот перезапустился), дать ему 30 минут на догон.
        misfire_grace_time=30 * 60,
        max_instances=1,
    )

    # 2) Daily reminders — раз в сутки, в 10:00 UTC (днём, чтобы пользователи
    #    видели сообщения, а не получали их посреди ночи).
    scheduler.add_job(
        _wrap(reminders_job, bot, "reminders"),
        trigger=CronTrigger(hour=10, minute=0, timezone="UTC"),
        id="reminders",
        name="Subscription reminders 3d/1d/0d (daily)",
        coalesce=True,
        misfire_grace_time=6 * 60 * 60,
        max_instances=1,
    )

    # 3) Traffic snapshots — каждые 6 часов (00/06/12/18 UTC).
    scheduler.add_job(
        _wrap(traffic_snapshot_job, bot, "traffic_snapshots"),
        trigger=CronTrigger(hour="0,6,12,18", minute=5, timezone="UTC"),
        id="traffic_snapshots",
        name="Traffic snapshots (every 6 hours)",
        coalesce=True,
        misfire_grace_time=60 * 60,
        max_instances=1,
    )

    # 4) Fallback auto-renewal — раз в сутки, в 09:00 UTC (РАНЬШЕ reminders в
    #    10:00, чтобы успеть списать с баланса до того, как уйдёт напоминание
    #    «истекает сегодня»). Покрывает только wallet-fallback подписки
    #    (auto_renew=1, tg_sub_charge_id IS NULL) — нативные Star Subscriptions
    #    продлевает сам Telegram.
    scheduler.add_job(
        _wrap(auto_renew_job, bot, "auto_renew"),
        trigger=CronTrigger(hour=9, minute=0, timezone="UTC"),
        id="auto_renew",
        name="Auto-renewal from wallet balance (daily)",
        coalesce=True,
        misfire_grace_time=6 * 60 * 60,
        max_instances=1,
    )

    # 5) Panel health-check — every 30 minutes. Probes the 3x-ui panel and
    #    alerts admins ONLY on an up↔down transition (state is persisted in
    #    ``health_status``). ``max_instances=1`` so a slow probe never overlaps
    #    with the next tick.
    scheduler.add_job(
        _wrap(health_check_job, bot, "health_check"),
        trigger=CronTrigger(minute="0,30", timezone="UTC"),
        id="health_check",
        name="3x-ui panel health-check (every 30 minutes)",
        coalesce=True,
        misfire_grace_time=10 * 60,
        max_instances=1,
    )

    logger.info(
        "scheduler: configured 5 jobs (expire_check / reminders / "
        "traffic_snapshots / auto_renew / health_check)"
    )
    return scheduler
