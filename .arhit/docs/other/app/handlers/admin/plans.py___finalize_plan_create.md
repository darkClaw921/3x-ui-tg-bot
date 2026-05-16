# app/handlers/admin/plans.py::_finalize_plan_create

Shared finalizer for both terminal paths of the create-plan wizard (st_traffic_gb manual text and cb_plan_preset on field='gb'). Reads title/days/price from FSM data, takes traffic_gb as kwarg, calls plans_repo.create, clears state, sends success message with plan_card_kb.
