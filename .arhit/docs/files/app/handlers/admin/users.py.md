# app/handlers/admin/users.py

Админский экран «Пользователи» — поиск + карточка пользователя.

router = Router(name="admin_users").

Константы:
- _MAX_PAYMENTS = 10 — лимит платежей в карточке.

Helpers:
- _safe(value) -> str — HTML-escape для имён/usernames.
- _fetch_traffic_line(sub) -> str — pulls traffic через xui.clients.get_client_traffics; XuiError→'панель недоступна', пустой ответ→'клиент не найден в панели', не-active → '' (без отображения).
- _sub_status_glyph(sub) -> str — ✅/🚫/❌ по эффективному статусу.
- _format_payment(p) -> str — однострочный summary платежа (stars, charge_id, plan, promo, дата).
- _build_card(target) -> (text, active_sub_id, is_admin) — собирает HTML-карточку: header (имя/tg_id/username/is_admin/created_at) + список подписок (active с трафиком, inactive — компактный) + 10 последних платежей. Обрезает на 4000 символов.
- _render_card_message(message, target, edit=True) — рендер карточки.
- _resolve_user_query(query) -> User | None — цифры→get_by_tg_id, иначе→get_by_username (case-insensitive).

Хендлеры:
- cb_open_users (AdminCB area=users action=open) — точка входа из админ-меню; ставит FSM AdminSearchUser.waiting_query, просит ввести tg_id или @username.
- cb_search (UserCB action=search) — re-enter поиска.
- st_query (AdminSearchUser.waiting_query) — резолвит пользователя, рендерит карточку или сообщает «не найден».
- cb_card (UserCB action=card) — открыть карточку по users.id.
- cb_revoke (UserCB action=revoke, id=sub_id, user_id=users.id) — services.subscriptions.revoke(xui, sub); защита sub.user_id==target.id; обновляет карточку.
- cb_toggle_admin (UserCB action=toggle_admin, id=users.id) — flip is_admin через users_repo.set_admin (UserContextMiddleware re-синхронизирует с ADMIN_IDS на следующем апдейте).

Зависимости: app.db.engine, app.db.repos (payments, subscriptions, users), app.handlers.user.my_subscription._format_bytes/_is_active (переиспользование), app.keyboards.admin (AdminCB, UserCB, cancel_kb, user_card_kb), app.services.subscriptions, app.states.admin.AdminSearchUser, app.xui (XuiError, get_xui_client), app.xui.clients.get_client_traffics.
