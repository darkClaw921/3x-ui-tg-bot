# grant_subscription

app/services/subscriptions.py::grant_subscription — ручная выдача подписки админом (xui-first через _provision, без оплаты). days=None → plan.days, иначе override; фиксирует plan_id + traffic_gb; всегда создаёт новую подписку (extend_sub_id=None).
