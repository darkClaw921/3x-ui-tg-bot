# app/handlers/admin/plans.py::st_traffic_gb

Manual text-input handler for the terminal wizard step PlanCreate.waiting_traffic_gb. Validates integer ≥ 0 (0 = unlimited). On success delegates to _finalize_plan_create which persists the plan via plans_repo.create(traffic_gb=...), clears state and shows the new card.
