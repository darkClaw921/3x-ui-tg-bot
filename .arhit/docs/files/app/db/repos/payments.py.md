# app/db/repos/payments.py

Репозиторий таблицы payments (Stars-платежи).

PaymentStatus = Literal['paid','refunded'].

Dataclass Payment(slots, frozen): id, user_id, subscription_id, telegram_charge_id, stars_amount, plan_id, promo_id, status, created_at.
Helper _to_iso(datetime|str) -> str — UTC ISO-8601 seconds.

Async-функции:
- create(conn, user_id, subscription_id, telegram_charge_id, stars_amount, plan_id, promo_id, status='paid') -> Payment. UNIQUE на telegram_charge_id защищает от дублей: повторный create поднимает aiosqlite.IntegrityError, caller должен ловить и обращаться к get_by_charge_id для идемпотентного обработчика successful_payment.
- get(conn, payment_id) -> Payment | None.
- get_by_charge_id(conn, telegram_charge_id) -> Payment | None.
- list_for_user(conn, user_id) -> list[Payment] — ORDER BY created_at DESC.
- total_stars_period(conn, start, end) -> int — SUM(stars_amount) WHERE status='paid' AND created_at BETWEEN [start, end] (включительно). Возвращает 0 если ничего не подходит (COALESCE).
- set_status(conn, payment_id, status).
