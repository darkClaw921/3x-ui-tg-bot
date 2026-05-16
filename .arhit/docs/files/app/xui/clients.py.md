# app/xui/clients.py

Модуль работы с клиентами 3x-ui inbound'а (CRUD над панелью + helpers генерации ID/email).

Helpers:
- make_client_uuid() -> str — str(uuid4()) для vless client id.
- make_client_email(tg_id: int, username: str | None = None) -> str — формирует уникальный label клиента для панели 3x-ui. Если задан username, он нормализуется (lowercase; все символы вне [A-Za-z0-9_] заменяются на _; обрезка ведущих/хвостовых _; cap 32) и формат принимает вид <safe_username>_tg_<tg_id>_<6hex>. Если username пустой или после нормализации остался пустым — fallback на legacy-формат tg_<tg_id>_<6hex>. Suffix secrets.token_hex(3) (6 hex) обеспечивает уникальность при пере-подписке после del_client (3x-ui требует уникальный email на inbound, и сохраняет traffic-снэпшоты после удаления, поэтому нельзя переиспользовать старый email).
- _make_sub_id() -> str — secrets.token_hex(8) (16 hex), внутренний suffix для panel sub URL.

CRUD функции:
- add_client(client, inbound_id, client_uuid, email, expiry_ts_ms, total_gb=0, sub_id=None, flow='', enable=True, limit_ip=0, tg_id='', reset=0) -> dict — POST /panel/api/inbounds/addClient. expiry_ts_ms в миллисекундах; total_gb — квота трафика в ГБ (0 = unlimited); settings оборачивается в JSON-строку (важный quirk 3x-ui).
- update_client(client, inbound_id, client_uuid, **fields) -> dict — POST /panel/api/inbounds/updateClient/:uuid. Whitelist _UPDATABLE_CLIENT_FIELDS (id, email, expiryTime, totalGB, enable, flow, subId, limitIp, tgId, reset). Неизвестные ключи → ValueError. Принимает партиал.
- del_client(client, inbound_id, client_uuid) -> None — POST /panel/api/inbounds/:id/delClient/:uuid. Soft-fail на 'not exist'/'not found'/'no such' (идемпотентно).
- get_client_traffics(client, email) -> dict — GET /panel/api/inbounds/getClientTraffics/:email. Возвращает {} если obj=None.

Используется services.subscriptions._provision и handlers.user.
