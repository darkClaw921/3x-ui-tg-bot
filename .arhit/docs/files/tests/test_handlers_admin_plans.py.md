# tests/test_handlers_admin_plans.py

Тесты для app.handlers.admin.plans — CRUD мастер планов с новым шагом выбора inbound.

Покрытие хендлеров (54 теста):
- Навигация: cb_open, cb_list, cb_card (existing/missing), cb_edit_menu, cb_deactivate.
- Create wizard: cb_create → waiting_title → waiting_days → waiting_price → waiting_traffic_gb → _enter_inbounds_step (waiting_inbounds) → cb_inbounds_done.
- st_title: empty/valid.
- st_days/st_price/st_traffic_gb: non-integer, negative, valid (последний теперь advances to inbounds step без создания плана).
- Preset/manual callbacks для days/price/gb (cb_plan_preset, cb_plan_manual): gb теперь advances to inbounds step (не создаёт план).
- _enter_inbounds_step: xui unavailable → state not advanced + сообщение, empty inbounds → same.
- cb_toggle_inbound: XOR selection (двойной клик снимает).
- cb_inbounds_done: empty selected (alert + no clear), create mode (creates plan + set_inbounds), edit mode (set_inbounds на existing plan).
- cb_edit_inbounds: preload current set в selected_inbounds, unknown plan (alert), xui unavailable (alert + state stays), empty panel (alert).
- Edit wizard (текстовые поля): cb_edit с known/unknown field, st_edit_value для title/days/price_stars/traffic_gb (valid/invalid/edge).
- _format_plan: с remarks, missing remark («(удалён)»), без remarks arg, пустой remarks dict («не настроены»).

Использует stub _stub_inbounds для InboundOption, autouse _clear_inbounds_cache.

См. также: app/handlers/admin/plans.py.
