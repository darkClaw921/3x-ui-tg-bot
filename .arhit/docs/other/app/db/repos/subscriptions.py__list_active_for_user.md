# app/db/repos/subscriptions.py::list_active_for_user

Возвращает все активные подписки пользователя (status='active' AND expires_at > now), отсортированные по expires_at DESC, id DESC. Используется для UI-сценария 'несколько подписок на пользователя' (список всех активных, выбор какую продлевать). Сигнатура: async def list_active_for_user(conn: aiosqlite.Connection, user_id: int) -> list[Subscription]. Сосуществует с get_active_for_user (тот возвращает только последнюю или None — оставлен для has_subscription булева в start.py).
