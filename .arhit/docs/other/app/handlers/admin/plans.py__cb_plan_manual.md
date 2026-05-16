# app/handlers/admin/plans.py::cb_plan_manual

Switches a numeric wizard step from preset-buttons to manual text entry. Does NOT change FSM state (already in the right waiting_* state); just sends an instruction message with cancel_kb. Field validates against 'days'/'price'/'gb'.
