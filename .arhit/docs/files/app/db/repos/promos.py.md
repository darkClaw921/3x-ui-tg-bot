# app/db/repos/promos.py

Репозиторий promos + promo_redemptions.

PromoType = Literal['percent','flat_stars','free_days'].

Dataclass Promo(slots, frozen): id, code, type, value, max_uses, used_count, expires_at, created_at, created_by.
Dataclass Redemption(slots, frozen): id, promo_id, user_id, subscription_id, redeemed_at.
Helper _utcnow_iso() — UTC ISO-8601 seconds.

Async-функции:
- create(conn, code, type, value, max_uses, expires_at, created_by) -> Promo.
- get(conn, promo_id) -> Promo | None.
- get_by_code(conn, code) -> Promo | None — case-insensitive через WHERE code = ? COLLATE NOCASE.
- list_active(conn) -> list[Promo] — (expires_at IS NULL OR expires_at>now) AND (max_uses=0 OR used_count<max_uses), ORDER BY created_at DESC.
- deactivate(conn, promo_id) — UPDATE expires_at = now (мягкое выключение, не DELETE).
- try_redeem(conn, promo_id, user_id, subscription_id) -> bool — атомарный redeem внутри transaction(conn): SELECT с валидацией → UPDATE с capacity-guarded WHERE (max_uses=0 OR used_count<max_uses) AND (expires_at IS NULL OR expires_at>now) → INSERT в promo_redemptions. Возвращает False если промо невалиден или гонка перехватила слот. На прочих исключениях — rollback + re-raise.
- list_redemptions(conn, promo_id) -> list[Redemption] — newest first.

Зависимости: app.db.engine.transaction (для try_redeem).
