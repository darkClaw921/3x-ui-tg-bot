# app/services/stats.py

Сервис агрегатов для админ-статистики. Все функции async и принимают aiosqlite.Connection (DI как у репозиториев).

Helpers:
- _utcnow() -> datetime — текущее UTC, seconds resolution, tz-aware.
- _iso(value) -> str — нормализация datetime/str → ISO-8601 UTC.

Revenue:
- revenue_stars(conn, period: timedelta) -> int — суммарный Stars-доход за окно [now-period, now], делегирует в payments_repo.total_stars_period.
- total_stars_period(conn, date_from, date_to) -> int — pass-through к репо.

Subscriptions:
- active_subscriptions_count(conn) -> int — COUNT по subscriptions WHERE status='active' AND expires_at > now.
- expiring_in(conn, days) -> list[Subscription] — обёртка над subs_repo.list_expiring_in.
- expiring_in_days(conn, days) — алиас expiring_in, чтобы имя совпадало с план-спецификацией.

Promos:
- top_promos(conn, limit=5) -> list[Promo] — SELECT * FROM promos ORDER BY used_count DESC, id DESC LIMIT ?. Включает деактивированные/истёкшие.

Users/Payments:
- users_count(conn) -> int — COUNT по users.
- users_count_total(conn) — алиас users_count.
- payments_count_period(conn, date_from, date_to) -> int — COUNT по payments WHERE status='paid' AND created_at в окне.

Зависимости: app.db.repos.payments, app.db.repos.subscriptions, app.db.repos.promos.Promo, app.db.repos.subscriptions.Subscription.
