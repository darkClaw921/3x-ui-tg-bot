# app/db/repos/users.py

Репозиторий пользователей.

- Dataclass User(id, tg_id, username, first_name, is_admin, created_at).
- User.from_row(row) — построение из aiosqlite.Row.
- async def get_by_tg_id(conn, tg_id) -> User | None.
- async def get_by_id(conn, user_id) -> User | None.
- async def get_by_username(conn, username) -> User | None — case-insensitive (COLLATE NOCASE), убирает ведущий '@'. Возвращает None для пустой строки. Используется admin-флоу 'Пользователи'.
- async def create(conn, tg_id, username, first_name, is_admin=False) -> User.
- async def get_or_create(conn, tg_id, username, first_name) -> User — идемпотентен; is_admin синхронизируется с settings.ADMIN_IDS.
- async def set_admin(conn, user_id, value: bool).
