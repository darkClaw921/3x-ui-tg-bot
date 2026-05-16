# app/middlewares/admin_only.py

Router-middleware AdminOnlyMiddleware. На Message/CallbackQuery: если data['user'].is_admin или event.from_user.id ∈ settings.ADMIN_IDS — пропускает; иначе отвечает «Доступ запрещён» (на CallbackQuery с show_alert=True) и поглощает апдейт без вызова handler. Static helper _is_admin(event, data) с приоритетом data['user'] (уже синхронизирован с ADMIN_IDS UserContextMiddleware'ом).
