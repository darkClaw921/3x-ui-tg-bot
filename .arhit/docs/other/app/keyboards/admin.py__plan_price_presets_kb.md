# app/keyboards/admin.py::plan_price_presets_kb

Inline keyboard with 6 preset Stars values (0, 50, 100, 200, 500, 1000) + manual entry + cancel. Shown during PlanCreate.waiting_price. Each preset emits PlanCB(action='preset', field='price', id=<stars>).
