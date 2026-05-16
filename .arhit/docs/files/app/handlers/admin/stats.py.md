# app/handlers/admin/stats.py

Админский экран «Статистика». Stateless — период переключается через callback (StatsCB.field), нет FSM.

router = Router(name="admin_stats").

Константы:
- _PERIODS — словарь key→(label, timedelta): 7d/30d/all. all=timedelta(days=36500).
- _DEFAULT_PERIOD = '30d'.
- _EXPIRING_WINDOW_DAYS = 7.
- _PAYMENTS_WINDOW = timedelta(days=30) — фиксированное окно для счётчика платежей (стабильная точка сравнения).
- _MAX_EXPIRING_ROWS = 10.
- _TOP_PROMOS_LIMIT = 5.

Helpers:
- _period_meta(key) -> (label, timedelta) — с fallback на default.
- _format_expiring(subs, tg_ids) -> str — список «истекающих» по 1 строке (tg_id, sub#id, expires_at), обрезка на 10 + хвост.
- _build_text(period_key) -> str — все запросы в одном get_conn: revenue_stars, active_subscriptions_count, expiring_in(7), top_promos(5), users_count, payments_count_period(30d), резолв tg_id для expiring. Обрезает на 4000 символов.
- _render(callback, period_key) — edit_message_text с stats_kb(active_period=period_key).

Хендлеры:
- cb_open_stats (AdminCB area=stats action=open) — рендерит с _DEFAULT_PERIOD.
- cb_period (StatsCB action=period) — переключение headline-периода.
- cb_refresh (StatsCB action=refresh) — пересчёт с тем же периодом (period передаётся в callback.field).

Зависимости: app.db.engine, app.db.repos.users, app.db.repos.subscriptions.Subscription, app.keyboards.admin (AdminCB, StatsCB, stats_kb), app.services.stats.
