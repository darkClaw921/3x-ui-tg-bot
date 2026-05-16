"""Admin "Статистика" — revenue / active subs / expiring / top promos.

The screen has a single state-less render path: pick a *headline*
period (7 days / 30 days / all time) and pull the rest of the metrics
which are not period-dependent (active subs, expiring in 7 days,
top-5 promos, total users).

Period is carried inside the callback (``StatsCB.field``) so we don't
need FSM — switching periods or refreshing the screen is a stateless
``edit_message_text`` call.

Output structure
----------------

* **Заголовок** + currently-selected period label.
* **Доход (Stars)** for the selected period.
* **Активные подписки** count.
* **Истекающих за 7 дней** count + brief list (up to 10 rows).
* **Платежей за 30 дней** count (always 30 days — gives a stable
  comparison datapoint regardless of the headline window).
* **Всего пользователей**.
* **Топ-5 промокодов** by ``used_count``.

Telegram limits the message body to 4096 characters; the layout is
designed to stay well under it even with the maximum 10 expiring rows
+ 5 promos. The expiring list is truncated to 10 entries.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.db.engine import get_conn
from app.db.repos import users as users_repo
from app.db.repos.subscriptions import Subscription
from app.keyboards.admin import AdminCB, StatsCB, stats_kb
from app.services import stats as stats_service

router = Router(name="admin_stats")


# --------------------------------------------------------------------- #
# Period helpers
# --------------------------------------------------------------------- #


# Mapping of callback key → (human label, lookback). ``all`` uses a very
# large timedelta which is effectively "since the epoch" — there's no
# separate codepath because the underlying SQL is the same.
_PERIODS: dict[str, tuple[str, timedelta]] = {
    "7d": ("за 7 дней", timedelta(days=7)),
    "30d": ("за 30 дней", timedelta(days=30)),
    "all": ("за всё время", timedelta(days=36500)),
}

_DEFAULT_PERIOD = "30d"
_EXPIRING_WINDOW_DAYS = 7
_PAYMENTS_WINDOW = timedelta(days=30)
_MAX_EXPIRING_ROWS = 10
_TOP_PROMOS_LIMIT = 5


def _period_meta(key: str) -> tuple[str, timedelta]:
    """Return ``(label, lookback)`` for ``key`` (fallback to default)."""
    return _PERIODS.get(key, _PERIODS[_DEFAULT_PERIOD])


# --------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------- #


def _format_expiring(subs: list[Subscription], tg_ids: dict[int, int]) -> str:
    """Format the "expiring soon" sub-section.

    ``tg_ids`` is a precomputed ``{users.id: tg_id}`` map (populated in
    :func:`_build_text`) so we don't hit the DB once per row.
    """
    if not subs:
        return "нет"
    lines: list[str] = []
    shown = subs[:_MAX_EXPIRING_ROWS]
    for s in shown:
        owner = tg_ids.get(s.user_id, 0)
        lines.append(
            f"• <code>{owner}</code> · sub#{s.id} · "
            f"до <code>{s.expires_at}</code> UTC"
        )
    if len(subs) > _MAX_EXPIRING_ROWS:
        lines.append(f"… и ещё {len(subs) - _MAX_EXPIRING_ROWS}")
    return "\n".join(lines)


async def _build_text(period_key: str) -> str:
    """Compose the full HTML body for the stats screen."""
    label, lookback = _period_meta(period_key)
    now = datetime.now(UTC).replace(microsecond=0)
    payments_window_start = now - _PAYMENTS_WINDOW

    async with get_conn() as conn:
        revenue = await stats_service.revenue_stars(conn, lookback)
        active_count = await stats_service.active_subscriptions_count(conn)
        expiring = await stats_service.expiring_in(conn, _EXPIRING_WINDOW_DAYS)
        top_promos = await stats_service.top_promos(conn, _TOP_PROMOS_LIMIT)
        total_users = await stats_service.users_count(conn)
        payments_30d = await stats_service.payments_count_period(
            conn, payments_window_start, now
        )
        # Resolve owners for the expiring list in a single pass.
        tg_ids: dict[int, int] = {}
        for s in expiring[:_MAX_EXPIRING_ROWS]:
            if s.user_id not in tg_ids:
                u = await users_repo.get_by_id(conn, s.user_id)
                tg_ids[s.user_id] = u.tg_id if u else 0

    promo_lines: list[str] = []
    if top_promos:
        for promo in top_promos:
            promo_lines.append(
                f"• <code>{promo.code}</code> "
                f"({promo.type}:{promo.value}) — <b>{promo.used_count}</b> исп."
            )
    else:
        promo_lines.append("нет данных")

    text = "\n".join(
        [
            f"<b>📊 Статистика бота</b> ({label})",
            "",
            f"💰 Доход: <b>{revenue}</b> ⭐",
            f"✅ Активные подписки: <b>{active_count}</b>",
            f"💳 Платежей за 30 дней: <b>{payments_30d}</b>",
            f"👥 Всего пользователей: <b>{total_users}</b>",
            "",
            f"<b>⏳ Истекают за {_EXPIRING_WINDOW_DAYS} дн.:</b>",
            _format_expiring(expiring, tg_ids),
            "",
            f"<b>🎟 Топ-{_TOP_PROMOS_LIMIT} промокодов:</b>",
            *promo_lines,
        ]
    )
    if len(text) > 4000:
        text = text[:3900] + "\n…\n(вывод обрезан)"
    return text


async def _render(callback: CallbackQuery, period_key: str) -> None:
    """Render the stats screen with the chosen ``period_key``."""
    text = await _build_text(period_key)
    if callback.message is not None:
        await callback.message.edit_text(
            text,
            reply_markup=stats_kb(active_period=period_key),
        )


# --------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------- #


@router.callback_query(AdminCB.filter((F.area == "stats") & (F.action == "open")))
async def cb_open_stats(callback: CallbackQuery) -> None:
    """Entry from the admin main menu — show the default-period view."""
    await _render(callback, _DEFAULT_PERIOD)
    await callback.answer()


@router.callback_query(StatsCB.filter(F.action == "period"))
async def cb_period(callback: CallbackQuery, callback_data: StatsCB) -> None:
    """Switch the headline period."""
    period = callback_data.field if callback_data.field in _PERIODS else _DEFAULT_PERIOD
    await _render(callback, period)
    await callback.answer()


@router.callback_query(StatsCB.filter(F.action == "refresh"))
async def cb_refresh(callback: CallbackQuery, callback_data: StatsCB) -> None:
    """Recompute and re-render for the currently-selected period."""
    period = callback_data.field if callback_data.field in _PERIODS else _DEFAULT_PERIOD
    await _render(callback, period)
    await callback.answer("Обновлено")


__all__ = ["router"]
