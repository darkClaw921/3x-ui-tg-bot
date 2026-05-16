# app/keyboards/admin.py::plan_gb_presets_kb

Inline keyboard with 6 preset traffic-GB values (0/10/50/100/250/500; 0 = unlimited, matches xui totalGB semantics) + manual entry + cancel. Shown during PlanCreate.waiting_traffic_gb. Each preset emits PlanCB(action='preset', field='gb', id=<gb>).
