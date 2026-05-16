# app/handlers/admin/plans.py::cb_plan_preset

Universal preset-button callback for the create-plan wizard. Dispatches on PlanCB.field: 'days'→writes data, transitions to waiting_price, sends plan_price_presets_kb; 'price'→writes, transitions to waiting_traffic_gb, sends plan_gb_presets_kb; 'gb'→terminal step, calls _finalize_plan_create (persists plan + clears state + shows card).
