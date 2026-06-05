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

Все job-ы максимально устойчивы к ошибкам отдельных подписок: исключение в
одной итерации логируется через ``loguru`` и не валит ни весь job, ни
сам scheduler. Bot-инстанс пробрасывается через closure в
:func:`setup_scheduler`, поэтому модуль не лезет в импорты ``main`` (no
circular imports).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Literal

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from app.db.engine import get_conn
from app.db.repos import subscriptions as subs_repo
from app.db.repos import users as users_repo
from app.xui import XuiError, get_xui_client
from app.xui.clients import get_client_traffics, update_client

# Тип «насколько близок дедлайн» — совпадает с CHECK-constraint в БД.
ReminderKind = Literal["3d", "1d", "0d"]

# Шаблоны сообщений. Держим тексты в одном месте, чтобы при необходимости
# легко поправить тон без правки логики.
_REMINDER_TEXTS: dict[ReminderKind, str] = {
    "3d": (
        "⏳ Ваша VPN-подписка истекает через 3 дня.\n"
        "Откройте «Моя подписка» и продлите её, чтобы не остаться без доступа."
    ),
    "1d": (
        "⏳ Ваша VPN-подписка истекает завтра.\n"
        "Продлите её через меню «Моя подписка», чтобы избежать перерыва."
    ),
    "0d": (
        "⚠️ Ваша VPN-подписка истекает сегодня.\n"
        "Продлите её прямо сейчас, иначе доступ будет отключён автоматически."
    ),
}

_EXPIRED_TEXT = (
    "❌ Срок вашей VPN-подписки истёк, доступ временно отключён.\n"
    "Чтобы продолжить пользоваться сервисом, оформите продление в меню "
    "«Купить подписку»."
)


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


async def _safe_send(bot: Bot, tg_id: int, text: str) -> None:
    """Шлёт сообщение пользователю, проглатывая Telegram-ошибки.

    Юзер мог заблокировать бота, удалить чат или быть deactivated — это не
    повод валить job. Любая ошибка только логируется.
    """
    try:
        await bot.send_message(tg_id, text)
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
            await _safe_send(bot, user.tg_id, _EXPIRED_TEXT)
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

        await _safe_send(bot, user.tg_id, _REMINDER_TEXTS[kind])
        sent_count += 1

    logger.info("scheduler: reminders_job done sent={}", sent_count)


async def traffic_snapshot_job(bot: Bot) -> None:  # noqa: ARG001 — bot принимается ради единого callable-signature
    """Снимает трафик-снапшот для каждой активной подписки.

    Ошибки 3x-ui по конкретной подписке — log + skip; ошибки записи в БД
    — log + skip. Главное — job не падает целиком из-за одного клиента.

    ``bot`` принимается ради единообразной подписи job-ов (см.
    :func:`setup_scheduler`), но в данный момент не используется.
    """
    logger.info("scheduler: traffic_snapshot_job start")
    written = 0

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

    logger.info("scheduler: traffic_snapshot_job done written={}", written)


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
    """Создаёт и наполняет :class:`AsyncIOScheduler` тремя job-ами.

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

    logger.info(
        "scheduler: configured 3 jobs (expire_check / reminders / traffic_snapshots)"
    )
    return scheduler
