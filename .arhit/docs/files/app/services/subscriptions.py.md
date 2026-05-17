# app/services/subscriptions.py

Сервисный слой создания/продления подписок. Гарантирует xui-first → DB-after порядок (xui клиент создаётся/обновляется первым, DB-строка пишется только после успеха).

Публичные функции:
- create_or_extend(conn, xui, user, plan, promo, *, inbound_id, extend_sub_id=None) — провизион платной подписки. extend_sub_id=None всегда создаёт новую подписку (новый UUID/email/sub_id, add_client + subs_repo.create). extend_sub_id=int продлевает конкретную подписку с проверкой ownership (sub.user_id == user.id) и status='active' (иначе ValueError). При extend inbound_id игнорируется — берётся существующий xui_inbound_id.
- activate_free_days(conn, xui, user, promo, *, inbound_id, extend_sub_id=None) — то же самое, но для бесплатных промокодов type='free_days'. Поддерживает тот же extend_sub_id-контракт.
- revoke(xui, sub) — отключает xui-клиента (enable=False, best-effort) и помечает DB-строку status='revoked'.

Внутреннее:
- _provision(...) — общий путь, выбор ветки create-vs-extend ЯВНЫЙ через extend_sub_id (никаких неявных решений на основе get_active_for_user).
- _expiry_ms / _parse_iso / _bonus_days_from_promo / _make_sub_id — helpers.

Ключевая инвариантa: пользователь может владеть произвольным числом активных подписок (по одной на устройство/inbound). Решение 'создать новую vs продлить какую' принимает caller (UI), сервис лишь исполняет.
