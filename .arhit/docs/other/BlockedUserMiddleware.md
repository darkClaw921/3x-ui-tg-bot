# BlockedUserMiddleware

app/middlewares/blocked.py — outer dispatcher-middleware, регистрируется ПЕРВЫМ (до UserContextMiddleware). Резолвит tg_id через _extract_tg_user, проверяет users_repo.is_blocked (узкий lookup, не зависит от data['user']); админы (ADMIN_IDS) никогда не блокируются; забаненному короткий отказ blocked.refused + потребление апдейта; fail-open при ошибке БД.
