# app/handlers/admin/promos.py

Хэндлеры CRUD промокодов с FSM-флоу мастера создания.

router = Router(name='admin_promos').

Helpers:
- _TYPE_LABELS — RU-метки типов промо.
- _format_promo(promo) — HTML-карточка со статусом (активен/исчерпан/истёк).
- _list_all_promos(conn) — inline-SQL (репо не имеет list_all).
- _promo_is_active(promo), _show_card, _show_list.
- _parse_expires_at(raw) — принимает '-'/'skip'/'нет'/'no' → None, иначе 'YYYY-MM-DD' → ISO-8601 UTC 23:59:59; False на parse-error.
- _expires_days_to_iso(days) — конвертирует пресет +N дней в ISO-строку (now + N days); 0 → None (бессрочно).

Базовые callback-ы:
- cb_open (AdminCB area=promos action=open).
- cb_list / cb_card / cb_deactivate / cb_redemptions (показывает историю с tg_id, датой, sub_id).

Wizard PromoCreate (5 шагов): cb_create → st_code → cb_type → st_value → st_max_uses → st_expires_at.
- st_code: уникальность через get_by_code, без пробелов.
- cb_type (PromoCB action=type, field ∈ {percent, flat_stars, free_days}) — после выбора шлёт promo_value_presets_kb(promo_type).
- st_value: валидация — percent 1..100, flat_stars/free_days > 0. На каждом из шагов value / max_uses / expires_at показывается пресет-клавиатура (promo_value_presets_kb / promo_max_uses_presets_kb / promo_expires_presets_kb), но ручной текстовый ввод сохранён.
- st_max_uses: ≥0, 0 = без лимита.
- st_expires_at: parse + финализация. Финализация вынесена в _finalize_promo_create — общая точка для preset- и manual-путей. Делает promos_repo.create(code, type, value, max_uses, expires_at, created_by=user.id). На aiosqlite.IntegrityError — fallback с сообщением об ошибке.

Общие preset/manual callback-и (PromoCB action ∈ {preset, manual}, field ∈ {value, max_uses, expires}):
- _PROMO_STEP_FLOW: dict[str, tuple[fsm_key, next_state, prompt_factory]] — мапа шага на FSM-ключ, следующее состояние и фабрику клавиатуры/подсказки.
- cb_promo_preset(callback, callback_data, state): для шагов value/max_uses — пишет callback_data.id в FSM-data и переходит к следующему шагу; для шага expires — конвертирует days в ISO через _expires_days_to_iso и сразу финализирует промокод.
- cb_promo_manual(callback, callback_data): переключает шаг на ручной ввод (state остаётся waiting_*, шлёт текстовую подсказку).
