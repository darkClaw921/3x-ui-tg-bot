# app/keyboards/admin.py::plan_days_presets_kb

Inline keyboard with 6 preset day values (7, 14, 30, 90, 180, 365) + a manual entry button + cancel. Shown during PlanCreate.waiting_days. Each preset emits PlanCB(action='preset', field='days', id=<days>).
